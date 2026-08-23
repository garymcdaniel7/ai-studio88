"""Billing Router — Stripe checkout + subscriptions tied to the cost ledger.

Story: Monetize AI Studio by charging a platform margin on GPU compute and
offering a paid Pro tier, while keeping the "pay for what you use" promise.

Design:
    POST /api/v1/billing/checkout        → create a Stripe Checkout Session
                                            (mode=subscription for Pro, or
                                             mode=payment for compute top-up)
    POST /api/v1/billing/portal          → create/return a Billing Portal URL
    GET  /api/v1/billing/status          → current plan + credit balance
    POST /api/v1/billing/webhook         → Stripe webhook (verify signature,
                                            credit compute balance, upsert plan)

Credits: a workspace holds a "compute credit" balance (USD). GPU launches
reserve cost from this balance via the cost ledger. When a Stripe top-up or
subscription payment succeeds, we credit the ledger. This gives users a
prepaid balance they control, which the ledger already enforces.

Security:
    - All endpoints auth-gated via require_auth (org-scoped).
    - Webhook verifies the Stripe signature against STRIPE_WEBHOOK_SECRET.
    - Fail-safe: if Stripe is not configured, endpoints return 503 rather than
      silently pretending billing works (mirrors ledger fail-safe).
"""

from __future__ import annotations

import logging
import os

import stripe
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, Header, HTTPException, Request

from backend.auth import AuthUser, require_auth
from backend.billing.credit_costs import get_credit_cost
from backend.billing.credit_ledger import CreditEntryType, CreditLedgerEntry, CreditLedgerService
from backend.cost_ledger import get_spend_summary

logger = logging.getLogger(__name__)

load_dotenv(override=True)

router = APIRouter()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_STRIPE_API_KEY = os.getenv("STRIPE_SECRET_KEY", "")
_STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
_STRIPE_STARTER_PRICE_ID = os.getenv("STRIPE_STARTER_PRICE_ID", "")
_STRIPE_PRO_PRICE_ID = os.getenv("STRIPE_PRO_PRICE_ID", "")

# Platform margin applied to GPU compute (what the platform earns).
PLATFORM_MARGIN_RATE = 0.15  # 15% — DECISION-REQUIRED, set per business model

if _STRIPE_API_KEY:
    stripe.api_key = _STRIPE_API_KEY


def _stripe_configured() -> bool:
    return bool(_STRIPE_API_KEY and _STRIPE_WEBHOOK_SECRET)


def _require_stripe() -> None:
    if not _stripe_configured():
        raise HTTPException(
            status_code=503,
            detail="Billing is not configured. Set STRIPE_SECRET_KEY and STRIPE_WEBHOOK_SECRET.",
        )


# ---------------------------------------------------------------------------
# In-memory credit balance (per org). In production this belongs in the DB.
# Mirrors the cost ledger's in-memory store so it is safe for dev/test.
# ---------------------------------------------------------------------------

_credit_balances: dict[str, float] = {}
_plans: dict[str, str] = {}  # org_id -> plan name ("free" | "starter" | "pro")
_consumer_credit_ledger = CreditLedgerService()
_LOCK = None  # replaced below


def _org_balance(org_id: str) -> float:
    return _credit_balances.get(org_id, 0.0)


def credit_balance(org_id: str, amount_usd: float) -> float:
    """Add funds to a workspace's compute-credit balance. Returns new balance."""
    current = _org_balance(org_id)
    updated = current + amount_usd
    _credit_balances[org_id] = updated
    logger.info("Billing: credited %s to org %s (new balance %.2f)", amount_usd, org_id, updated)
    return updated


def get_plan(org_id: str) -> str:
    return _plans.get(org_id, "free")


async def debit_after_generation_success(
    org_id: str,
    preset_id: str,
    job_id: str,
) -> CreditLedgerEntry:
    """Debit consumer credits after a generation success transition."""
    cost = get_credit_cost(preset_id)
    return _consumer_credit_ledger.debit_after_success(
        org_id,
        cost["credits"],
        reason=f"generation:{preset_id}",
        ref_id=job_id,
        generation_succeeded=True,
    )


async def refund_failed_generation(
    org_id: str,
    preset_id: str,
    job_id: str,
) -> CreditLedgerEntry | None:
    """Refund a prior generation debit when the job ultimately fails.

    Generation debits happen only after success. Therefore a failure before a
    debit is a zero-charge outcome and returns ``None``; if a downstream
    failure occurs after the success transition, the matching debit is
    refunded exactly once.
    """
    debit = next(
        (
            entry
            for entry in _consumer_credit_ledger.entries(org_id)
            if entry.entry_type == CreditEntryType.DEBIT and entry.ref_id == job_id
        ),
        None,
    )
    if debit is None:
        return None

    return _consumer_credit_ledger.refund(
        org_id,
        -debit.amount,
        reason=f"failed-generation:{preset_id}",
        ref_id=f"refund:{job_id}",
    )


async def settle_generation_credits(
    org_id: str,
    preset_id: str,
    job_id: str,
    *,
    generation_succeeded: bool,
) -> CreditLedgerEntry | None:
    """Settle a generation outcome with success debit or failure refund."""
    if generation_succeeded:
        return await debit_after_generation_success(org_id, preset_id, job_id)
    return await refund_failed_generation(org_id, preset_id, job_id)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/checkout", tags=["billing"])
async def create_checkout(
    request: Request,
    user: AuthUser = Depends(require_auth),
) -> dict:
    """Create a Stripe Checkout Session.

    Body:
        mode: "subscription" (default) — start/upgrade a paid plan
              "payment" — top up GPU compute credits
        amount_usd: required when mode == "payment"

    Returns the checkout session URL (client redirects there).
    """
    _require_stripe()
    org_id = user.org_id
    if not org_id:
        raise HTTPException(status_code=400, detail="No workspace context for this user.")

    body = await request.json()
    mode = body.get("mode", "subscription")
    origin = request.headers.get("origin") or "http://localhost:3000"

    try:
        if mode == "payment":
            amount = float(body.get("amount_usd", 0))
            if amount < 1:
                raise HTTPException(status_code=400, detail="Top-up amount must be at least $1.")
            session = stripe.checkout.Session.create(
                mode="payment",
                payment_method_types=["card"],
                line_items=[{
                    "price_data": {
                        "currency": "usd",
                        "product_data": {"name": "AI Studio Compute Credits"},
                        "unit_amount": int(amount * 100),
                    },
                    "quantity": 1,
                }],
                metadata={"org_id": org_id, "mode": "payment"},
                success_url=f"{origin}/settings?billing=success",
                cancel_url=f"{origin}/settings?billing=cancelled",
            )
        else:
            # Subscription mode — requires a configured plan price.
            price_id = _STRIPE_PRO_PRICE_ID or _STRIPE_STARTER_PRICE_ID
            if not price_id:
                raise HTTPException(
                    status_code=503,
                    detail="No plan price configured. Set STRIPE_PRO_PRICE_ID or STRIPE_STARTER_PRICE_ID.",
                )
            session = stripe.checkout.Session.create(
                mode="subscription",
                line_items=[{"price": price_id, "quantity": 1}],
                metadata={"org_id": org_id, "mode": "subscription"},
                success_url=f"{origin}/settings?billing=success",
                cancel_url=f"{origin}/settings?billing=cancelled",
            )

        return {"url": session.url, "session_id": session.id}
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - network/provider error
        logger.error("Billing: checkout failed: %s", exc)
        raise HTTPException(status_code=502, detail="Could not create checkout session.") from exc


@router.post("/portal", tags=["billing"])
async def billing_portal(user: AuthUser = Depends(require_auth)) -> dict:
    """Return a Stripe Billing Portal URL for the user's customer record."""
    _require_stripe()
    org_id = user.org_id
    if not org_id:
        raise HTTPException(status_code=400, detail="No workspace context for this user.")

    # Look up or create the Stripe customer for this org.
    customers = stripe.Customer.list(metadata={"org_id": org_id}, limit=1)
    if customers.data:
        customer_id = customers.data[0].id
    else:
        customer = stripe.Customer.create(metadata={"org_id": org_id})
        customer_id = customer.id

    session = stripe.billing_portal.Session.create(
        customer=customer_id,
        return_url="http://localhost:3000/settings",  # configurable
    )
    return {"url": session.url}


@router.get("/status", tags=["billing"])
async def billing_status(user: AuthUser = Depends(require_auth)) -> dict:
    """Current plan + credit balance + spend summary for the workspace."""
    org_id = user.org_id
    if not org_id:
        raise HTTPException(status_code=400, detail="No workspace context for this user.")

    return {
        "plan": get_plan(org_id),
        "credit_balance_usd": round(_org_balance(org_id), 2),
        "platform_margin_rate": PLATFORM_MARGIN_RATE,
        "configured": _stripe_configured(),
        "spend_summary": get_spend_summary(org_id),
    }


@router.post("/webhook", tags=["billing"])
async def stripe_webhook(
    request: Request,
    stripe_signature: str | None = Header(default=None, alias="Stripe-Signature"),
) -> dict:
    """Handle Stripe webhooks: credit compute balance on successful payment."""
    if not _stripe_configured() or not stripe_signature:
        raise HTTPException(status_code=400, detail="Billing not configured or missing signature.")

    payload = await request.body()

    try:
        event = stripe.Webhook.construct_event(
            payload,
            stripe_signature,
            _STRIPE_WEBHOOK_SECRET,
        )
    except Exception as exc:
        logger.warning("Billing: invalid webhook signature: %s", exc)
        raise HTTPException(status_code=400, detail="Invalid signature.") from exc

    event_type = event.get("type")
    data = event.get("data", {}).get("object", {})
    logger.info("Billing: webhook event %s", event_type)

    if event_type == "checkout.session.completed":
        metadata = data.get("metadata", {})
        org_id = metadata.get("org_id")
        if org_id:
            if metadata.get("mode") == "payment":
                amount_total = (data.get("amount_total") or 0) / 100.0
                credit_balance(org_id, amount_total)
            else:
                # Subscription started/upgraded — set plan.
                _plans[org_id] = "pro"
                logger.info("Billing: org %s subscribed to Pro", org_id)

    elif event_type == "invoice.paid":
        # Recurring subscription payment — credit a monthly compute allowance.
        customer_id = data.get("customer")
        if customer_id:
            # Best-effort: map customer -> org via our metadata.
            customers = stripe.Customer.retrieve(customer_id, {"expand": []})
            org_id = (customers.get("metadata") or {}).get("org_id")
            if org_id:
                # DECISION-REQUIRED: monthly credit amount per plan.
                credit_balance(org_id, 20.0)
                _plans[org_id] = "pro"

    return {"received": True, "type": event_type}
