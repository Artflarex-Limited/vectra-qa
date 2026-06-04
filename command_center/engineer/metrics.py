"""
Live QA metrics — thresholds and in-memory recorder for the live command center.

Provides:
- ``MetricsConfig``: Pydantic model with the six thresholds defined by the spec.
- ``MetricsRecorder``: per-session recorder keyed by ``session_id`` in a module-level
  dict. Timing is captured with ``time.monotonic()`` so measurements are
  immune to wall-clock adjustments.

The module is deliberately side-effect free outside of its own in-memory
store and ``structlog`` calls. There is no network I/O, no database, no
filesystem writes — keeping the surface small and the thresholds
immutable at runtime (per the spec).
"""

from __future__ import annotations

import time
from threading import Lock
from typing import Any, Dict, Optional

import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger("engineer.metrics")


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


class MetricsConfig(BaseModel):
    """Immutable-at-runtime threshold configuration for live QA metrics.

    These defaults match the spec for the live QA engineer module. The
    model is frozen via Pydantic so a single instance can be reused
    safely across the process; per-session overrides are intentionally
    not supported.
    """

    first_response_ms: int = Field(
        default=2000,
        description="Max time (ms) for the first response to be emitted by an agent.",
    )
    narration_lag_ms: int = Field(
        default=5000,
        description="Max allowed narration lag (ms) between events.",
    )
    report_render_ms: int = Field(
        default=10000,
        description="Max render time (ms) for a session report.",
    )
    greeting_word_budget: int = Field(
        default=25,
        description="Word budget for greeting messages.",
    )
    narration_word_budget: int = Field(
        default=15,
        description="Word budget for an individual narration line.",
    )
    report_section_word_budget: int = Field(
        default=150,
        description="Word budget for a single report section.",
    )

    model_config = {"frozen": True}

    def to_dict(self) -> Dict[str, int]:
        """Return the thresholds as a plain dict for serialization."""
        return {
            "first_response_ms": self.first_response_ms,
            "narration_lag_ms": self.narration_lag_ms,
            "report_render_ms": self.report_render_ms,
            "greeting_word_budget": self.greeting_word_budget,
            "narration_word_budget": self.narration_word_budget,
            "report_section_word_budget": self.report_section_word_budget,
        }


# ---------------------------------------------------------------------------
# In-memory storage
# ---------------------------------------------------------------------------


# Module-level dict keyed by session_id. All access is guarded by a lock
# so concurrent agent callbacks cannot corrupt the per-session record.
_SESSIONS: Dict[str, Dict[str, Any]] = {}
_LOCK = Lock()
_CONFIG = MetricsConfig()


def _get_or_create(session_id: str) -> Dict[str, Any]:
    """Return the per-session bucket, creating it lazily on first access."""
    bucket = _SESSIONS.get(session_id)
    if bucket is not None:
        return bucket
    with _LOCK:
        bucket = _SESSIONS.get(session_id)
        if bucket is None:
            bucket = {
                "started_at": time.monotonic(),
                "first_response_ms": None,
                "narrations": [],
                "report_ms": None,
            }
            _SESSIONS[session_id] = bucket
    return bucket


# ---------------------------------------------------------------------------
# Recorder
# ---------------------------------------------------------------------------


class MetricsRecorder:
    """Record and retrieve per-session metrics.

    All public methods are safe to call from multiple threads. The
    underlying storage is a module-level dict, so recorder instances are
    essentially interchangeable — holding multiple instances is fine,
    sharing a single instance across the codebase is also fine.
    """

    def __init__(self, config: Optional[MetricsConfig] = None) -> None:
        # ``config`` is accepted for future-proofing but the spec
        # forbids per-session customization. The module-level ``_CONFIG``
        # remains the single source of truth.
        self._config = config or _CONFIG

    # -- mutation ---------------------------------------------------------

    def record_first_response(self, session_id: str) -> int:
        """Record the first-response latency for ``session_id``.

        Returns the measured latency in milliseconds. Repeated calls are
        idempotent — only the first measurement is retained.
        """
        bucket = _get_or_create(session_id)
        with _LOCK:
            existing = bucket["first_response_ms"]
            if existing is not None:
                logger.debug(
                    "metrics.first_response.duplicate",
                    session_id=session_id,
                    first_response_ms=existing,
                )
                return existing
            elapsed_ms = int((time.monotonic() - bucket["started_at"]) * 1000)
            bucket["first_response_ms"] = elapsed_ms

        breach = elapsed_ms > self._config.first_response_ms
        logger.info(
            "metrics.first_response",
            session_id=session_id,
            first_response_ms=elapsed_ms,
            threshold_ms=self._config.first_response_ms,
            breach=breach,
        )
        return elapsed_ms

    def record_narration(
        self, session_id: str, agent_id: str, delta_ms: int
    ) -> Dict[str, Any]:
        """Append a narration entry for ``session_id``.

        ``agent_id`` identifies the agent that produced the narration;
        ``delta_ms`` is the lag in milliseconds from the previous
        narration (or from session start for the first one).
        """
        if delta_ms < 0:
            raise ValueError("delta_ms must be non-negative")

        bucket = _get_or_create(session_id)
        entry = {"agent_id": agent_id, "delta_ms": int(delta_ms)}
        with _LOCK:
            bucket["narrations"].append(entry)

        breach = delta_ms > self._config.narration_lag_ms
        logger.info(
            "metrics.narration",
            session_id=session_id,
            agent_id=agent_id,
            delta_ms=delta_ms,
            threshold_ms=self._config.narration_lag_ms,
            breach=breach,
        )
        return entry

    def record_report(self, session_id: str, delta_ms: int) -> int:
        """Record the report-render latency for ``session_id``."""
        if delta_ms < 0:
            raise ValueError("delta_ms must be non-negative")

        bucket = _get_or_create(session_id)
        with _LOCK:
            bucket["report_ms"] = int(delta_ms)
            stored = bucket["report_ms"]

        breach = stored > self._config.report_render_ms
        logger.info(
            "metrics.report",
            session_id=session_id,
            report_ms=stored,
            threshold_ms=self._config.report_render_ms,
            breach=breach,
        )
        return stored

    # -- retrieval --------------------------------------------------------

    def get_session_metrics(self, session_id: str) -> Dict[str, Any]:
        """Return the raw metrics dict for ``session_id``.

        Shape::

            {
                "first_response_ms": int | None,
                "narrations": [{"agent_id": str, "delta_ms": int}, ...],
                "report_ms": int | None,
                "config": {...threshold dict...},
            }

        Unknown ``session_id`` returns an empty record (no values
        recorded yet) — this keeps the API contract uniform regardless
        of whether the session has started recording.
        """
        bucket = _SESSIONS.get(session_id)
        if bucket is None:
            return {
                "first_response_ms": None,
                "narrations": [],
                "report_ms": None,
                "config": self._config.to_dict(),
            }
        # Snapshot under the lock to avoid torn reads.
        with _LOCK:
            return {
                "first_response_ms": bucket["first_response_ms"],
                "narrations": list(bucket["narrations"]),
                "report_ms": bucket["report_ms"],
                "config": self._config.to_dict(),
            }

    def metrics_summary(self, session_id: str) -> Dict[str, Any]:
        """Return the API-ready summary for ``/api/engineer/metrics/{session_id}``.

        Extends ``get_session_metrics`` with computed ``breaches`` and
        aggregate counters that are useful for the dashboard.
        """
        metrics = self.get_session_metrics(session_id)
        cfg = metrics["config"]

        first_response_ms = metrics["first_response_ms"]
        report_ms = metrics["report_ms"]
        narrations = metrics["narrations"]

        breaches: Dict[str, bool] = {
            "first_response": (
                first_response_ms is not None
                and first_response_ms > cfg["first_response_ms"]
            ),
            "report": (
                report_ms is not None
                and report_ms > cfg["report_render_ms"]
            ),
            "narration": any(
                n["delta_ms"] > cfg["narration_lag_ms"] for n in narrations
            ),
        }

        return {
            **metrics,
            "session_id": session_id,
            "narration_count": len(narrations),
            "breaches": breaches,
        }


__all__ = [
    "MetricsConfig",
    "MetricsRecorder",
    "logger",
]
