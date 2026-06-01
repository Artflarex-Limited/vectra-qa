"""
Unit tests for BrowserAutomation.
Uses mocked Playwright to avoid real browser launching.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch

from mcp_server.browser_tools import BrowserAutomation


class TestBrowserAutomationBasic:
    """Test BrowserAutomation lifecycle."""

    @pytest.fixture
    def browser(self):
        """Create a BrowserAutomation instance."""
        return BrowserAutomation(headless=True)

    @pytest.mark.asyncio
    async def test_start_creates_browser(self, browser):
        """Should launch browser and create page."""
        mock_playwright = AsyncMock()
        mock_browser = AsyncMock()
        mock_context = AsyncMock()
        mock_page = AsyncMock()
        mock_page.on = Mock()  # Event registration is synchronous

        mock_playwright.start.return_value = mock_playwright
        mock_playwright.chromium.launch.return_value = mock_browser
        mock_browser.new_context.return_value = mock_context
        mock_context.new_page.return_value = mock_page

        with patch("mcp_server.browser_tools.async_playwright", return_value=mock_playwright):
            await browser.start()

        assert browser.browser == mock_browser
        assert browser.page == mock_page
        mock_playwright.chromium.launch.assert_called_once_with(headless=True)
        # Verify event listeners were registered
        assert mock_page.on.call_count == 3

    @pytest.mark.asyncio
    async def test_close_browser(self, browser):
        """Should close browser cleanly."""
        mock_browser = AsyncMock()
        mock_playwright = AsyncMock()

        browser.browser = mock_browser
        browser.playwright = mock_playwright

        await browser.close()

        mock_browser.close.assert_called_once()
        mock_playwright.stop.assert_called_once()


class TestBrowserAutomationNavigation:
    """Test page navigation."""

    @pytest.fixture
    def browser_with_page(self):
        """Create browser with mocked page."""
        browser = BrowserAutomation(headless=True)
        browser.page = AsyncMock()
        browser.page.url = "https://example.com"
        return browser

    @pytest.mark.asyncio
    async def test_visit_success(self, browser_with_page):
        """Should navigate to URL successfully."""
        mock_response = Mock()
        mock_response.status = 200
        browser_with_page.page.goto.return_value = mock_response
        browser_with_page.page.title.return_value = "Example"

        result = await browser_with_page.visit("https://example.com")

        assert result["success"] is True
        assert result["url"] == "https://example.com"
        assert result["status"] == 200
        assert result["title"] == "Example"

    @pytest.mark.asyncio
    async def test_visit_failure(self, browser_with_page):
        """Should handle navigation errors."""
        browser_with_page.page.goto.side_effect = Exception("Timeout")

        result = await browser_with_page.visit("https://example.com")

        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_click_element(self, browser_with_page):
        """Should click element by selector."""
        result = await browser_with_page.click("#submit-btn")

        assert result["success"] is True
        assert result["selector"] == "#submit-btn"
        browser_with_page.page.click.assert_called_once_with("#submit-btn", timeout=5000)


class TestBrowserAutomationContent:
    """Test content extraction."""

    @pytest.fixture
    def browser_with_page(self):
        """Create browser with mocked page."""
        browser = BrowserAutomation(headless=True)
        browser.page = AsyncMock()
        return browser

    @pytest.mark.asyncio
    async def test_get_text(self, browser_with_page):
        """Should get text content of element."""
        mock_element = AsyncMock()
        mock_element.text_content.return_value = "Hello World"
        browser_with_page.page.query_selector.return_value = mock_element

        result = await browser_with_page.get_text("#title")

        assert result["success"] is True
        assert result["text"] == "Hello World"

    @pytest.mark.asyncio
    async def test_get_elements_count(self, browser_with_page):
        """Should count elements matching selector."""
        browser_with_page.page.query_selector_all.return_value = [Mock(), Mock(), Mock()]

        result = await browser_with_page.get_elements(".card")

        assert result["success"] is True
        assert result["count"] == 3


class TestBrowserAutomationCapture:
    """Test screenshot and console capture."""

    @pytest.fixture
    def browser_with_page(self):
        """Create browser with mocked page."""
        browser = BrowserAutomation(headless=True)
        browser.page = AsyncMock()
        browser.page.url = "https://example.com"
        return browser

    @pytest.mark.asyncio
    async def test_screenshot(self, browser_with_page):
        """Should take screenshot."""
        result = await browser_with_page.screenshot("/tmp/test.png", full_page=True)

        assert result["success"] is True
        assert result["path"] == "/tmp/test.png"
        assert result["full_page"] is True
        browser_with_page.page.screenshot.assert_called_once_with(
            path="/tmp/test.png", full_page=True
        )

    @pytest.mark.asyncio
    async def test_get_console_errors(self, browser_with_page):
        """Should extract console error messages."""
        browser_with_page.console_logs = [
            {"type": "error", "text": "TypeError: undefined"},
            {"type": "log", "text": "Normal log"},
            {"type": "error", "text": "ReferenceError: x"},
        ]

        errors = await browser_with_page.get_console_errors()

        assert len(errors) == 2
        assert "TypeError" in errors[0]


class TestBrowserAutomationForms:
    """Test form interaction."""

    @pytest.fixture
    def browser_with_page(self):
        """Create browser with mocked page."""
        browser = BrowserAutomation(headless=True)
        browser.page = AsyncMock()
        return browser

    @pytest.mark.asyncio
    async def test_fill_form(self, browser_with_page):
        """Should fill input field."""
        result = await browser_with_page.fill("#email", "test@example.com")

        assert result["success"] is True
        assert result["selector"] == "#email"
        assert result["text"] == "test@example.com"
        browser_with_page.page.fill.assert_called_once_with("#email", "test@example.com")

    @pytest.mark.asyncio
    async def test_check_form(self, browser_with_page):
        """Should analyze form fields."""
        mock_form = AsyncMock()
        mock_input1 = AsyncMock()
        mock_input1.get_attribute.side_effect = ["text", "email", "", None]

        mock_input2 = AsyncMock()
        mock_input2.get_attribute.side_effect = ["password", "pass", "", True]

        browser_with_page.page.query_selector.return_value = mock_form
        mock_form.query_selector_all.return_value = [mock_input1, mock_input2]

        result = await browser_with_page.check_form("#login-form")

        assert result["success"] is True
        assert result["count"] == 2
        assert len(result["fields"]) == 2
