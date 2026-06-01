"""
Resource limits and browser pool for Vectra QA.

Controls concurrent browser instances, agent timeouts, and resource usage.
"""

import os
import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

import structlog

from mcp_server.browser_tools import BrowserAutomation

logger = structlog.get_logger()

# Configuration
MAX_CONCURRENT_BROWSERS = int(os.getenv("VECTRA_MAX_BROWSERS", "10"))
MAX_AGENT_DURATION_SECONDS = int(os.getenv("VECTRA_MAX_AGENT_DURATION", "600"))
MAX_AGENT_STEPS = int(os.getenv("VECTRA_MAX_AGENT_STEPS", "50"))
MAX_LLM_CALLS_PER_AGENT = int(os.getenv("VECTRA_MAX_LLM_CALLS", "50"))


class BrowserPool:
    """Pool of reusable browser contexts."""

    def __init__(self, max_size: int = MAX_CONCURRENT_BROWSERS):
        self.max_size = max_size
        self._pool: List[BrowserAutomation] = []
        self._in_use: Set[BrowserAutomation] = set()
        self._lock = asyncio.Lock()
        self._semaphore = asyncio.Semaphore(max_size)

    async def acquire(self) -> BrowserAutomation:
        """Acquire a browser from the pool."""
        async with self._semaphore:
            async with self._lock:
                # Try to reuse an available browser
                while self._pool:
                    browser = self._pool.pop()

                    # Validate: must have both page and browser instances
                    if browser.page is None or browser.browser is None:
                        logger.debug(
                            "browser_skipped_no_instance",
                            page=browser.page is not None,
                            browser=browser.browser is not None,
                        )
                        try:
                            await browser.close()
                        except Exception as e:
                            logger.warning("browser_close_failed", error=str(e), context="acquire_validation_no_instance")
                        continue

                    # Validate: must be connected (if method available)
                    if hasattr(browser.browser, "is_connected") and not browser.browser.is_connected():
                        logger.debug("browser_skipped_disconnected")
                        try:
                            await browser.close()
                        except Exception as e:
                            logger.warning("browser_close_failed", error=str(e), context="acquire_validation_disconnected")
                        continue

                    self._in_use.add(browser)
                    logger.debug("browser_reused_from_pool", pool_size=len(self._pool))
                    return browser

                # Create new browser
                browser = BrowserAutomation(headless=True)
                await browser.start()
                self._in_use.add(browser)
                logger.info("browser_created", total_created=len(self._in_use) + len(self._pool))
                return browser

    async def release(self, browser: BrowserAutomation, reset: bool = True):
        """Release a browser back to the pool."""
        async with self._lock:
            if browser in self._in_use:
                self._in_use.remove(browser)

                if reset and browser.page:
                    try:
                        # Clear cookies, storage, etc.
                        context = browser.page.context
                        await context.clear_cookies()
                        # Navigate to blank page to clear state
                        await browser.page.goto("about:blank")
                        logger.debug("browser_reset", pool_size=len(self._pool))
                    except Exception as e:
                        logger.warning("browser_reset_failed", error=str(e))
                        # Don't return broken browsers to pool
                        try:
                            await browser.close()
                        except Exception as e:
                            logger.warning("browser_close_failed", error=str(e), context="release_reset_failed")
                        return

                # Add back to pool if not full
                if len(self._pool) < self.max_size:  # Keep up to max_size browsers in pool
                    self._pool.append(browser)
                    logger.debug("browser_returned_to_pool", pool_size=len(self._pool))
                else:
                    # Pool is full, close browser
                    try:
                        await browser.close()
                    except Exception as e:
                        logger.warning("browser_close_failed", error=str(e), context="release_pool_full")
                    logger.debug("browser_closed_pool_full")

    async def cleanup(self):
        """Close all browsers in pool."""
        async with self._lock:
            for browser in self._pool:
                try:
                    await browser.close()
                except Exception as e:
                    logger.warning("browser_close_failed", error=str(e), context="cleanup_pool")
            self._pool.clear()

            for browser in list(self._in_use):
                try:
                    await browser.close()
                except Exception as e:
                    logger.warning("browser_close_failed", error=str(e), context="cleanup_in_use")
            self._in_use.clear()

            logger.info("browser_pool_cleaned")


class AgentResourceTracker:
    """Tracks resource usage per agent and enforces limits."""

    def __init__(self):
        self._agents: Dict[str, Dict[str, Any]] = {}
        self._llm_calls: Dict[str, int] = {}

    def register_agent(self, agent_id: str, max_duration: int = MAX_AGENT_DURATION_SECONDS):
        """Register a new agent with resource limits."""
        self._agents[agent_id] = {
            "started_at": datetime.now(timezone.utc),
            "max_duration": max_duration,
            "steps": 0,
            "llm_calls": 0,
            "status": "active",
        }
        self._llm_calls[agent_id] = 0
        logger.info("agent_registered", agent_id=agent_id, max_duration=max_duration)

    def record_step(self, agent_id: str) -> bool:
        """Record a step for an agent. Returns False if limit exceeded."""
        if agent_id not in self._agents:
            return False

        self._agents[agent_id]["steps"] += 1

        if self._agents[agent_id]["steps"] > MAX_AGENT_STEPS:
            logger.warning(
                "agent_step_limit_exceeded",
                agent_id=agent_id,
                steps=self._agents[agent_id]["steps"],
            )
            return False

        return True

    def record_llm_call(self, agent_id: str) -> bool:
        """Record an LLM call for an agent. Returns False if limit exceeded."""
        if agent_id not in self._agents:
            return False

        self._llm_calls[agent_id] = self._llm_calls.get(agent_id, 0) + 1
        self._agents[agent_id]["llm_calls"] = self._llm_calls[agent_id]

        if self._llm_calls[agent_id] > MAX_LLM_CALLS_PER_AGENT:
            logger.warning(
                "agent_llm_limit_exceeded", agent_id=agent_id, calls=self._llm_calls[agent_id]
            )
            return False

        return True

    def check_timeout(self, agent_id: str) -> bool:
        """Check if agent has exceeded time limit. Returns True if timed out."""
        if agent_id not in self._agents:
            return True

        elapsed = (
            datetime.now(timezone.utc) - self._agents[agent_id]["started_at"]
        ).total_seconds()
        max_duration = self._agents[agent_id]["max_duration"]

        if elapsed > max_duration:
            logger.warning(
                "agent_timeout", agent_id=agent_id, elapsed=elapsed, max_duration=max_duration
            )
            return True

        return False

    def get_usage(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get resource usage for an agent."""
        if agent_id not in self._agents:
            return None

        agent = self._agents[agent_id]
        elapsed = (datetime.now(timezone.utc) - agent["started_at"]).total_seconds()

        return {
            "elapsed_seconds": elapsed,
            "max_duration": agent["max_duration"],
            "steps": agent["steps"],
            "max_steps": MAX_AGENT_STEPS,
            "llm_calls": agent["llm_calls"],
            "max_llm_calls": MAX_LLM_CALLS_PER_AGENT,
            "remaining_time": max(0, agent["max_duration"] - elapsed),
            "remaining_steps": max(0, MAX_AGENT_STEPS - agent["steps"]),
            "remaining_llm_calls": max(0, MAX_LLM_CALLS_PER_AGENT - agent["llm_calls"]),
        }

    def unregister_agent(self, agent_id: str):
        """Unregister an agent and free resources."""
        if agent_id in self._agents:
            del self._agents[agent_id]
        if agent_id in self._llm_calls:
            del self._llm_calls[agent_id]
        logger.info("agent_unregistered", agent_id=agent_id)

    def get_all_usage(self) -> Dict[str, Dict[str, Any]]:
        """Get resource usage for all active agents."""
        return {
            agent_id: usage
            for agent_id in self._agents
            if (usage := self.get_usage(agent_id)) is not None
        }


# Global instances
_browser_pool_instance: Optional[BrowserPool] = None
_resource_tracker_instance: Optional[AgentResourceTracker] = None


def get_browser_pool() -> BrowserPool:
    """Get or create the BrowserPool instance."""
    global _browser_pool_instance
    if _browser_pool_instance is None:
        _browser_pool_instance = BrowserPool()
    return _browser_pool_instance


def get_resource_tracker() -> AgentResourceTracker:
    """Get or create the AgentResourceTracker instance."""
    global _resource_tracker_instance
    if _resource_tracker_instance is None:
        _resource_tracker_instance = AgentResourceTracker()
    return _resource_tracker_instance
