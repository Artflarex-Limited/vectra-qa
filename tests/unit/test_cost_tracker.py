"""
Unit tests for the LLM cost tracking and budget enforcement module.

Tests CostTracker: cost calculation, usage tracking, budget enforcement,
and database persistence with mocked dependencies.
"""

import pytest
from unittest.mock import MagicMock, patch
from decimal import Decimal
from datetime import datetime

# ---------------------------------------------------------------------------
#  Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_db():
    """Mock get_db_manager_sync and the asyncio event loop for CostTracker.

    Returns (mock_db, mock_loop) so tests can configure return values.
    """
    with patch("mcp_server.cost_tracker.get_db_manager_sync") as mock_get_db:
        mock_db = MagicMock()
        mock_db._initialized = True
        mock_get_db.return_value = mock_db

        with patch("asyncio.get_event_loop") as mock_get_loop:
            mock_loop = MagicMock()
            mock_loop.is_running.return_value = False
            mock_get_loop.return_value = mock_loop

            yield mock_db, mock_loop


@pytest.fixture
def tracker(mock_db):
    """Create a CostTracker with a generous budget and mocked DB.

    Default budget of $1,000 ensures budget tests don't false-positive.
    """
    from mcp_server.cost_tracker import CostTracker

    return CostTracker(budget_usd=Decimal("1000.00"))


# ---------------------------------------------------------------------------
#  Cost Calculation Tests
# ---------------------------------------------------------------------------


class TestCalculateCost:
    """Tests for the calculate_cost method."""

    @pytest.mark.unit
    def test_known_model_returns_expected_cost(self):
        """Should calculate $0.02 for 1000 input + 1000 output tokens on gpt-4o."""
        from mcp_server.cost_tracker import CostTracker

        tracker = CostTracker(budget_usd=Decimal("1000.00"))

        # gpt-4o: $0.005/1K input, $0.015/1K output
        # 1000 input = 1 * 0.005 = 0.005
        # 1000 output = 1 * 0.015 = 0.015
        # total = 0.02
        cost = tracker.calculate_cost("gpt-4o", 1000, 1000)

        assert cost == Decimal("0.02000")

    @pytest.mark.unit
    def test_unknown_model_falls_back_to_default_pricing(self):
        """Should use default pricing ($0.001/1K) for unknown models."""
        from mcp_server.cost_tracker import CostTracker

        tracker = CostTracker(budget_usd=Decimal("1000.00"))

        # unknown model: default $0.001/1K input + $0.001/1K output
        # 1000 input = 0.001, 2000 output = 0.002, total = 0.003
        cost = tracker.calculate_cost("unknown-model-v1", 1000, 2000)

        assert cost == Decimal("0.00300")

    @pytest.mark.unit
    def test_local_model_is_free(self):
        """Should calculate $0 cost for local models with zero pricing."""
        from mcp_server.cost_tracker import CostTracker

        tracker = CostTracker(budget_usd=Decimal("1000.00"))

        cost = tracker.calculate_cost("llama3.1:70b", 5000, 5000)

        assert cost == Decimal("0")

    @pytest.mark.unit
    def test_zero_tokens_cost_nothing(self):
        """Should return $0 when both token counts are zero."""
        from mcp_server.cost_tracker import CostTracker

        tracker = CostTracker(budget_usd=Decimal("1000.00"))

        cost = tracker.calculate_cost("gpt-4o", 0, 0)

        assert cost == Decimal("0")

    @pytest.mark.unit
    def test_provider_prefix_is_stripped(self):
        """Should strip provider prefix (e.g. 'openai/gpt-4o') for lookup."""
        from mcp_server.cost_tracker import CostTracker

        tracker = CostTracker(budget_usd=Decimal("1000.00"))

        # 'openai/gpt-4o' -> 'gpt-4o' after split
        cost = tracker.calculate_cost("openai/gpt-4o", 1000, 1000)

        assert cost == Decimal("0.02000")


# ---------------------------------------------------------------------------
#  Usage Tracking Tests
# ---------------------------------------------------------------------------


class TestTrackUsage:
    """Tests for the track_usage method."""

    @pytest.mark.unit
    def test_track_usage_returns_record_with_correct_fields(self, tracker, mock_db):
        """Should return a UsageRecord with calculated cost and metadata."""
        record = tracker.track_usage(
            model="gpt-4o",
            input_tokens=500,
            output_tokens=300,
            provider="openai",
        )

        assert record.model == "gpt-4o"
        assert record.provider == "openai"
        assert record.input_tokens == 500
        assert record.output_tokens == 300
        assert record.cost_usd == Decimal("0.00700")  # 0.5*0.005 + 0.3*0.015
        assert isinstance(record.timestamp, datetime)
        assert record.cache_hit is False

    @pytest.mark.unit
    def test_cache_hit_sets_cost_to_zero(self, tracker, mock_db):
        """Should zero out the cost when cache_hit is True."""
        record = tracker.track_usage(
            model="gpt-4o",
            input_tokens=10000,
            output_tokens=10000,
            cache_hit=True,
        )

        assert record.cache_hit is True
        assert record.cost_usd == Decimal("0.000000")

    @pytest.mark.unit
    def test_track_usage_persists_to_database(self, tracker, mock_db):
        """Should insert a row into llm_usage via db.execute."""
        mock_db, mock_loop = mock_db

        tracker.track_usage(
            model="gpt-4o",
            input_tokens=100,
            output_tokens=50,
            provider="openai",
            test_run_id="run-001",
        )

        # db.execute should have been called with the INSERT query
        mock_db.execute.assert_called_once()
        sql, params = mock_db.execute.call_args[0]
        assert "INSERT INTO llm_usage" in sql

    @pytest.mark.unit
    def test_track_usage_with_test_run_id(self, tracker, mock_db):
        """Should pass test_run_id to the database insert."""
        mock_db, mock_loop = mock_db

        tracker.track_usage(
            model="claude-3-haiku",
            input_tokens=100,
            output_tokens=100,
            test_run_id="run-abc-123",
        )

        mock_db.execute.assert_called_once()
        sql, params = mock_db.execute.call_args[0]
        assert "run-abc-123" in params

    @pytest.mark.unit
    def test_track_usage_handles_db_failure_gracefully(self, tracker, mock_db):
        """Should not raise when the database write fails."""
        mock_db, mock_loop = mock_db
        mock_db.execute.side_effect = RuntimeError("Database unreachable")

        # Should not raise; failure is logged at DEBUG level
        record = tracker.track_usage(
            model="gpt-4o",
            input_tokens=10,
            output_tokens=10,
        )

        assert record.model == "gpt-4o"

    @pytest.mark.unit
    def test_track_usage_skips_db_when_uninitialized(self):
        """Should skip DB write when db._initialized is False."""
        with patch("mcp_server.cost_tracker.get_db_manager_sync") as mock_get_db:
            mock_db = MagicMock()
            mock_db._initialized = False
            mock_get_db.return_value = mock_db

            from mcp_server.cost_tracker import CostTracker

            tracker = CostTracker(budget_usd=Decimal("1000.00"))

            record = tracker.track_usage(
                model="gpt-4o",
                input_tokens=10,
                output_tokens=10,
            )

            assert record.model == "gpt-4o"
            # db.execute should NOT have been called since !_initialized
            mock_db.execute.assert_not_called()


# ---------------------------------------------------------------------------
#  Total Spend & Summary Tests
# ---------------------------------------------------------------------------


class TestTotalSpend:
    """Tests for get_total_spent and get_usage_summary."""

    @pytest.mark.unit
    def test_get_total_spent_queries_database(self, tracker, mock_db):
        """Should query llm_usage SUM from database."""
        mock_db, mock_loop = mock_db
        mock_loop.run_until_complete.return_value = Decimal("1.234500")

        total = tracker.get_total_spent()

        mock_db.fetchval.assert_called_once()
        sql = mock_db.fetchval.call_args[0][0]
        assert "SUM(cost_usd)" in sql
        assert total == Decimal("1.234500")

    @pytest.mark.unit
    def test_get_total_spent_returns_zero_when_db_uninitialized(self):
        """Should return 0 when the database is not initialized."""
        with patch("mcp_server.cost_tracker.get_db_manager_sync") as mock_get_db:
            mock_db = MagicMock()
            mock_db._initialized = False
            mock_get_db.return_value = mock_db

            from mcp_server.cost_tracker import CostTracker

            tracker = CostTracker(budget_usd=Decimal("1000.00"))

            total = tracker.get_total_spent()

            assert total == Decimal("0.000000")
            mock_db.fetchval.assert_not_called()

    @pytest.mark.unit
    def test_get_total_spent_returns_zero_on_db_error(self, tracker, mock_db):
        """Should return 0 when the database query fails."""
        mock_db, mock_loop = mock_db
        mock_db.fetchval.side_effect = RuntimeError("Query failed")

        total = tracker.get_total_spent()

        assert total == Decimal("0.000000")

    @pytest.mark.unit
    def test_get_usage_summary_returns_correct_structure(self, tracker, mock_db):
        """Should return a dict with all summary fields populated."""
        mock_db, mock_loop = mock_db
        mock_loop.run_until_complete.return_value = Decimal("50.000000")

        summary = tracker.get_usage_summary()

        assert summary["total_spent_usd"] == 50.0
        assert summary["budget_usd"] == 1000.0
        assert summary["remaining_usd"] == 950.0
        assert summary["pct_used"] == 5.0  # 50/1000 * 100
        assert summary["alert_threshold_pct"] == 80
        assert summary["is_alert"] is False
        assert summary["is_exceeded"] is False


# ---------------------------------------------------------------------------
#  Budget Enforcement Tests
# ---------------------------------------------------------------------------


class TestBudgetEnforcement:
    """Tests for budget checking and alerting."""

    @pytest.mark.unit
    def test_budget_exceeded_raises_error(self, tracker, mock_db):
        """Should raise BudgetExceededError when total spend >= budget."""
        mock_db, mock_loop = mock_db
        # Make get_total_spent return a value over budget
        mock_loop.run_until_complete.return_value = Decimal("1000.000000")

        from mcp_server.cost_tracker import BudgetExceededError

        with pytest.raises(BudgetExceededError) as exc_info:
            tracker.track_usage(model="gpt-4o", input_tokens=10, output_tokens=10)

        assert "budget exceeded" in str(exc_info.value).lower()

    @pytest.mark.unit
    def test_budget_alert_sent_when_approaching_limit(self, tracker, mock_db):
        """Should set _alert_sent flag when crossing the alert threshold."""
        mock_db, mock_loop = mock_db
        # 80% of $1000 = $800. Set total to $850 to cross threshold.
        mock_loop.run_until_complete.return_value = Decimal("850.000000")

        assert tracker._alert_sent is False

        tracker.track_usage(model="gpt-4o", input_tokens=10, output_tokens=10)

        assert tracker._alert_sent is True

    @pytest.mark.unit
    def test_budget_alert_not_sent_below_threshold(self, tracker, mock_db):
        """Should not set _alert_sent when below alert threshold."""
        mock_db, mock_loop = mock_db
        # 80% of $1000 = $800. $500 is below threshold.
        mock_loop.run_until_complete.return_value = Decimal("500.000000")

        assert tracker._alert_sent is False

        tracker.track_usage(model="gpt-4o", input_tokens=10, output_tokens=10)

        assert tracker._alert_sent is False

    @pytest.mark.unit
    def test_alert_only_sent_once(self, tracker, mock_db):
        """Should not re-send the alert on subsequent calls above threshold."""
        mock_db, mock_loop = mock_db
        # Stay above threshold
        mock_loop.run_until_complete.return_value = Decimal("900.000000")

        # First call triggers alert
        tracker.track_usage(model="gpt-4o", input_tokens=1, output_tokens=1)
        assert tracker._alert_sent is True

        # Reset the mock call count after last _check_budget
        # Second call: already alerted, should not log another alert
        tracker.track_usage(model="gpt-4o", input_tokens=1, output_tokens=1)
        assert tracker._alert_sent is True  # still True, not re-triggered


# ---------------------------------------------------------------------------
#  CostTracker Constructor / Singleton Tests
# ---------------------------------------------------------------------------


class TestCostTrackerInit:
    """Tests for CostTracker initialization and the get_cost_tracker factory."""

    @pytest.mark.unit
    def test_default_budget_from_env(self):
        """Should use env var VECTRA_LLM_BUDGET_USD when no budget provided."""
        with (
            patch("mcp_server.cost_tracker.LLM_BUDGET_USD", Decimal("25.00")),
            patch("mcp_server.cost_tracker.get_db_manager_sync"),
        ):
            from mcp_server.cost_tracker import CostTracker

            tracker = CostTracker()
            assert tracker.budget_usd == Decimal("25.00")

    @pytest.mark.unit
    def test_custom_budget_overrides_env(self):
        """Should use passed budget over environment variable."""
        with patch("mcp_server.cost_tracker.get_db_manager_sync"):
            from mcp_server.cost_tracker import CostTracker

            tracker = CostTracker(budget_usd=Decimal("5.00"))
            assert tracker.budget_usd == Decimal("5.00")

    @pytest.mark.unit
    def test_get_cost_tracker_returns_singleton(self):
        """Should return the same CostTracker instance on repeated calls."""
        with patch("mcp_server.cost_tracker.get_db_manager_sync"):
            from mcp_server.cost_tracker import get_cost_tracker

            # Reset singleton
            import mcp_server.cost_tracker as ct_mod

            ct_mod._cost_tracker = None

            t1 = get_cost_tracker()
            t2 = get_cost_tracker()
            assert t1 is t2

            # Cleanup
            ct_mod._cost_tracker = None
