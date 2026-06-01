"""
Deterministic Mode for Vectra QA CI/CD.

Replaces LLM-driven agents with scripted YAML playbooks for reliable,
repeatable testing. No API calls, no flakiness.

Usage:
    from mcp_server.deterministic import DeterministicTester, load_playbook

    tester = DeterministicTester()
    playbook = load_playbook("tests/playbooks/homepage.yaml")
    results = await tester.execute_playbook(playbook, browser)
"""

import yaml
from typing import Any, Dict, List, Optional, cast
from dataclasses import dataclass, field
from datetime import datetime, timezone

import structlog

from mcp_server.browser_tools import BrowserAutomation

logger = structlog.get_logger()


@dataclass
class PlaybookResult:
    """Result from executing a playbook step."""

    step_index: int
    action: str
    success: bool
    message: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    duration_seconds: float = 0.0


class DeterministicTester:
    """Executes deterministic test playbooks against a browser."""

    def __init__(self):
        self.results: List[PlaybookResult] = []

    async def execute_playbook(
        self, playbook: Dict[str, Any], browser: BrowserAutomation
    ) -> List[PlaybookResult]:
        """Execute all steps in a playbook."""
        self.results = []
        start_time = datetime.now(timezone.utc)

        logger.info(
            "playbook_execution_started",
            name=playbook.get("name", "unnamed"),
            url=playbook.get("url", ""),
            step_count=len(playbook.get("steps", [])),
        )

        for idx, step in enumerate(playbook.get("steps", [])):
            step_start = datetime.now(timezone.utc)
            result = await self._execute_step(idx, step, browser)
            result.duration_seconds = (datetime.now(timezone.utc) - step_start).total_seconds()
            self.results.append(result)

            if not result.success and step.get("required", True):
                logger.warning(
                    "playbook_step_failed",
                    step_index=idx,
                    action=step.get("action"),
                    message=result.message,
                )
                break

        total_duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        success_count = sum(1 for r in self.results if r.success)
        total_count = len(self.results)

        logger.info(
            "playbook_execution_completed",
            name=playbook.get("name", "unnamed"),
            success_count=success_count,
            total_count=total_count,
            duration_seconds=total_duration,
        )

        return self.results

    async def _execute_step(
        self, idx: int, step: Dict[str, Any], browser: BrowserAutomation
    ) -> PlaybookResult:
        """Execute a single playbook step."""
        action = step.get("action", "unknown")

        try:
            if action == "visit":
                return await self._action_visit(idx, step, browser)
            elif action == "click":
                return await self._action_click(idx, step, browser)
            elif action == "fill":
                return await self._action_fill(idx, step, browser)
            elif action == "assert":
                return await self._action_assert(idx, step, browser)
            elif action == "screenshot":
                return await self._action_screenshot(idx, step, browser)
            elif action == "wait":
                return await self._action_wait(idx, step, browser)
            elif action == "scroll":
                return await self._action_scroll(idx, step, browser)
            elif action == "hover":
                return await self._action_hover(idx, step, browser)
            else:
                return PlaybookResult(
                    step_index=idx,
                    action=action,
                    success=False,
                    message=f"Unknown action: {action}",
                )
        except Exception as e:
            return PlaybookResult(
                step_index=idx,
                action=action,
                success=False,
                message=str(e),
            )

    async def _action_visit(
        self, idx: int, step: Dict, browser: BrowserAutomation
    ) -> PlaybookResult:
        """Visit a URL."""
        url = step.get("url", "")
        if not url:
            return PlaybookResult(idx, "visit", False, "No URL specified")

        result = await browser.visit(url)
        return PlaybookResult(
            idx,
            "visit",
            result.get("success", False),
            message=result.get("error", f"Visited {url}"),
            data={
                "url": result.get("final_url", url),
                "title": await browser.page.title() if browser.page else "",
            },
        )

    async def _action_click(
        self, idx: int, step: Dict, browser: BrowserAutomation
    ) -> PlaybookResult:
        """Click an element."""
        selector = step.get("selector", "")
        if not selector:
            return PlaybookResult(idx, "click", False, "No selector specified")

        result = await browser.click(selector)
        return PlaybookResult(
            idx,
            "click",
            result.get("success", False),
            message=result.get("error", f"Clicked {selector}"),
            data={"url": result.get("url", "")},
        )

    async def _action_fill(
        self, idx: int, step: Dict, browser: BrowserAutomation
    ) -> PlaybookResult:
        """Fill an input field."""
        selector = step.get("selector", "")
        value = step.get("value", "")
        if not selector:
            return PlaybookResult(idx, "fill", False, "No selector specified")

        result = await browser.fill(selector, value)
        return PlaybookResult(
            idx,
            "fill",
            result.get("success", False),
            message=(
                f"Filled {selector} with '{value[:50]}...'"
                if len(value) > 50
                else f"Filled {selector} with '{value}'"
            ),
        )

    async def _action_assert(
        self, idx: int, step: Dict, browser: BrowserAutomation
    ) -> PlaybookResult:
        """Assert element exists or contains text."""
        selector = step.get("selector", "")
        expected_text = step.get("expected_text", "")
        expected_count = step.get("expected_count")

        if not selector:
            return PlaybookResult(idx, "assert", False, "No selector specified")

        # Check element exists
        elements = await browser.get_elements(selector)
        if not elements.get("success"):
            return PlaybookResult(idx, "assert", False, f"Element not found: {selector}")

        # Check count if specified
        if expected_count is not None:
            actual_count = elements.get("count", 0)
            if actual_count != expected_count:
                return PlaybookResult(
                    idx,
                    "assert",
                    False,
                    f"Expected {expected_count} elements, found {actual_count}",
                    data={"expected": expected_count, "actual": actual_count},
                )

        # Check text if specified
        if expected_text:
            text_result = await browser.get_text(selector)
            actual_text = text_result.get("text", "")
            if expected_text not in actual_text:
                return PlaybookResult(
                    idx,
                    "assert",
                    False,
                    f"Expected text '{expected_text}' not found in '{actual_text[:100]}...'",
                    data={"expected": expected_text, "actual": actual_text},
                )

        return PlaybookResult(idx, "assert", True, f"Assertion passed: {selector}")

    async def _action_screenshot(
        self, idx: int, step: Dict, browser: BrowserAutomation
    ) -> PlaybookResult:
        """Take a screenshot."""
        path = step.get("path", "screenshot.png")
        result = await browser.screenshot(path, full_page=step.get("full_page", True))
        return PlaybookResult(
            idx,
            "screenshot",
            result.get("success", False),
            message=result.get("error", f"Screenshot saved to {path}"),
            data={"path": path},
        )

    async def _action_wait(
        self, idx: int, step: Dict, browser: BrowserAutomation
    ) -> PlaybookResult:
        """Wait for specified milliseconds."""
        import asyncio

        ms = step.get("ms", 1000)
        await asyncio.sleep(ms / 1000)
        return PlaybookResult(idx, "wait", True, f"Waited {ms}ms")

    async def _action_scroll(
        self, idx: int, step: Dict, browser: BrowserAutomation
    ) -> PlaybookResult:
        """Scroll page."""
        direction = step.get("direction", "bottom")
        if direction == "bottom":
            result = await browser.scroll_to_bottom()
        else:
            # Could add more scroll directions
            result = await browser.scroll_to_bottom()
        return PlaybookResult(idx, "scroll", result.get("success", False))

    async def _action_hover(
        self, idx: int, step: Dict, browser: BrowserAutomation
    ) -> PlaybookResult:
        """Hover over an element."""
        selector = step.get("selector", "")
        if not selector:
            return PlaybookResult(idx, "hover", False, "No selector specified")

        if browser.page:
            await browser.page.hover(selector)
            return PlaybookResult(idx, "hover", True, f"Hovered {selector}")
        return PlaybookResult(idx, "hover", False, "Browser page not available")


def load_playbook(path: str) -> Dict[str, Any]:
    """Load a playbook from YAML file."""
    with open(path, "r", encoding="utf-8") as f:
        return cast(Dict[str, Any], yaml.safe_load(f) or {})


def save_playbook(playbook: Dict[str, Any], path: str):
    """Save a playbook to YAML file."""
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(playbook, f, default_flow_style=False, allow_unicode=True)


# Global singleton
_tester: Optional[DeterministicTester] = None


def get_deterministic_tester() -> DeterministicTester:
    """Get or create the DeterministicTester singleton."""
    global _tester
    if _tester is None:
        _tester = DeterministicTester()
    return _tester
