"""
Browser Automation Module for Vectra QA Agents

Provides Playwright-based browser automation for UI testing.
Used by agent workers to perform real browser interactions.
"""

import os
import asyncio
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone
from playwright.async_api import async_playwright, Page, Browser, ConsoleMessage


class BrowserAutomation:
    """
    Browser automation wrapper using Playwright.

    Usage:
        browser = BrowserAutomation(headless=True)
        await browser.start()
        result = await browser.visit("https://example.com")
        await browser.click("#login-btn")
        await browser.screenshot("/path/to/screenshot.png")
        await browser.close()
    """

    def __init__(self, headless: bool = True, slow_mo: int = 0):
        self.headless = headless
        self.slow_mo = slow_mo
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        self.console_logs: List[Dict[str, Any]] = []
        self.network_logs: List[Dict[str, Any]] = []
        self.errors: List[str] = []

    async def start(self):
        """Launch browser and create page."""
        self.playwright = await async_playwright().start()

        launch_options = {
            "headless": self.headless,
        }

        if self.slow_mo > 0:
            launch_options["slow_mo"] = self.slow_mo

        self.browser = await self.playwright.chromium.launch(**launch_options)

        context = await self.browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.0 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.0 VectraQA/1.0",
        )

        self.page = await context.new_page()

        # Set up event listeners
        self.page.on("console", self._handle_console)
        self.page.on("pageerror", self._handle_page_error)
        self.page.on("response", self._handle_response)

    def _handle_console(self, msg: ConsoleMessage):
        """Capture console messages."""
        self.console_logs.append(
            {
                "type": msg.type,
                "text": msg.text,
                "time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z",
            }
        )

    def _handle_page_error(self, error):
        """Capture page errors."""
        self.errors.append(str(error))

    def _handle_response(self, response):
        """Capture network responses."""
        self.network_logs.append(
            {
                "url": response.url,
                "status": response.status,
                "time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z",
            }
        )

    async def visit(self, url: str, wait_until: str = "networkidle") -> Dict[str, Any]:
        """Navigate to URL."""
        if not self.page:
            raise RuntimeError("Browser not started. Call start() first.")

        try:
            response = await self.page.goto(url, wait_until=wait_until, timeout=30000)
            return {
                "success": True,
                "url": url,
                "final_url": self.page.url,
                "title": await self.page.title(),
                "status": response.status if response else None,
                "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z",
            }
        except Exception as e:
            return {
                "success": False,
                "url": url,
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z",
            }

    async def click(self, selector: str, timeout: int = 5000) -> Dict[str, Any]:
        """Click element by selector."""
        try:
            await self.page.click(selector, timeout=timeout)
            await self.page.wait_for_load_state("networkidle", timeout=10000)
            return {
                "success": True,
                "selector": selector,
                "url": self.page.url,
                "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z",
            }
        except Exception as e:
            return {
                "success": False,
                "selector": selector,
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z",
            }

    async def fill(self, selector: str, text: str) -> Dict[str, Any]:
        """Fill input field."""
        try:
            await self.page.fill(selector, text)
            return {
                "success": True,
                "selector": selector,
                "text": text,
                "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z",
            }
        except Exception as e:
            return {
                "success": False,
                "selector": selector,
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z",
            }

    async def get_text(self, selector: str) -> Dict[str, Any]:
        """Get text content of element."""
        try:
            element = await self.page.query_selector(selector)
            if element:
                text = await element.text_content()
                return {
                    "success": True,
                    "selector": selector,
                    "text": text.strip() if text else "",
                    "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z",
                }
            else:
                return {
                    "success": False,
                    "selector": selector,
                    "error": "Element not found",
                    "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z",
                }
        except Exception as e:
            return {
                "success": False,
                "selector": selector,
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z",
            }

    async def get_elements(self, selector: str) -> Dict[str, Any]:
        """Count elements matching selector."""
        try:
            elements = await self.page.query_selector_all(selector)
            return {
                "success": True,
                "selector": selector,
                "count": len(elements),
                "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z",
            }
        except Exception as e:
            return {
                "success": False,
                "selector": selector,
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z",
            }

    async def screenshot(self, path: str, full_page: bool = True) -> Dict[str, Any]:
        """Take screenshot."""
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(path), exist_ok=True)
            await self.page.screenshot(path=path, full_page=full_page)
            return {
                "success": True,
                "path": path,
                "full_page": full_page,
                "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z",
            }
        except Exception as e:
            return {
                "success": False,
                "path": path,
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z",
            }

    async def scroll_to_bottom(self) -> Dict[str, Any]:
        """Scroll to bottom of page."""
        try:
            await self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(0.5)
            return {
                "success": True,
                "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z",
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z",
            }

    async def check_responsive(self, width: int, height: int) -> Dict[str, Any]:
        """Test viewport size."""
        try:
            await self.page.set_viewport_size({"width": width, "height": height})
            await asyncio.sleep(1)
            return {
                "success": True,
                "viewport": f"{width}x{height}",
                "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z",
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z",
            }

    async def get_console_errors(self) -> List[str]:
        """Get console error messages."""
        errors = [log["text"] for log in self.console_logs if log["type"] == "error"]
        return errors

    async def get_all_links(self) -> Dict[str, Any]:
        """Get all links on page."""
        try:
            links = await self.page.query_selector_all("a")
            results = []
            for link in links:
                href = await link.get_attribute("href")
                text = await link.text_content()
                if href:
                    results.append(
                        {
                            "href": href,
                            "text": text.strip() if text else "",
                            "visible": await link.is_visible(),
                        }
                    )
            return {
                "success": True,
                "count": len(results),
                "links": results,
                "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z",
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z",
            }

    async def check_form(self, form_selector: str = "form") -> Dict[str, Any]:
        """Check form fields."""
        try:
            form = await self.page.query_selector(form_selector)
            if not form:
                return {
                    "success": False,
                    "error": "Form not found",
                    "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z",
                }

            inputs = await form.query_selector_all("input, textarea, select")
            fields = []
            for inp in inputs:
                field_type = await inp.get_attribute("type") or "text"
                name = await inp.get_attribute("name") or ""
                placeholder = await inp.get_attribute("placeholder") or ""
                required = await inp.get_attribute("required") is not None

                fields.append(
                    {
                        "type": field_type,
                        "name": name,
                        "placeholder": placeholder,
                        "required": required,
                    }
                )

            return {
                "success": True,
                "fields": fields,
                "count": len(fields),
                "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z",
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z",
            }

    async def close(self):
        """Close browser."""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
