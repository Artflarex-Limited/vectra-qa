"""
Extended unit tests for BrowserAutomation.

Covers previously untested methods and error handling paths
to push browser_tools.py coverage to 80%+.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch

from mcp_server.browser_tools import BrowserAutomation


# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────


@pytest.fixture
def browser():
    """Create a BrowserAutomation instance."""
    return BrowserAutomation(headless=True)


@pytest.fixture
def browser_with_page():
    """Create browser with mocked page."""
    browser = BrowserAutomation(headless=True)
    browser.page = AsyncMock()
    browser.page.url = "https://example.com"
    return browser


# ──────────────────────────────────────────────
# Browser Start Options
# ──────────────────────────────────────────────


class TestBrowserStartOptions:
    """Test browser launch options."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_start_with_slow_mo(self, browser):
        """Should pass slow_mo to launch options when > 0."""
        browser.slow_mo = 100

        mock_playwright = AsyncMock()
        mock_browser = AsyncMock()
        mock_context = AsyncMock()
        mock_page = AsyncMock()
        mock_page.on = Mock()

        mock_playwright.start.return_value = mock_playwright
        mock_playwright.chromium.launch.return_value = mock_browser
        mock_browser.new_context.return_value = mock_context
        mock_context.new_page.return_value = mock_page

        with patch("mcp_server.browser_tools.async_playwright", return_value=mock_playwright):
            await browser.start()

        mock_playwright.chromium.launch.assert_called_once_with(
            headless=True, slow_mo=100
        )


# ──────────────────────────────────────────────
# Event Handlers
# ──────────────────────────────────────────────


class TestEventHandlers:
    """Test console, page error, and response event handlers."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_handle_console_captures_log(self, browser):
        """Should append console messages to console_logs."""
        mock_msg = Mock()
        mock_msg.type = "log"
        mock_msg.text = "hello world"

        await browser._handle_console(mock_msg)

        assert len(browser.console_logs) == 1
        assert browser.console_logs[0]["type"] == "log"
        assert browser.console_logs[0]["text"] == "hello world"
        assert "time" in browser.console_logs[0]

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_handle_page_error_captures_error(self, browser):
        """Should append page errors to errors list."""
        error = RuntimeError("Page crashed")

        await browser._handle_page_error(error)

        assert len(browser.errors) == 1
        assert "Page crashed" in browser.errors[0]

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_handle_response_captures_network(self, browser):
        """Should append network responses to network_logs."""
        mock_response = Mock()
        mock_response.url = "https://example.com/api"
        mock_response.status = 200

        await browser._handle_response(mock_response)

        assert len(browser.network_logs) == 1
        assert browser.network_logs[0]["url"] == "https://example.com/api"
        assert browser.network_logs[0]["status"] == 200
        assert "time" in browser.network_logs[0]


# ──────────────────────────────────────────────
# visit
# ──────────────────────────────────────────────


class TestVisitErrors:
    """Test visit error handling."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_visit_not_started(self, browser):
        """Should raise RuntimeError when page is not started."""
        with pytest.raises(RuntimeError, match="Browser not started"):
            await browser.visit("https://example.com")


# ──────────────────────────────────────────────
# click
# ──────────────────────────────────────────────


class TestClickErrors:
    """Test click error handling."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_click_not_started(self, browser):
        """Should return error when page is not started."""
        result = await browser.click("#btn")

        assert result["success"] is False
        assert "Browser not started" in result["error"]

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_click_exception(self, browser_with_page):
        """Should handle click exceptions gracefully."""
        browser_with_page.page.click.side_effect = Exception("Element not clickable")

        result = await browser_with_page.click("#btn")

        assert result["success"] is False
        assert "Element not clickable" in result["error"]


# ──────────────────────────────────────────────
# fill
# ──────────────────────────────────────────────


class TestFillErrors:
    """Test fill error handling."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_fill_not_started(self, browser):
        """Should return error when page is not started."""
        result = await browser.fill("#input", "text")

        assert result["success"] is False
        assert "Browser not started" in result["error"]

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_fill_exception(self, browser_with_page):
        """Should handle fill exceptions gracefully."""
        browser_with_page.page.fill.side_effect = Exception("Cannot fill")

        result = await browser_with_page.fill("#input", "text")

        assert result["success"] is False
        assert "Cannot fill" in result["error"]


# ──────────────────────────────────────────────
# get_text
# ──────────────────────────────────────────────


class TestGetTextErrors:
    """Test get_text error handling."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_text_not_started(self, browser):
        """Should return error when page is not started."""
        result = await browser.get_text("#title")

        assert result["success"] is False
        assert "Browser not started" in result["error"]

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_text_element_not_found(self, browser_with_page):
        """Should return error when element is not found."""
        browser_with_page.page.query_selector.return_value = None

        result = await browser_with_page.get_text("#title")

        assert result["success"] is False
        assert "Element not found" in result["error"]

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_text_exception(self, browser_with_page):
        """Should handle query_selector exceptions gracefully."""
        browser_with_page.page.query_selector.side_effect = Exception("Selector invalid")

        result = await browser_with_page.get_text("#title")

        assert result["success"] is False
        assert "Selector invalid" in result["error"]


# ──────────────────────────────────────────────
# get_elements
# ──────────────────────────────────────────────


class TestGetElementsErrors:
    """Test get_elements error handling."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_elements_not_started(self, browser):
        """Should return error when page is not started."""
        result = await browser.get_elements(".card")

        assert result["success"] is False
        assert "Browser not started" in result["error"]

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_elements_exception(self, browser_with_page):
        """Should handle query_selector_all exceptions gracefully."""
        browser_with_page.page.query_selector_all.side_effect = Exception("Invalid selector")

        result = await browser_with_page.get_elements(".card")

        assert result["success"] is False
        assert "Invalid selector" in result["error"]


# ──────────────────────────────────────────────
# screenshot
# ──────────────────────────────────────────────


class TestScreenshotErrors:
    """Test screenshot error handling."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_screenshot_not_started(self, browser):
        """Should return error when page is not started."""
        result = await browser.screenshot("/tmp/test.png")

        assert result["success"] is False
        assert "Browser not started" in result["error"]

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_screenshot_exception(self, browser_with_page):
        """Should handle screenshot exceptions gracefully."""
        browser_with_page.page.screenshot.side_effect = Exception("Screenshot failed")

        result = await browser_with_page.screenshot("/tmp/test.png")

        assert result["success"] is False
        assert "Screenshot failed" in result["error"]


# ──────────────────────────────────────────────
# scroll_to_bottom
# ──────────────────────────────────────────────


class TestScrollToBottom:
    """Test scroll_to_bottom method."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_scroll_to_bottom_success(self, browser_with_page):
        """Should scroll to bottom successfully."""
        result = await browser_with_page.scroll_to_bottom()

        assert result["success"] is True
        browser_with_page.page.evaluate.assert_called_once_with(
            "window.scrollTo(0, document.body.scrollHeight)"
        )

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_scroll_to_bottom_not_started(self, browser):
        """Should return error when page is not started."""
        result = await browser.scroll_to_bottom()

        assert result["success"] is False
        assert "Browser not started" in result["error"]

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_scroll_to_bottom_exception(self, browser_with_page):
        """Should handle scroll exceptions gracefully."""
        browser_with_page.page.evaluate.side_effect = Exception("Scroll failed")

        result = await browser_with_page.scroll_to_bottom()

        assert result["success"] is False
        assert "Scroll failed" in result["error"]


# ──────────────────────────────────────────────
# check_responsive
# ──────────────────────────────────────────────


class TestCheckResponsive:
    """Test check_responsive method."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_check_responsive_success(self, browser_with_page):
        """Should set viewport size and return success."""
        result = await browser_with_page.check_responsive(375, 667)

        assert result["success"] is True
        assert result["viewport"] == "375x667"
        browser_with_page.page.set_viewport_size.assert_called_once_with(
            {"width": 375, "height": 667}
        )

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_check_responsive_not_started(self, browser):
        """Should return error when page is not started."""
        result = await browser.check_responsive(375, 667)

        assert result["success"] is False
        assert "Browser not started" in result["error"]

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_check_responsive_exception(self, browser_with_page):
        """Should handle viewport exceptions gracefully."""
        browser_with_page.page.set_viewport_size.side_effect = Exception("Viewport error")

        result = await browser_with_page.check_responsive(375, 667)

        assert result["success"] is False
        assert "Viewport error" in result["error"]


# ──────────────────────────────────────────────
# get_all_links
# ──────────────────────────────────────────────


class TestGetAllLinks:
    """Test get_all_links method."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_all_links_success(self, browser_with_page):
        """Should extract all visible links."""
        mock_link1 = AsyncMock()
        mock_link1.get_attribute.return_value = "https://example.com"
        mock_link1.text_content.return_value = "Example"
        mock_link1.is_visible.return_value = True

        mock_link2 = AsyncMock()
        mock_link2.get_attribute.return_value = "/about"
        mock_link2.text_content.return_value = "About Us"
        mock_link2.is_visible.return_value = False

        browser_with_page.page.query_selector_all.return_value = [mock_link1, mock_link2]

        result = await browser_with_page.get_all_links()

        assert result["success"] is True
        assert result["count"] == 2
        assert result["links"][0]["href"] == "https://example.com"
        assert result["links"][0]["visible"] is True
        assert result["links"][1]["href"] == "/about"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_all_links_skips_empty_href(self, browser_with_page):
        """Should skip links without href."""
        mock_link = AsyncMock()
        mock_link.get_attribute.return_value = None
        mock_link.text_content.return_value = "No href"

        browser_with_page.page.query_selector_all.return_value = [mock_link]

        result = await browser_with_page.get_all_links()

        assert result["success"] is True
        assert result["count"] == 0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_all_links_not_started(self, browser):
        """Should return error when page is not started."""
        result = await browser.get_all_links()

        assert result["success"] is False
        assert "Browser not started" in result["error"]

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_all_links_exception(self, browser_with_page):
        """Should handle query_selector_all exceptions gracefully."""
        browser_with_page.page.query_selector_all.side_effect = Exception("Query failed")

        result = await browser_with_page.get_all_links()

        assert result["success"] is False
        assert "Query failed" in result["error"]


# ──────────────────────────────────────────────
# check_form
# ──────────────────────────────────────────────


class TestCheckForm:
    """Test check_form method."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_check_form_not_started(self, browser):
        """Should return error when page is not started."""
        result = await browser.check_form("form")

        assert result["success"] is False
        assert "Browser not started" in result["error"]

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_check_form_not_found(self, browser_with_page):
        """Should return error when form is not found."""
        browser_with_page.page.query_selector.return_value = None

        result = await browser_with_page.check_form("#missing-form")

        assert result["success"] is False
        assert "Form not found" in result["error"]

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_check_form_exception(self, browser_with_page):
        """Should handle form query exceptions gracefully."""
        browser_with_page.page.query_selector.side_effect = Exception("Form query error")

        result = await browser_with_page.check_form("form")

        assert result["success"] is False
        assert "Form query error" in result["error"]


# ──────────────────────────────────────────────
# close
# ──────────────────────────────────────────────


class TestCloseEdgeCases:
    """Test close edge cases."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_close_when_none(self, browser):
        """Should not raise when browser and playwright are None."""
        browser.browser = None
        browser.playwright = None

        await browser.close()

        # Should not raise

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_close_browser_only(self, browser):
        """Should close browser even when playwright is None."""
        mock_browser = AsyncMock()
        browser.browser = mock_browser
        browser.playwright = None

        await browser.close()

        mock_browser.close.assert_called_once()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_close_playwright_only(self, browser):
        """Should stop playwright even when browser is None."""
        mock_playwright = AsyncMock()
        browser.browser = None
        browser.playwright = mock_playwright

        await browser.close()

        mock_playwright.stop.assert_called_once()


# ──────────────────────────────────────────────
# get_console_errors
# ──────────────────────────────────────────────


class TestGetConsoleErrorsExtended:
    """Extended tests for get_console_errors."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_console_errors_empty(self, browser):
        """Should return empty list when no console logs."""
        errors = await browser.get_console_errors()
        assert errors == []

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_console_errors_mixed_types(self, browser):
        """Should filter only error type logs."""
        browser.console_logs = [
            {"type": "log", "text": "info"},
            {"type": "warn", "text": "warning"},
            {"type": "error", "text": "error1"},
            {"type": "error", "text": "error2"},
        ]

        errors = await browser.get_console_errors()

        assert len(errors) == 2
        assert errors == ["error1", "error2"]

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_console_errors_all_non_error(self, browser):
        """Should return empty list when no error logs."""
        browser.console_logs = [
            {"type": "log", "text": "info"},
            {"type": "warn", "text": "warning"},
        ]

        errors = await browser.get_console_errors()

        assert errors == []
