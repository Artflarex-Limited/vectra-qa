"""
Multi-browser support for Vectra QA.

Supports Chromium, Firefox, and WebKit via Playwright.
"""

import os
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

import structlog

logger = structlog.get_logger()


class MultiBrowserTester:
    """Runs tests across multiple browsers."""

    BROWSERS = ["chromium", "firefox", "webkit"]

    def __init__(self):
        self.results: Dict[str, Any] = {}
        self.findings: List[Dict[str, Any]] = []

    async def test_all_browsers(
        self, test_func, url: str, browsers: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Run a test function across multiple browsers.

        Args:
            test_func: Async function that takes a BrowserAutomation instance and URL
            url: URL to test
            browsers: List of browsers to test (default: all)

        Returns:
            Results per browser
        """
        self.results = {}
        self.findings = []
        start_time = datetime.now(timezone.utc)

        test_browsers = browsers or self.BROWSERS

        for browser_name in test_browsers:
            browser_start = datetime.now(timezone.utc)

            try:
                # Create browser for this type
                from mcp_server.browser_tools import BrowserAutomation

                # Create browser with specific browser type
                browser = BrowserAutomation(headless=True)

                # Override browser launch to use specific browser
                playwright = (
                    await browser.playwright.start() if hasattr(browser, "playwright") else None
                )

                if not playwright:
                    # Need to start playwright first
                    from playwright.async_api import async_playwright

                    playwright = await async_playwright().start()

                # Launch specific browser
                if browser_name == "chromium":
                    launched_browser = await playwright.chromium.launch(headless=True)
                elif browser_name == "firefox":
                    launched_browser = await playwright.firefox.launch(headless=True)
                elif browser_name == "webkit":
                    launched_browser = await playwright.webkit.launch(headless=True)
                else:
                    self.findings.append(
                        {
                            "title": f"Unknown Browser",
                            "description": f"Browser '{browser_name}' not supported",
                            "severity": "warning",
                        }
                    )
                    continue

                # Create context and page
                context = await launched_browser.new_context(
                    viewport={"width": 1920, "height": 1080}
                )
                page = await context.new_page()

                # Attach to BrowserAutomation
                browser.browser = launched_browser
                browser.page = page
                browser.playwright = playwright

                # Run test
                result = await test_func(browser, url)

                self.results[browser_name] = {
                    "status": result.get("status", "unknown"),
                    "findings": result.get("findings", []),
                    "duration_seconds": (
                        datetime.now(timezone.utc) - browser_start
                    ).total_seconds(),
                }

                # Compare with chromium results
                if browser_name != "chromium" and "chromium" in self.results:
                    chromium_result = self.results["chromium"]
                    if result.get("status") != chromium_result.get("status"):
                        self.findings.append(
                            {
                                "title": f"Browser Divergence: {browser_name}",
                                "description": f"{browser_name}: {result.get('status')}, chromium: {chromium_result.get('status')}",
                                "severity": "high",
                            }
                        )

                # Cleanup
                await launched_browser.close()

            except Exception as e:
                logger.error("browser_test_error", browser=browser_name, error=str(e))
                self.results[browser_name] = {
                    "status": "error",
                    "error": str(e),
                    "duration_seconds": (
                        datetime.now(timezone.utc) - browser_start
                    ).total_seconds(),
                }
                self.findings.append(
                    {
                        "title": f"{browser_name.title()} Error",
                        "description": str(e),
                        "severity": "high",
                    }
                )

        # Determine overall status
        statuses = [r["status"] for r in self.results.values()]

        if any(s == "fail" for s in statuses):
            overall_status = "fail"
        elif any(s == "warning" for s in statuses):
            overall_status = "warning"
        elif any(s == "error" for s in statuses):
            overall_status = "warning"
        else:
            overall_status = "pass"

        return {
            "status": overall_status,
            "results": self.results,
            "findings": self.findings,
            "duration_seconds": (datetime.now(timezone.utc) - start_time).total_seconds(),
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z",
        }

    async def capture_screenshots(
        self,
        url: str,
        browsers: Optional[List[str]] = None,
        viewport: Optional[Dict[str, int]] = None,
    ) -> Dict[str, Any]:
        """
        Capture screenshots across multiple browsers.

        Args:
            url: URL to screenshot
            browsers: List of browsers (default: all)
            viewport: Optional viewport size

        Returns:
            Screenshot paths per browser
        """
        screenshots = {}

        async def take_screenshot(browser, test_url):
            await browser.visit(test_url)

            if viewport and browser.page:
                await browser.page.set_viewport_size(viewport)

            path = f"obsidian_vault/Screenshots/cross_browser_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}.png"
            result = await browser.screenshot(path)

            return {
                "status": "pass" if result.get("success") else "fail",
                "screenshot_path": path if result.get("success") else None,
            }

        result = await self.test_all_browsers(take_screenshot, url, browsers)

        for browser_name, browser_result in result.get("results", {}).items():
            if browser_result.get("status") == "pass":
                findings = browser_result.get("findings", [])
                screenshot_path = next(
                    (f.get("screenshot_path") for f in findings if f.get("screenshot_path")), None
                )
                if screenshot_path:
                    screenshots[browser_name] = screenshot_path

        return {
            "screenshots": screenshots,
            "status": result["status"],
            "findings": result["findings"],
        }
