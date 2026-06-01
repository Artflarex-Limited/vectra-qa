"""
Unit tests for mcp_server/features/multi_browser.py.
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch

from mcp_server.features.multi_browser import MultiBrowserTester


@pytest.mark.unit
class TestMultiBrowserTester:
    """Tests for MultiBrowserTester."""

    @pytest.fixture
    def tester(self):
        return MultiBrowserTester()

    @pytest.fixture
    def mock_playwright(self):
        """Create a fully mocked playwright context."""
        mock_browser_instance = AsyncMock()
        mock_context = AsyncMock()
        mock_page = AsyncMock()

        mock_browser_instance.new_context = AsyncMock(return_value=mock_context)
        mock_context.new_page = AsyncMock(return_value=mock_page)

        mock_chromium = AsyncMock()
        mock_chromium.launch = AsyncMock(return_value=mock_browser_instance)
        mock_firefox = AsyncMock()
        mock_firefox.launch = AsyncMock(return_value=mock_browser_instance)
        mock_webkit = AsyncMock()
        mock_webkit.launch = AsyncMock(return_value=mock_browser_instance)

        pw = AsyncMock()
        pw.chromium = mock_chromium
        pw.firefox = mock_firefox
        pw.webkit = mock_webkit

        return pw, mock_browser_instance, mock_context, mock_page

    @pytest.mark.asyncio
    async def test_init(self, tester):
        """Should initialize with empty results and findings."""
        assert tester.results == {}
        assert tester.findings == []
        assert tester.BROWSERS == ["chromium", "firefox", "webkit"]

    @pytest.mark.asyncio
    async def test_test_all_browsers_all_pass(self, tester, mock_playwright):
        """Should run tests across all browsers successfully."""
        pw, mock_browser_instance, mock_context, mock_page = mock_playwright

        async def mock_test_func(browser, url):
            return {"status": "pass", "findings": []}

        with patch("mcp_server.browser_tools.BrowserAutomation") as MockBrowserAuto:
            mock_browser_auto = Mock()
            mock_browser_auto.playwright = None
            MockBrowserAuto.return_value = mock_browser_auto

            with patch("playwright.async_api.async_playwright") as mock_async_pw:
                mock_pw_mgr = AsyncMock()
                mock_pw_mgr.start = AsyncMock(return_value=pw)
                mock_async_pw.return_value = mock_pw_mgr

                result = await tester.test_all_browsers(mock_test_func, "https://example.com")

        assert result["status"] == "pass"
        assert "chromium" in result["results"]
        assert "firefox" in result["results"]
        assert "webkit" in result["results"]
        assert result["results"]["chromium"]["status"] == "pass"
        assert result["results"]["firefox"]["status"] == "pass"
        assert result["results"]["webkit"]["status"] == "pass"
        assert "duration_seconds" in result
        assert "timestamp" in result

    @pytest.mark.asyncio
    async def test_test_all_browsers_with_divergence(self, tester, mock_playwright):
        """Should detect status divergence across browsers."""
        pw, mock_browser_instance, mock_context, mock_page = mock_playwright

        call_count = 0

        async def mock_test_func(browser, url):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"status": "pass", "findings": []}
            return {"status": "fail", "findings": []}

        with patch("mcp_server.browser_tools.BrowserAutomation") as MockBrowserAuto:
            mock_browser_auto = Mock()
            mock_browser_auto.playwright = None
            MockBrowserAuto.return_value = mock_browser_auto

            with patch("playwright.async_api.async_playwright") as mock_async_pw:
                mock_pw_mgr = AsyncMock()
                mock_pw_mgr.start = AsyncMock(return_value=pw)
                mock_async_pw.return_value = mock_pw_mgr

                result = await tester.test_all_browsers(mock_test_func, "https://example.com")

        assert result["status"] == "fail"
        divergence = [f for f in result["findings"] if "Divergence" in f["title"]]
        assert len(divergence) > 0

    @pytest.mark.asyncio
    async def test_test_all_browsers_unknown_browser(self, tester, mock_playwright):
        """Should handle unknown browser types gracefully."""
        pw, mock_browser_instance, mock_context, mock_page = mock_playwright

        async def mock_test_func(browser, url):
            return {"status": "pass", "findings": []}

        with patch("mcp_server.browser_tools.BrowserAutomation") as MockBrowserAuto:
            mock_browser_auto = Mock()
            mock_browser_auto.playwright = None
            MockBrowserAuto.return_value = mock_browser_auto

            with patch("playwright.async_api.async_playwright") as mock_async_pw:
                mock_pw_mgr = AsyncMock()
                mock_pw_mgr.start = AsyncMock(return_value=pw)
                mock_async_pw.return_value = mock_pw_mgr

                result = await tester.test_all_browsers(
                    mock_test_func,
                    "https://example.com",
                    browsers=["chromium", "ie6"],
                )

        assert "chromium" in result["results"]
        assert "ie6" not in result["results"]
        unknown = [f for f in result["findings"] if "Unknown Browser" in f["title"]]
        assert len(unknown) == 1
        assert unknown[0]["severity"] == "warning"

    @pytest.mark.asyncio
    async def test_test_all_browsers_error_handling(self, tester, mock_playwright):
        """Should handle browser launch failures."""
        pw, mock_browser_instance, mock_context, mock_page = mock_playwright
        pw.chromium.launch = AsyncMock(side_effect=Exception("Launch failed"))
        pw.firefox.launch = AsyncMock(side_effect=Exception("Launch failed"))
        pw.webkit.launch = AsyncMock(side_effect=Exception("Launch failed"))

        async def mock_test_func(browser, url):
            return {"status": "pass", "findings": []}

        with patch("mcp_server.browser_tools.BrowserAutomation") as MockBrowserAuto:
            mock_browser_auto = Mock()
            mock_browser_auto.playwright = None
            MockBrowserAuto.return_value = mock_browser_auto

            with patch("playwright.async_api.async_playwright") as mock_async_pw:
                mock_pw_mgr = AsyncMock()
                mock_pw_mgr.start = AsyncMock(return_value=pw)
                mock_async_pw.return_value = mock_pw_mgr

                result = await tester.test_all_browsers(mock_test_func, "https://example.com")

        assert result["status"] == "warning"
        for browser_name in tester.BROWSERS:
            assert result["results"][browser_name]["status"] == "error"
            assert "Launch failed" in result["results"][browser_name]["error"]

    @pytest.mark.asyncio
    async def test_test_all_browsers_warning_status(self, tester, mock_playwright):
        """Should return warning when any browser returns warning."""
        pw, mock_browser_instance, mock_context, mock_page = mock_playwright

        call_count = 0

        async def mock_test_func(browser, url):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"status": "pass", "findings": []}
            return {"status": "warning", "findings": []}

        with patch("mcp_server.browser_tools.BrowserAutomation") as MockBrowserAuto:
            mock_browser_auto = Mock()
            mock_browser_auto.playwright = None
            MockBrowserAuto.return_value = mock_browser_auto

            with patch("playwright.async_api.async_playwright") as mock_async_pw:
                mock_pw_mgr = AsyncMock()
                mock_pw_mgr.start = AsyncMock(return_value=pw)
                mock_async_pw.return_value = mock_pw_mgr

                result = await tester.test_all_browsers(mock_test_func, "https://example.com")

        assert result["status"] == "warning"

    @pytest.mark.asyncio
    async def test_test_all_browsers_playwright_already_started(self, tester, mock_playwright):
        """Should reuse existing playwright if browser has it."""
        pw, mock_browser_instance, mock_context, mock_page = mock_playwright

        async def mock_test_func(browser, url):
            return {"status": "pass", "findings": []}

        with patch("mcp_server.browser_tools.BrowserAutomation") as MockBrowserAuto:
            mock_browser_auto = Mock()
            mock_pw = Mock()
            mock_pw.start = AsyncMock(return_value=pw)
            mock_browser_auto.playwright = mock_pw
            MockBrowserAuto.return_value = mock_browser_auto

            result = await tester.test_all_browsers(
                mock_test_func, "https://example.com", browsers=["chromium"]
            )

        assert result["status"] == "pass"
        mock_pw.start.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_capture_screenshots(self, tester, mock_playwright, tmp_path):
        """Should capture screenshots across browsers."""
        pw, mock_browser_instance, mock_context, mock_page = mock_playwright

        with patch("mcp_server.browser_tools.BrowserAutomation") as MockBrowserAuto:
            mock_browser_auto = Mock()
            mock_browser_auto.playwright = None
            mock_browser_auto.visit = AsyncMock(return_value={"success": True})
            mock_browser_auto.screenshot = AsyncMock(return_value={"success": True})
            mock_browser_auto.page = mock_page
            MockBrowserAuto.return_value = mock_browser_auto

            with patch("playwright.async_api.async_playwright") as mock_async_pw:
                mock_pw_mgr = AsyncMock()
                mock_pw_mgr.start = AsyncMock(return_value=pw)
                mock_async_pw.return_value = mock_pw_mgr

                result = await tester.capture_screenshots(
                    "https://example.com",
                    browsers=["chromium"],
                    viewport={"width": 1280, "height": 720},
                )

        assert "screenshots" in result
        assert result["status"] == "pass"

    @pytest.mark.asyncio
    async def test_capture_screenshots_no_success(self, tester, mock_playwright):
        """Should handle screenshot failures."""
        pw, mock_browser_instance, mock_context, mock_page = mock_playwright

        with patch("mcp_server.browser_tools.BrowserAutomation") as MockBrowserAuto:
            mock_browser_auto = Mock()
            mock_browser_auto.playwright = None
            mock_browser_auto.visit = AsyncMock(return_value={"success": True})
            mock_browser_auto.screenshot = AsyncMock(return_value={"success": False})
            mock_browser_auto.page = mock_page
            MockBrowserAuto.return_value = mock_browser_auto

            with patch("playwright.async_api.async_playwright") as mock_async_pw:
                mock_pw_mgr = AsyncMock()
                mock_pw_mgr.start = AsyncMock(return_value=pw)
                mock_async_pw.return_value = mock_pw_mgr

                result = await tester.capture_screenshots(
                    "https://example.com", browsers=["chromium"]
                )

        assert result["screenshots"] == {}

    @pytest.mark.asyncio
    async def test_test_all_browsers_empty_browser_list(self, tester):
        """Should fall back to default browsers when empty list provided."""

        async def mock_test_func(browser, url):
            return {"status": "pass", "findings": []}

        # Since [] is falsy, code falls back to self.BROWSERS
        # We just verify the method handles it without error
        # by checking it doesn't crash and uses defaults
        with patch("mcp_server.browser_tools.BrowserAutomation") as MockBrowserAuto:
            mock_browser_auto = Mock()
            mock_browser_auto.playwright = None
            MockBrowserAuto.return_value = mock_browser_auto

            with patch("playwright.async_api.async_playwright") as mock_async_pw:
                mock_pw = AsyncMock()
                mock_pw.start = AsyncMock(return_value=AsyncMock())
                mock_async_pw.return_value = mock_pw

                result = await tester.test_all_browsers(
                    mock_test_func, "https://example.com", browsers=[]
                )

        # Empty list falls back to all browsers due to `or self.BROWSERS`
        assert len(result["results"]) == 3
