"""Cost model service — class_type-keyed GPU-seconds registry for the graph composer.

Provides:
- `get_cost_entry(class_type, resolution, steps, turbo)` → CostEntry | None
- `estimate_chain(chain_graph)` → ChainEstimate with per-node breakdown + overhead
- Startup validation of `GPU_HOURLY_RATE` env var

Unknown class_types return None — the caller MUST treat None as "cost pending, dispatch
blocked", not as zero. The startup validator refuses to serve estimates if the env var
is missing or NaN, preventing silent zero-cost bypasses.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger("cost-model")

# ── Cost lookup key ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CostKey:
    """Composite key: class_type + resolution hint + steps + turbo flag."""
    class_type: str
    resolution: str = "768p"
    steps: int = 8
    turbo: bool = False


# ── Cost entry ───────────────────────────────────────────────────────────────


@dataclass
class CostEntry:
    """GPU-seconds for one node type at the given params.

    Attributes:
        class_type: ComfyUI node class type (e.g. "H3I2V", "KreaT2I")
        gpu_seconds_base: Seconds at 768p/8 steps/non-turbo
        resolution_mult: Dict mapping "Np" → multiplier (e.g. {"768p": 1.0, "1024p": 1.4})
        steps_power: Step count exponent (cost ∝ steps^steps_power; 1.0 = linear)
        turbo_mult: Multiplier when turbo mode is active (e.g. 0.25 for 4× faster)
        min_gpu_seconds: Floor to prevent zero-cost entries
        description: Human-readable label for cost breakdown UI
    """
    class_type: str
    gpu_seconds_base: float
    resolution_mult: Dict[str, float] = field(default_factory=lambda: {"768p": 1.0})
    steps_power: float = 1.0
    turbo_mult: float = 1.0
    min_gpu_seconds: float = 1.0
    description: str = ""

    def estimate(self, resolution: str = "768p", steps: int = 8, turbo: bool = False) -> float:
        """Compute estimated GPU-seconds for the given parameters."""
        res_mult = self.resolution_mult.get(resolution, 1.0)
        step_ratio = (steps / 8) ** self.steps_power
        turbo_factor = self.turbo_mult if turbo else 1.0
        raw = self.gpu_seconds_base * res_mult * step_ratio * turbo_factor
        return max(raw, self.min_gpu_seconds)

    def render(self, resolution: str = "768p", steps: int = 8, turbo: bool = False) -> str:
        """Render a human-readable cost line."""
        secs = self.estimate(resolution, steps, turbo)
        tag = "TURBO" if turbo else ""
        return f"{self.description or self.class_type} → {secs:.0f}s GPU {tag}".strip()


# ── Overhead entry ───────────────────────────────────────────────────────────


@dataclass
class OverheadEntry:
    """GPU-seconds for pipeline overhead that isn't a single class_type.

    Motion Director stitch overhead, frame re-anchoring, latent carry-forward.
    """
    name: str
    gpu_seconds_per_segment: float
    description: str = ""

    def estimate(self, segment_count: int) -> float:
        return self.gpu_seconds_per_segment * max(segment_count - 1, 0)

    def render(self, segment_count: int) -> str:
        secs = self.estimate(segment_count)
        if secs <= 0:
            return ""
        return f"{self.description or self.name} ({segment_count - 1} seams) → {secs:.0f}s GPU"


# ── Registry ─────────────────────────────────────────────────────────────────


class CostRegistry:
    """Class_type-keyed cost model with overhead entries.

    Maintained as a singleton per process. Unknown class_types return None
    from `lookup()` — consumers MUST treat None as "cost pending, blocked".
    """

    def __init__(self):
        self._entries: Dict[str, CostEntry] = {}
        self._overhead: Dict[str, OverheadEntry] = {}
        self._register_defaults()

    def _register_defaults(self):
        """Register known node types.

        NOTE(@ai-studio): Fill GPU-seconds and multipliers from actual
        benchmarks. The values below are conservative estimates from
        the Motion Director config and should be updated per real
        post-job reconciliation data.
        """
        # ── Image generation ────────────────────────────────────────────────
        self.register(CostEntry(
            class_type="KSampler",
            gpu_seconds_base=15.0,
            resolution_mult={"512p": 0.6, "768p": 1.0, "1024p": 1.8},
            steps_power=1.0,
            description="SDXL/1.5 single image",
        ))
        self.register(CostEntry(
            class_type="KSamplerAdvanced",
            gpu_seconds_base=15.0,
            resolution_mult={"512p": 0.6, "768p": 1.0, "1024p": 1.8},
            steps_power=1.0,
            description="SDXL/1.5 advanced sampler",
        ))

        # ── H3 video (MiniMax) ──────────────────────────────────────────────
        self.register(CostEntry(
            class_type="H3I2V",
            gpu_seconds_base=240.0,          # 4 min at 768p/8 steps
            resolution_mult={"512p": 0.7, "768p": 1.0, "1024p": 1.6},
            steps_power=1.0,                  # roughly linear in steps
            turbo_mult=0.25,                  # Turbo 4-step = 4× faster → 60s
            description="H3 I2V 5s clip",
        ))
        self.register(CostEntry(
            class_type="H3T2V",
            gpu_seconds_base=180.0,
            resolution_mult={"512p": 0.7, "768p": 1.0, "1024p": 1.6},
            steps_power=1.0,
            turbo_mult=0.25,
            description="H3 T2V 5s clip",
        ))
        self.register(CostEntry(
            class_type="H3Stitch",
            gpu_seconds_base=30.0,           # segment boundary cost, NOT included in MotionDir overhead
            resolution_mult={"768p": 1.0, "1024p": 1.3},
            turbo_mult=1.0,
            description="H3 stitch (per segment)",
        ))

        # ── Krea 2 ──────────────────────────────────────────────────────────
        self.register(CostEntry(
            class_type="KreaT2I",
            gpu_seconds_base=2.0,            # ~1700/hr → 2.1s per image
            resolution_mult={"768p": 1.0, "1024p": 1.2},
            steps_power=0.8,                  # less-than-linear scaling
            description="Krea 2 image gen",
        ))
        self.register(CostEntry(
            class_type="KreaI2I",
            gpu_seconds_base=2.5,
            resolution_mult={"768p": 1.0, "1024p": 1.2},
            steps_power=0.8,
            description="Krea 2 img2img",
        ))

        # ── Klein 9B ────────────────────────────────────────────────────────
        self.register(CostEntry(
            class_type="KleinT2I",
            gpu_seconds_base=2.5,            # ~2.5s per image
            resolution_mult={"768p": 1.0, "1024p": 1.4},
            steps_power=0.9,
            description="Klein 9B text-to-image",
        ))
        self.register(CostEntry(
            class_type="KleinI2I",
            gpu_seconds_base=2.5,            # same ballpark
            resolution_mult={"768p": 1.0, "1024p": 1.4},
            steps_power=0.9,
            description="Klein 9B img2img",
        ))

        # ── Wan (generic) ───────────────────────────────────────────────────
        self.register(CostEntry(
            class_type="WanI2V",
            gpu_seconds_base=150.0,          # Lightning 4+4
            resolution_mult={"512p": 0.7, "768p": 1.0, "1024p": 1.5},
            steps_power=1.0,
            turbo_mult=0.5,
            description="Wan I2V clip",
        ))
        self.register(CostEntry(
            class_type="WanT2V",
            gpu_seconds_base=120.0,
            resolution_mult={"512p": 0.7, "768p": 1.0, "1024p": 1.5},
            steps_power=1.0,
            turbo_mult=0.5,
            description="Wan T2V clip",
        ))

        # ── Motion Director pipeline overhead ───────────────────────────────
        self._overhead["MotionDirectorStitch"] = OverheadEntry(
            name="MotionDirectorStitch",
            gpu_seconds_per_segment=30.0,
            description="Motion Director latent carry-forward per seam",
        )

    # ── Public API ───────────────────────────────────────────────────────────

    def register(self, entry: CostEntry):
        """Register or update a cost entry for a class_type."""
        self._entries[entry.class_type] = entry
        logger.info("Registered cost entry: %s = %ss base", entry.class_type, entry.gpu_seconds_base)

    def lookup(self, class_type: str) -> Optional[CostEntry]:
        """Look up a cost entry by class_type. Returns None for unknown types.

        The caller MUST treat None as "cost pending, dispatch blocked".
        """
        return self._entries.get(class_type)

    def known_types(self) -> List[str]:
        """Return all registered class_type strings."""
        return list(self._entries.keys())

    @property
    def overhead(self) -> Dict[str, OverheadEntry]:
        return dict(self._overhead)

    def estimate_chain(
        self,
        nodes: List[Dict],
        segment_count: int = 0,
    ) -> dict:
        """Estimate total cost for a chain of nodes.

        Each node dict must have at minimum:
            {"class_type": str, "resolution": str, "steps": int, "turbo": bool}

        Returns dict with:
            total_seconds: float (None if any node is unknown)
            total_cost: float (None if unknown, else USD)
            breakdown: list of per-node strings
            overhead: list of overhead strings
            blocked: list of unknown class_types (empty = all known)
        """
        hourly = _gpu_hourly_rate()
        if hourly is None:
            return {"total_seconds": None, "total_cost": None, "breakdown": [],
                    "overhead": [], "blocked": [], "error": "GPU_HOURLY_RATE not configured"}

        total = 0.0
        breakdown: List[str] = []
        blocked: List[str] = []

        for node in nodes:
            ct = node.get("class_type", "")
            entry = self.lookup(ct)
            if entry is None:
                blocked.append(ct)
                breakdown.append(f"{ct} → cost pending (blocked)")
                continue
            secs = entry.estimate(
                resolution=node.get("resolution", "768p"),
                steps=node.get("steps", 8),
                turbo=node.get("turbo", False),
            )
            total += secs
            breakdown.append(entry.render(
                resolution=node.get("resolution", "768p"),
                steps=node.get("steps", 8),
                turbo=node.get("turbo", False),
            ))

        overhead_lines: List[str] = []
        if segment_count > 1:
            for oh in self._overhead.values():
                oh_secs = oh.estimate(segment_count)
                if oh_secs > 0:
                    total += oh_secs
                    oh_line = oh.render(segment_count)
                    if oh_line:
                        overhead_lines.append(oh_line)

        cost = total / 3600 * hourly if hourly is not None and total > 0 else 0.0

        return {
            "total_seconds": total,
            "total_cost": round(cost, 4),
            "breakdown": breakdown,
            "overhead": overhead_lines,
            "blocked": blocked,
            "error": None,
        }


# ── Singleton ────────────────────────────────────────────────────────────────

_registry: Optional[CostRegistry] = None


def get_registry() -> CostRegistry:
    """Get or create the singleton CostRegistry."""
    global _registry
    if _registry is None:
        _registry = CostRegistry()
    return _registry


# ── Startup validator ────────────────────────────────────────────────────────


def _gpu_hourly_rate() -> Optional[float]:
    """Parse GPU_HOURLY_RATE env var. Returns None if missing or NaN."""
    raw = os.getenv("GPU_HOURLY_RATE")
    if not raw:
        return None
    try:
        rate = float(raw)
        if rate <= 0:
            logger.warning("GPU_HOURLY_RATE=%s is not positive, treating as unset", raw)
            return None
        return rate
    except (ValueError, TypeError):
        logger.warning("GPU_HOURLY_RATE='%s' is not a valid float, treating as unset", raw)
        return None


_COST_MODEL_INIT_ERROR: Optional[str] = None


def validate_startup() -> Optional[str]:
    """Run startup validation. Returns None on success, error message on failure.

    Call this at module import time in api.py. If it returns an error, the
    cost model endpoints should refuse to serve estimates.
    """
    global _COST_MODEL_INIT_ERROR

    rate = _gpu_hourly_rate()
    if rate is None:
        msg = (
            "GPU_HOURLY_RATE is unset or invalid. The cost model will refuse all "
            "estimates until this env var is set to a positive float (e.g. '0.52')."
        )
        _COST_MODEL_INIT_ERROR = msg
        logger.error(msg)
        return msg

    # Verify registry has entries
    registry = get_registry()
    known = registry.known_types()
    if not known:
        msg = "CostRegistry has zero registered class_types — no estimates can be served."
        _COST_MODEL_INIT_ERROR = msg
        logger.error(msg)
        return msg

    logger.info(
        "Cost model validated: GPU_HOURLY_RATE=$%.2f/hr, %d class_types registered",
        rate, len(known),
    )
    _COST_MODEL_INIT_ERROR = None
    return None


def startup_error() -> Optional[str]:
    """Return the init error message if validation failed, else None."""
    return _COST_MODEL_INIT_ERROR


# ── Auto-validate on import ──────────────────────────────────────────────────

validate_startup()