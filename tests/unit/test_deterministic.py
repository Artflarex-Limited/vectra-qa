"""
Unit tests for DeterministicTester and playbook utilities.

Tests all 8 deterministic actions (visit, click, fill, assert, screenshot,
wait, scroll, hover) as well as YAML playbook parsing, error handling,
and edge cases.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, mock_open

from mcp_server.deterministic import (
    DeterministicTester,
    PlaybookResult,
    load_playbook,
    save_playbook,
    get_deterministic_tester,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_browser():
    """Create a mocked BrowserAutomation instance with async methods."""
    browser = MagicMock()
    browser.page = AsyncMock()
    browser.page.title = AsyncMock(return_value="Test Page")

    # Wire up async browser methods
    browser.visit = AsyncMock(
        return_value={"success": True, "final_url": "https://example.com", "error": ""}
    )
    browser.click = AsyncMock(
        return_value={"success": True, "selector": "#btn", "url": "https://example.com/page2"}
    )
    browser.fill = AsyncMock(return_value={"success": True, "selector": "#input", "text": "hello"})
    browser.get_elements = AsyncMock(
        return_value={"success": True, "selector": ".item", "count": 3}
    )
    browser.get_text = AsyncMock(
        return_value={"success": True, "selector": ".item", "text": "Hello World"}
    )
    browser.screenshot = AsyncMock(return_value={"success": True, "path": "/tmp/shot.png"})
    browser.scroll_to_bottom = AsyncMock(return_value={"success": True})
    browser.page.hover = AsyncMock(return_value=None)
    return browser


@pytest.fixture
def tester():
    """Create a fresh DeterministicTester for each test."""
    return DeterministicTester()


@pytest.fixture
def valid_playbook():
    """Return a minimal valid playbook."""
    return {
        "name": "test_playbook",
        "url": "https://example.com",
        "steps": [
            {"action": "visit", "url": "https://example.com"},
            {"action": "click", "selector": "#login-btn"},
            {"action": "fill", "selector": "#email", "value": "test@example.com"},
        ],
    }


# ---------------------------------------------------------------------------
# Action: visit
# ---------------------------------------------------------------------------


class TestActionVisit:
    """Test the visit action."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_visit_success(self, tester, mock_browser):
        """Should navigate to a URL successfully."""
        step = {"action": "visit", "url": "https://example.com"}
        result = await tester._execute_step(0, step, mock_browser)

        assert result.success is True
        assert result.action == "visit"
        mock_browser.visit.assert_awaited_once_with("https://example.com")

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_visit_missing_url(self, tester, mock_browser):
        """Should fail when no URL is specified."""
        step = {"action": "visit"}
        result = await tester._execute_step(0, step, mock_browser)

        assert result.success is False
        assert "No URL specified" in result.message
        mock_browser.visit.assert_not_awaited()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_visit_browser_error(self, tester, mock_browser):
        """Should propagate browser visit errors."""
        mock_browser.visit.return_value = {
            "success": False,
            "error": "Navigation timeout",
            "final_url": "https://example.com",
        }
        step = {"action": "visit", "url": "https://example.com"}
        result = await tester._execute_step(0, step, mock_browser)

        assert result.success is False
        assert "Navigation timeout" in result.message


# ---------------------------------------------------------------------------
# Action: click
# ---------------------------------------------------------------------------


class TestActionClick:
    """Test the click action."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_click_success(self, tester, mock_browser):
        """Should click an element successfully."""
        step = {"action": "click", "selector": "#submit-btn"}
        result = await tester._execute_step(0, step, mock_browser)

        assert result.success is True
        assert result.action == "click"
        mock_browser.click.assert_awaited_once_with("#submit-btn")

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_click_missing_selector(self, tester, mock_browser):
        """Should fail when no selector is specified."""
        step = {"action": "click"}
        result = await tester._execute_step(0, step, mock_browser)

        assert result.success is False
        assert "No selector specified" in result.message
        mock_browser.click.assert_not_awaited()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_click_browser_error(self, tester, mock_browser):
        """Should propagate browser click errors."""
        mock_browser.click.return_value = {
            "success": False,
            "error": "Element not found",
        }
        step = {"action": "click", "selector": "#missing"}
        result = await tester._execute_step(0, step, mock_browser)

        assert result.success is False
        assert "Element not found" in result.message


# ---------------------------------------------------------------------------
# Action: fill
# ---------------------------------------------------------------------------


class TestActionFill:
    """Test the fill action."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_fill_success(self, tester, mock_browser):
        """Should fill an input field successfully."""
        step = {"action": "fill", "selector": "#email", "value": "user@example.com"}
        result = await tester._execute_step(0, step, mock_browser)

        assert result.success is True
        assert result.action == "fill"
        mock_browser.fill.assert_awaited_once_with("#email", "user@example.com")

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_fill_missing_selector(self, tester, mock_browser):
        """Should fail when no selector is specified."""
        step = {"action": "fill", "value": "hello"}
        result = await tester._execute_step(0, step, mock_browser)

        assert result.success is False
        assert "No selector specified" in result.message
        mock_browser.fill.assert_not_awaited()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_fill_long_value_truncation(self, tester, mock_browser):
        """Should truncate long values in the success message."""
        long_value = "a" * 100
        step = {"action": "fill", "selector": "#field", "value": long_value}
        result = await tester._execute_step(0, step, mock_browser)

        assert result.success is True
        # Message should contain truncated value (not the full 100 chars)
        assert "..." in result.message
        assert len(result.message) < 120


# ---------------------------------------------------------------------------
# Action: assert
# ---------------------------------------------------------------------------


class TestActionAssert:
    """Test the assert action."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_assert_element_exists(self, tester, mock_browser):
        """Should pass when element exists."""
        step = {"action": "assert", "selector": ".item"}
        result = await tester._execute_step(0, step, mock_browser)

        assert result.success is True
        assert "Assertion passed" in result.message
        mock_browser.get_elements.assert_awaited_once_with(".item")

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_assert_element_not_found(self, tester, mock_browser):
        """Should fail when element does not exist."""
        mock_browser.get_elements.return_value = {"success": False, "count": 0}
        step = {"action": "assert", "selector": ".missing"}
        result = await tester._execute_step(0, step, mock_browser)

        assert result.success is False
        assert "Element not found" in result.message

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_assert_missing_selector(self, tester, mock_browser):
        """Should fail when no selector is specified."""
        step = {"action": "assert"}
        result = await tester._execute_step(0, step, mock_browser)

        assert result.success is False
        assert "No selector specified" in result.message

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_assert_text_match(self, tester, mock_browser):
        """Should pass when expected text is found."""
        step = {"action": "assert", "selector": ".item", "expected_text": "Hello"}
        result = await tester._execute_step(0, step, mock_browser)

        assert result.success is True
        mock_browser.get_text.assert_awaited_once_with(".item")

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_assert_text_mismatch(self, tester, mock_browser):
        """Should fail when expected text is not found."""
        mock_browser.get_text.return_value = {
            "success": True,
            "text": "Goodbye World",
        }
        step = {"action": "assert", "selector": ".item", "expected_text": "Hello"}
        result = await tester._execute_step(0, step, mock_browser)

        assert result.success is False
        assert "Expected text" in result.message

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_assert_count_match(self, tester, mock_browser):
        """Should pass when expected count matches."""
        step = {"action": "assert", "selector": ".item", "expected_count": 3}
        result = await tester._execute_step(0, step, mock_browser)

        assert result.success is True

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_assert_count_mismatch(self, tester, mock_browser):
        """Should fail when expected count does not match."""
        step = {"action": "assert", "selector": ".item", "expected_count": 5}
        result = await tester._execute_step(0, step, mock_browser)

        assert result.success is False
        assert "Expected 5 elements" in result.message


# ---------------------------------------------------------------------------
# Action: screenshot
# ---------------------------------------------------------------------------


class TestActionScreenshot:
    """Test the screenshot action."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_screenshot_success(self, tester, mock_browser):
        """Should take a screenshot successfully."""
        step = {"action": "screenshot", "path": "/tmp/test.png"}
        result = await tester._execute_step(0, step, mock_browser)

        assert result.success is True
        assert result.action == "screenshot"
        mock_browser.screenshot.assert_awaited_once_with("/tmp/test.png", full_page=True)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_screenshot_default_path(self, tester, mock_browser):
        """Should use default path when none specified."""
        step = {"action": "screenshot"}
        result = await tester._execute_step(0, step, mock_browser)

        assert result.success is True
        mock_browser.screenshot.assert_awaited_once_with("screenshot.png", full_page=True)


# ---------------------------------------------------------------------------
# Action: wait
# ---------------------------------------------------------------------------


class TestActionWait:
    """Test the wait action."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_wait_default_ms(self, tester, mock_browser):
        """Should wait with default 1000ms when ms is not specified."""
        with patch("asyncio.sleep", AsyncMock()) as mock_sleep:
            step = {"action": "wait"}
            result = await tester._execute_step(0, step, mock_browser)

            assert result.success is True
            assert "Waited 1000ms" in result.message
            mock_sleep.assert_awaited_once_with(1.0)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_wait_custom_ms(self, tester, mock_browser):
        """Should wait for the specified number of milliseconds."""
        with patch("asyncio.sleep", AsyncMock()) as mock_sleep:
            step = {"action": "wait", "ms": 500}
            result = await tester._execute_step(0, step, mock_browser)

            assert result.success is True
            assert "Waited 500ms" in result.message
            mock_sleep.assert_awaited_once_with(0.5)


# ---------------------------------------------------------------------------
# Action: scroll
# ---------------------------------------------------------------------------


class TestActionScroll:
    """Test the scroll action."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_scroll_bottom(self, tester, mock_browser):
        """Should scroll to bottom of the page."""
        step = {"action": "scroll", "direction": "bottom"}
        result = await tester._execute_step(0, step, mock_browser)

        assert result.success is True
        assert result.action == "scroll"
        mock_browser.scroll_to_bottom.assert_awaited_once()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_scroll_default_direction(self, tester, mock_browser):
        """Should default to scrolling to bottom when direction is omitted."""
        step = {"action": "scroll"}
        result = await tester._execute_step(0, step, mock_browser)

        assert result.success is True
        mock_browser.scroll_to_bottom.assert_awaited_once()


# ---------------------------------------------------------------------------
# Action: hover
# ---------------------------------------------------------------------------


class TestActionHover:
    """Test the hover action."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_hover_success(self, tester, mock_browser):
        """Should hover over an element successfully."""
        step = {"action": "hover", "selector": "#menu-item"}
        result = await tester._execute_step(0, step, mock_browser)

        assert result.success is True
        assert result.action == "hover"
        mock_browser.page.hover.assert_awaited_once_with("#menu-item")

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_hover_missing_selector(self, tester, mock_browser):
        """Should fail when no selector is specified."""
        step = {"action": "hover"}
        result = await tester._execute_step(0, step, mock_browser)

        assert result.success is False
        assert "No selector specified" in result.message
        mock_browser.page.hover.assert_not_awaited()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_hover_no_page(self, tester, mock_browser):
        """Should fail when browser page is not available."""
        mock_browser.page = None
        step = {"action": "hover", "selector": "#menu"}
        result = await tester._execute_step(0, step, mock_browser)

        assert result.success is False
        assert "Browser page not available" in result.message


# ---------------------------------------------------------------------------
# Unknown action & exception handling
# ---------------------------------------------------------------------------


class TestActionUnknown:
    """Test unknown action handling."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_unknown_action(self, tester, mock_browser):
        """Should return failure for unknown actions."""
        step = {"action": "dance"}
        result = await tester._execute_step(0, step, mock_browser)

        assert result.success is False
        assert "Unknown action: dance" in result.message


class TestExceptionHandling:
    """Test exception handling in step execution."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_step_raises_exception(self, tester, mock_browser):
        """Should catch exceptions and return failure PlaybookResult."""
        mock_browser.visit.side_effect = RuntimeError("Unexpected crash")
        step = {"action": "visit", "url": "https://example.com"}
        result = await tester._execute_step(0, step, mock_browser)

        assert result.success is False
        assert "Unexpected crash" in result.message


# ---------------------------------------------------------------------------
# Playbook execution flow
# ---------------------------------------------------------------------------


class TestPlaybookExecution:
    """Test full playbook execution."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_execute_full_playbook(self, tester, mock_browser, valid_playbook):
        """Should execute all steps in a playbook and return results."""
        results = await tester.execute_playbook(valid_playbook, mock_browser)

        assert len(results) == 3
        assert all(r.success for r in results)
        assert results[0].action == "visit"
        assert results[1].action == "click"
        assert results[2].action == "fill"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_required_step_failure_stops_execution(self, tester, mock_browser):
        """Should stop execution when a required step fails."""
        mock_browser.visit.side_effect = RuntimeError("Connection refused")
        playbook = {
            "name": "fail_fast",
            "steps": [
                {"action": "visit", "url": "https://example.com"},
                {"action": "click", "selector": "#btn"},
            ],
        }
        results = await tester.execute_playbook(playbook, mock_browser)

        assert len(results) == 1
        assert results[0].success is False

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_non_required_step_failure_continues(self, tester, mock_browser):
        """Should continue execution when a non-required step fails."""
        mock_browser.click.return_value = {"success": False, "error": "Not found"}
        playbook = {
            "name": "continue_on_fail",
            "steps": [
                {"action": "visit", "url": "https://example.com"},
                {"action": "click", "selector": "#missing", "required": False},
                {"action": "fill", "selector": "#email", "value": "a@b.com"},
            ],
        }
        results = await tester.execute_playbook(playbook, mock_browser)

        assert len(results) == 3
        assert results[0].success is True
        assert results[1].success is False
        assert results[2].success is True

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_empty_playbook(self, tester, mock_browser):
        """Should handle playbook with no steps gracefully."""
        playbook = {"name": "empty", "steps": []}
        results = await tester.execute_playbook(playbook, mock_browser)

        assert results == []

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_playbook_without_steps_key(self, tester, mock_browser):
        """Should handle playbook without steps key gracefully."""
        playbook = {"name": "no_steps"}
        results = await tester.execute_playbook(playbook, mock_browser)

        assert results == []

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_step_with_extra_params(self, tester, mock_browser):
        """Should ignore extra parameters in a step."""
        step = {
            "action": "click",
            "selector": "#btn",
            "extra_param": "should_be_ignored",
            "another_extra": 42,
        }
        result = await tester._execute_step(0, step, mock_browser)

        assert result.success is True
        assert result.action == "click"
        mock_browser.click.assert_awaited_once_with("#btn")

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_playbook_result_has_duration(self, tester, mock_browser, valid_playbook):
        """Each step result should have a non-negative duration."""
        results = await tester.execute_playbook(valid_playbook, mock_browser)

        for r in results:
            assert r.duration_seconds >= 0


# ---------------------------------------------------------------------------
# YAML playbook I/O
# ---------------------------------------------------------------------------


class TestPlaybookIO:
    """Test load_playbook and save_playbook functions."""

    @pytest.mark.unit
    def test_load_playbook_valid_yaml(self):
        """Should load a valid YAML playbook."""
        yaml_content = """
        name: login_test
        url: https://example.com/login
        steps:
          - action: visit
            url: https://example.com/login
          - action: fill
            selector: "#username"
            value: admin
        """
        with patch("builtins.open", mock_open(read_data=yaml_content)):
            playbook = load_playbook("/fake/path.yaml")

        assert playbook["name"] == "login_test"
        assert len(playbook["steps"]) == 2

    @pytest.mark.unit
    def test_load_playbook_empty_yaml(self):
        """Should return empty dict for empty YAML."""
        with patch("builtins.open", mock_open(read_data="")):
            playbook = load_playbook("/fake/empty.yaml")

        assert playbook == {}

    @pytest.mark.unit
    def test_load_playbook_file_not_found(self):
        """Should propagate FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_playbook("/nonexistent/path.yaml")

    @pytest.mark.unit
    def test_save_playbook(self):
        """Should save a playbook as valid YAML."""
        playbook = {"name": "test", "steps": [{"action": "click", "selector": "#btn"}]}

        mock_file = mock_open()
        with patch("builtins.open", mock_file):
            save_playbook(playbook, "/fake/output.yaml")

        mock_file.assert_called_once_with("/fake/output.yaml", "w", encoding="utf-8")

    @pytest.mark.unit
    def test_save_and_load_roundtrip(self, tmp_path):
        """Should save and load a playbook without data loss."""
        playbook = {
            "name": "roundtrip",
            "url": "https://example.com",
            "steps": [
                {"action": "visit", "url": "https://example.com"},
                {"action": "click", "selector": "#btn"},
            ],
        }

        file_path = tmp_path / "test_playbook.yaml"
        save_playbook(playbook, str(file_path))

        loaded = load_playbook(str(file_path))

        assert loaded["name"] == playbook["name"]
        assert len(loaded["steps"]) == len(playbook["steps"])


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------


class TestSingleton:
    """Test the get_deterministic_tester singleton."""

    @pytest.mark.unit
    def test_singleton_returns_same_instance(self):
        """Should return the same instance on repeated calls."""
        # Reset the singleton for test isolation
        import mcp_server.deterministic as det_mod

        det_mod._tester = None

        t1 = get_deterministic_tester()
        t2 = get_deterministic_tester()

        assert t1 is t2
        assert isinstance(t1, DeterministicTester)

    @pytest.mark.unit
    def test_singleton_is_independent(self):
        """Singleton instances should not share state via results."""
        import mcp_server.deterministic as det_mod

        det_mod._tester = None

        t1 = get_deterministic_tester()
        t1.results = [PlaybookResult(0, "click", True)]

        t2 = get_deterministic_tester()
        # Both point to the same object
        assert t2.results == [PlaybookResult(0, "click", True)]
        assert len(t2.results) == 1
