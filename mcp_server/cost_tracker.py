"""
Cost tracking and budget enforcement for Vectra QA LLM usage.

Tracks per-call costs, enforces budget limits, provides real-time spend visibility.

Usage:
    from mcp_server.cost_tracker import CostTracker

    tracker = CostTracker()
    tracker.track_usage(model="gpt-4o", input_tokens=1000, output_tokens=500)
    if tracker.is_budget_exceeded():
        raise BudgetExceededError("LLM budget exhausted")
"""

import os
from typing import Any, Dict, Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

import structlog

from mcp_server.db import get_db_manager_sync

logger = structlog.get_logger()

# Configuration
LLM_BUDGET_USD = Decimal(os.getenv("VECTRA_LLM_BUDGET_USD", "50.00"))
LLM_BUDGET_ALERT_PCT = Decimal(os.getenv("VECTRA_LLM_BUDGET_ALERT_PCT", "80"))

# Pricing per 1K tokens (input, output)
MODEL_PRICING: Dict[str, Dict[str, Decimal]] = {
    "gpt-4o": {"input": Decimal("0.00500"), "output": Decimal("0.01500")},
    "gpt-4o-mini": {"input": Decimal("0.00015"), "output": Decimal("0.00060")},
    "claude-3-5-sonnet-20241022": {"input": Decimal("0.00300"), "output": Decimal("0.01500")},
    "claude-3-haiku": {"input": Decimal("0.00025"), "output": Decimal("0.00125")},
    "minimax-text-01": {"input": Decimal("0.00050"), "output": Decimal("0.00050")},
    "kimi-k2": {"input": Decimal("0.00100"), "output": Decimal("0.00100")},
    "llama3.1:70b": {"input": Decimal("0.00000"), "output": Decimal("0.00000")},  # Local = free
}


@dataclass
class UsageRecord:
    """Single LLM usage record."""

    model: str
    provider: str
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    cache_hit: bool = False


class BudgetExceededError(Exception):
    """Raised when LLM budget is exceeded."""

    pass


class CostTracker:
    """Tracks LLM usage costs and enforces budget limits."""

    def __init__(self, budget_usd: Optional[Decimal] = None):
        self.budget_usd = budget_usd or LLM_BUDGET_USD
        self.alert_threshold = self.budget_usd * (LLM_BUDGET_ALERT_PCT / Decimal("100"))
        self._alert_sent = False
        self.db = get_db_manager_sync()

    def calculate_cost(self, model: str, input_tokens: int, output_tokens: int) -> Decimal:
        """Calculate cost for a given model and token usage."""
        # Normalize model name
        model_key = model.split("/")[-1]  # Remove provider prefix
        pricing = MODEL_PRICING.get(
            model_key, {"input": Decimal("0.001"), "output": Decimal("0.001")}
        )

        input_cost = Decimal(input_tokens) / 1000 * pricing["input"]
        output_cost = Decimal(output_tokens) / 1000 * pricing["output"]

        return input_cost + output_cost

    def track_usage(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        provider: str = "unknown",
        cache_hit: bool = False,
        test_run_id: Optional[str] = None,
    ) -> UsageRecord:
        """
        Track LLM usage and persist to database.

        Returns:
            UsageRecord with calculated cost
        """
        cost = self.calculate_cost(model, input_tokens, output_tokens)
        if cache_hit:
            cost = Decimal("0.000000")  # Cache hits are free

        record = UsageRecord(
            model=model,
            provider=provider,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            cache_hit=cache_hit,
        )

        # Persist to database
        if self.db._initialized:
            import asyncio

            try:
                loop = asyncio.get_event_loop()
                if not loop.is_running():
                    loop.run_until_complete(
                        self.db.execute(
                            """
                            INSERT INTO llm_usage (model, provider, input_tokens, output_tokens, cost_usd, test_run_id, cache_hit)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                            """,
                            (
                                model,
                                provider,
                                input_tokens,
                                output_tokens,
                                cost,
                                test_run_id,
                                cache_hit,
                            ),
                        )
                    )
            except Exception as e:
                logger.debug("cost_tracking_db_failed", error=str(e))

        # Check budget
        self._check_budget()

        logger.debug(
            "llm_usage_tracked",
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=float(cost),
            cache_hit=cache_hit,
        )

        return record

    def _check_budget(self):
        """Check if budget is approaching or exceeded."""
        total_spent = self.get_total_spent()

        if total_spent >= self.budget_usd:
            logger.error(
                "budget_exceeded",
                total_spent=float(total_spent),
                budget=float(self.budget_usd),
            )
            raise BudgetExceededError(
                f"LLM budget exceeded: ${total_spent:.4f} / ${self.budget_usd:.2f}"
            )

        if total_spent >= self.alert_threshold and not self._alert_sent:
            logger.warning(
                "budget_alert",
                total_spent=float(total_spent),
                budget=float(self.budget_usd),
                threshold_pct=float(LLM_BUDGET_ALERT_PCT),
            )
            self._alert_sent = True

    def get_total_spent(self) -> Decimal:
        """Get total LLM spend from database."""
        if not self.db._initialized:
            return Decimal("0.000000")

        import asyncio

        try:
            loop = asyncio.get_event_loop()
            if not loop.is_running():
                result = loop.run_until_complete(
                    self.db.fetchval("SELECT COALESCE(SUM(cost_usd), 0) FROM llm_usage")
                )
                return Decimal(str(result)) if result else Decimal("0.000000")
        except Exception as e:
            logger.warning("cost_query_failed", error=str(e))

        return Decimal("0.000000")

    def get_usage_summary(self, test_run_id: Optional[str] = None) -> Dict[str, Any]:
        """Get usage summary for dashboard display."""
        total = self.get_total_spent()
        remaining = self.budget_usd - total
        pct_used = (total / self.budget_usd * 100) if self.budget_usd > 0 else Decimal("0")

        return {
            "total_spent_usd": float(total),
            "budget_usd": float(self.budget_usd),
            "remaining_usd": float(max(Decimal("0"), remaining)),
            "pct_used": float(pct_used),
            "alert_threshold_pct": float(LLM_BUDGET_ALERT_PCT),
            "is_alert": total >= self.alert_threshold,
            "is_exceeded": total >= self.budget_usd,
        }


# Global singleton
_cost_tracker: Optional[CostTracker] = None


def get_cost_tracker() -> CostTracker:
    """Get or create the CostTracker singleton."""
    global _cost_tracker
    if _cost_tracker is None:
        _cost_tracker = CostTracker()
    return _cost_tracker
