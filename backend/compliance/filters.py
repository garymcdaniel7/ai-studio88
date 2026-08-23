"""Bright-line prompt-ingress classifier for prohibited minors-related content."""

from __future__ import annotations

import re
from dataclasses import dataclass

from backend.compliance.quarantine import record_violation

_BLOCKED_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("minor", re.compile(r"\bminors?\b", re.IGNORECASE)),
    ("child", re.compile(r"\bchild(?:ren)?\b", re.IGNORECASE)),
    ("kid", re.compile(r"\bkids?\b", re.IGNORECASE)),
    ("teen", re.compile(r"\bteen(?:age|ager|s)?\b", re.IGNORECASE)),
    ("underage", re.compile(r"\bunder\s*age\b", re.IGNORECASE)),
    ("under-18", re.compile(r"\bunder\s*[- ]?\s*18\b", re.IGNORECASE)),
    ("preteen", re.compile(r"\bpre[- ]?teen\b", re.IGNORECASE)),
    ("schoolgirl", re.compile(r"\bschool\s*girl\b", re.IGNORECASE)),
    ("schoolboy", re.compile(r"\bschool\s*boy\b", re.IGNORECASE)),
    ("loli", re.compile(r"\bloli(?:ta)?\b", re.IGNORECASE)),
    ("shota", re.compile(r"\bshota\b", re.IGNORECASE)),
    ("toddler", re.compile(r"\btoddler\b", re.IGNORECASE)),
    ("infant", re.compile(r"\binfant\b", re.IGNORECASE)),
)


@dataclass(frozen=True, slots=True)
class PromptDecision:
    """Result of the bright-line prompt classifier."""

    blocked: bool
    instant_ban: bool
    matched_terms: tuple[str, ...]


def classify_prompt(prompt: str) -> PromptDecision:
    """Classify a prompt without logging or mutating state."""
    matched = tuple(label for label, pattern in _BLOCKED_PATTERNS if pattern.search(prompt))
    return PromptDecision(
        blocked=bool(matched),
        instant_ban=bool(matched),
        matched_terms=matched,
    )


def enforce_prompt_compliance(
    prompt: str,
    *,
    org_id: str = "",
    user_id: str = "",
) -> PromptDecision:
    """Block prohibited prompts and append a quarantine violation record."""
    decision = classify_prompt(prompt)
    if decision.blocked:
        record_violation(
            org_id=org_id,
            reason="bright-line-minors-prompt",
            source_type="prompt",
            matched_terms=decision.matched_terms,
        )
        raise PromptBlockedError(
            "Prompt blocked by the zero-tolerance minors-content policy.",
            matched_terms=decision.matched_terms,
            instant_ban=decision.instant_ban,
            user_id=user_id,
        )
    return decision


class PromptBlockedError(ValueError):
    """Raised when prompt ingress violates a bright-line safety rule."""

    def __init__(
        self,
        message: str,
        *,
        matched_terms: tuple[str, ...],
        instant_ban: bool,
        user_id: str,
    ) -> None:
        super().__init__(message)
        self.matched_terms = matched_terms
        self.instant_ban = instant_ban
        self.user_id = user_id
