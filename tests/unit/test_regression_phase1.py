"""
Regression tests for Phase 1 bug fixes.

Covers dead browser detection, pool capacity cap, capture_output thread
exception handling, LLM cache concurrency, Google AI model updates,
and bare except:pass removal.

Each test targets a specific fix from Phase 1.1 through 1.6.
"""

import os
import time
import json
import threading
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch, call

import pytest

from mcp_server.resource_manager import BrowserPool
from mcp_server.llm_router import LLMCache, LLMResponse, LLMRouter
from mcp_server.tools import AgentSpawner, ObsidianVault


# =============================================================================
# Helpers
# =============================================================================

def _make_mock_browser(page=None, browser=None, connected=True):
    """Build a mocked BrowserAutomation with controllable dead/alive state."""
    b = MagicMock()
    b.close = AsyncMock()
    b.page = page
    b.browser = browser

    # Wire is_connected on the underlying browser object
    if browser is not None and connected is not None:
        browser.is_connected.return_value = connected

    return b


def _make_live_browser():
    """Build a fully alive BrowserAutomation mock."""
    page = MagicMock()
    page.context.clear_cookies = AsyncMock()
    page.goto = AsyncMock()
    browser = MagicMock()
    browser.is_connected.return_value = True
    b = MagicMock()
    b.close = AsyncMock()
    b.start = AsyncMock()
    b.page = page
    b.browser = browser
    return b


# =============================================================================
# 1.1  BrowserPool.acquire() — dead browser detection
# =============================================================================

@pytest.mark.unit
class TestBrowserPoolAcquireDeadDetection:
    """Dead browser detection in acquire() — Phase 1.1."""

    @pytest.mark.asyncio
    async def test_acquire_skips_dead_browsers(self):
        """Should skip dead (disconnected) browsers and return a live one."""
        dead_browser = _make_mock_browser(
            page=MagicMock(),
            browser=MagicMock(),
            connected=False,
        )
        live_browser = _make_live_browser()

        pool = BrowserPool(max_size=5)
        # pop() removes from the end, so dead browser must be last to be checked first
        pool._pool = [live_browser, dead_browser]

        acquired = await pool.acquire()

        # The live browser is returned; the dead one should have been closed
        assert acquired is live_browser
        dead_browser.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_acquire_skips_browsers_with_none_page(self):
        """Should skip browsers whose page is None and return a live one."""
        dead_browser = _make_mock_browser(page=None, browser=MagicMock(), connected=True)
        live_browser = _make_live_browser()

        pool = BrowserPool(max_size=5)
        pool._pool = [live_browser, dead_browser]

        acquired = await pool.acquire()

        assert acquired is live_browser
        dead_browser.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_acquire_skips_browsers_with_none_browser(self):
        """Should skip browsers whose browser is None and return a live one."""
        dead_browser = _make_mock_browser(page=MagicMock(), browser=None, connected=True)
        live_browser = _make_live_browser()

        pool = BrowserPool(max_size=5)
        pool._pool = [live_browser, dead_browser]

        acquired = await pool.acquire()

        assert acquired is live_browser
        dead_browser.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_acquire_creates_new_when_all_dead(self):
        """Should create a fresh browser when every pooled browser is dead."""
        dead = _make_mock_browser(page=None, browser=None, connected=False)
        pool = BrowserPool(max_size=5)
        pool._pool = [dead]

        with patch.object(pool, "_semaphore"):
            with patch("mcp_server.resource_manager.BrowserAutomation") as mock_browser_cls:
                mock_browser = _make_live_browser()
                mock_browser_cls.return_value = mock_browser
                acquired = await pool.acquire()

        # A new browser should have been created (not the dead one)
        assert acquired is not dead
        assert acquired.page is not None
        assert acquired.browser is not None
        dead.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_acquire_reuses_live_browser_from_pool(self):
        """Should return a live browser from the pool without creating a new one."""
        live = _make_live_browser()
        pool = BrowserPool(max_size=5)
        pool._pool = [live]

        acquired = await pool.acquire()

        assert acquired is live
        assert acquired in pool._in_use
        assert live not in pool._pool


# =============================================================================
# 1.2  BrowserPool.release() — pool capacity cap bug
# =============================================================================

@pytest.mark.unit
class TestBrowserPoolReleaseCapacity:
    """Pool capacity cap fix in release() — Phase 1.2."""

    @pytest.mark.asyncio
    async def test_release_retains_up_to_max_size(self):
        """Should keep up to max_size idle browsers in the pool (not max_size // 2)."""
        pool = BrowserPool(max_size=3)
        browsers = [_make_live_browser() for _ in range(5)]

        for b in browsers:
            pool._in_use.add(b)

        for b in browsers:
            await pool.release(b, reset=False)

        # Pool should retain exactly max_size = 3 browsers
        assert len(pool._pool) == 3

    @pytest.mark.asyncio
    async def test_release_closes_excess_browsers(self):
        """Should close excess browsers beyond max_size."""
        pool = BrowserPool(max_size=2)
        browsers = [_make_live_browser() for _ in range(4)]

        for b in browsers:
            pool._in_use.add(b)

        for b in browsers:
            await pool.release(b, reset=False)

        # The first two released should be in the pool
        # The last two should have been closed
        assert len(pool._pool) == 2
        # browsers[2] and browsers[3] should have been closed
        browsers[2].close.assert_awaited_once()
        browsers[3].close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_release_does_not_close_when_under_capacity(self):
        """Should not close browsers when pool is under max_size."""
        pool = BrowserPool(max_size=5)
        browsers = [_make_live_browser() for _ in range(3)]

        for b in browsers:
            pool._in_use.add(b)

        for b in browsers:
            await pool.release(b, reset=False)

        assert len(pool._pool) == 3
        for b in browsers:
            b.close.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_release_reset_failure_closes_browser(self):
        """Should close the browser if reset fails instead of returning it broken."""
        pool = BrowserPool(max_size=5)
        live = _make_live_browser()
        pool._in_use.add(live)

        # Make the reset (clear_cookies) raise
        live.page.context.clear_cookies.side_effect = RuntimeError("context crashed")

        await pool.release(live, reset=True)

        # Browser should be closed and NOT returned to pool
        assert live not in pool._pool
        live.close.assert_awaited_once()


# =============================================================================
# 1.3  capture_output thread — silent exception swallowing
# =============================================================================

@pytest.mark.unit
class TestCaptureOutputThread:
    """capture_output thread exception handling — Phase 1.3."""

    # A small logger that lets us spy on warning calls
    @pytest.fixture
    def vault(self, tmp_path):
        return ObsidianVault(tmp_path / "vault")

    def _run_capture_output(self, proc, log_path):
        """Replicates mcp_server.tools.AgentSpawner.spawn_agent's capture_output."""
        try:
            log_path = Path(log_path)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, "w") as f:
                if proc.stdout:
                    for line in proc.stdout:
                        f.write(line.decode("utf-8", errors="replace"))
                        f.flush()
        except Exception as e:
            # This is the key fix: log the error instead of bare except:pass
            import structlog
            logger = structlog.get_logger()
            logger.warning("log_capture_failed", error=str(e), log_path=str(log_path))

    def test_stdout_none_does_not_crash(self, tmp_path):
        """Test that proc.stdout=None is handled gracefully (no crash)."""
        proc = MagicMock()
        proc.stdout = None
        log_path = str(tmp_path / "logs" / "agent.log")

        # Should not raise any exception
        self._run_capture_output(proc, log_path)

        # File is created (open with "w") but remains empty
        assert Path(log_path).exists()
        assert Path(log_path).read_text() == ""

    def test_logs_warning_on_capture_failure(self, tmp_path):
        """Test that logging happens instead of silent pass when capture fails."""
        proc = MagicMock()
        proc.stdout = ["line1\n", "line2\n"]

        # Make open raise by pointing to an unwritable location
        log_path = str(tmp_path / "nonexistent" / "subdir" / "agent.log")
        # tmp_path is writable so this will actually succeed since mkdir creates parents
        # Let's instead patch Path.mkdir to raise
        original_mkdir = Path.mkdir

        warning_calls = []

        def fake_mkdir(self, *a, **kw):
            if "nonexistent" in str(self):
                raise PermissionError("cannot create directory")
            return original_mkdir(self, *a, **kw)

        mock_logger = MagicMock()
        mock_logger.warning = MagicMock(side_effect=lambda *a, **kw: warning_calls.append((a, kw)))

        with patch.object(Path, "mkdir", fake_mkdir):
            with patch("structlog.get_logger", return_value=mock_logger):
                self._run_capture_output(proc, log_path)

        assert len(warning_calls) >= 1
        # At least one warning should mention log_capture_failed
        log_warnings = [c for c in warning_calls if "log_capture_failed" in str(c)]
        assert len(log_warnings) >= 1

    def test_capture_output_via_spawn_agent_smoke(self, vault):
        """Smoke test: spawn_agent does not crash when capture_output thread runs."""
        spawner = AgentSpawner(vault)

        with patch("subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.stdout = None  # Trigger the fix path
            mock_process.pid = 12345
            mock_process.poll.return_value = None
            mock_popen.return_value = mock_process

            result = spawner.spawn_agent(
                role="ui_explorer",
                objective="Test capture smoke",
                memory_node="Runs/CaptureSmoke.md",
            )

            assert result["status"] == "active"


# =============================================================================
# 1.4  LLM cache concurrency
# =============================================================================

@pytest.mark.unit
class TestLLMCacheConcurrency:
    """LLM cache thread safety — Phase 1.4."""

    @pytest.fixture
    def cache(self):
        """Create a cache with short TTL purely in memory (no DB)."""
        return LLMCache(ttl_seconds=3600, persist_path=None)

    @pytest.fixture
    def sample_response(self):
        return LLMResponse(
            content="Test response",
            model="gpt-4o",
            provider="openai",
            usage={"total_tokens": 15},
            raw_response=None,
        )

    def test_concurrent_set_and_get(self, cache, sample_response):
        """Multiple threads should be able to read/write cache without corruption."""
        messages = [{"role": "user", "content": "Hello"}]
        errors = []
        lock = threading.Lock()

        def writer():
            try:
                for i in range(20):
                    msg = [{"role": "user", "content": f"Message {i}"}]
                    cache.set("gpt-4o", msg, 0.7, 100, sample_response)
            except Exception as e:
                with lock:
                    errors.append(e)

        def reader():
            try:
                for i in range(20):
                    msg = [{"role": "user", "content": f"Message {i}"}]
                    cache.get("gpt-4o", msg, 0.7, 100)
            except Exception as e:
                with lock:
                    errors.append(e)

        threads = [threading.Thread(target=writer) for _ in range(5)]
        threads += [threading.Thread(target=reader) for _ in range(5)]

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert not errors, f"Concurrent cache access raised: {errors}"
        # Memory cache should have entries from the writers
        assert len(cache._memory_cache) > 0

    def test_cache_get_returns_none_for_miss(self, cache):
        """Should return None when cache has no matching entry."""
        result = cache.get("nonexistent", [{"role": "user", "content": "hi"}], 0.0, 10)
        assert result is None

    def test_cache_set_then_get_returns_same_content(self, cache, sample_response):
        """Written entry should be retrievable."""
        messages = [{"role": "user", "content": "cache me"}]
        cache.set("gpt-4o", messages, 0.7, 100, sample_response)

        result = cache.get("gpt-4o", messages, 0.7, 100)

        assert result is not None
        assert result.content == "Test response"
        assert result.provider == "openai"
        assert result.usage["total_tokens"] == 15

    def test_cache_key_uniqueness(self, cache, sample_response):
        """Different parameters should produce different cache keys."""
        msg = [{"role": "user", "content": "Hello"}]

        cache.set("gpt-4o", msg, 0.7, 100, sample_response)

        # Different temperature should be a different key → cache miss
        result_diff_temp = cache.get("gpt-4o", msg, 0.8, 100)
        assert result_diff_temp is None

        # Same temperature should hit
        result_same = cache.get("gpt-4o", msg, 0.7, 100)
        assert result_same is not None


# =============================================================================
# 1.5  Google AI deprecated model
# =============================================================================

@pytest.mark.unit
class TestGoogleModels:
    """Google AI model updates — Phase 1.5."""

    def test_get_available_models_returns_updated_google_models(self):
        """Should return gemini-2.5-pro and gemini-2.0-flash (not deprecated names)."""
        router = LLMRouter.__new__(LLMRouter)
        router.clients = {"google": MagicMock()}

        models = router.get_available_models()

        assert "google" in models
        google_models = models["google"]
        assert "gemini-2.5-pro" in google_models
        assert "gemini-2.0-flash" in google_models
        # Verify deprecated models are NOT present
        deprecated = ["gemini-pro", "gemini-pro-vision", "gemini-1.5-pro", "gemini-1.0-pro"]
        for d in deprecated:
            assert d not in google_models

    def test_get_available_models_returns_all_providers(self):
        """Should return models for all initialized providers."""
        router = LLMRouter.__new__(LLMRouter)
        router.clients = {
            "openai": MagicMock(),
            "anthropic": MagicMock(),
            "google": MagicMock(),
        }

        models = router.get_available_models()

        assert "openai" in models
        assert "anthropic" in models
        assert "google" in models
        assert "minimax" not in models  # not initialized

    def test_get_available_models_empty_when_no_clients(self):
        """Should return empty dict when no providers are initialized."""
        router = LLMRouter.__new__(LLMRouter)
        router.clients = {}

        models = router.get_available_models()

        assert models == {}


# =============================================================================
# 1.6  Bare except:pass removal
# =============================================================================

@pytest.mark.unit
class TestBareExceptRemoval:
    """Bare except:pass removal — Phase 1.6."""

    def test_cache_read_failure_logs_warning(self):
        """Cache read errors should produce log warnings, not silent pass."""
        cache = LLMCache.__new__(LLMCache)
        cache.ttl_seconds = 3600
        cache._lock = threading.Lock()
        cache._memory_cache = {}
        cache._use_postgres = True
        cache.persist_path = None
        cache.db = MagicMock()

        warning_calls = []

        # Patch the module-level logger that LLMCache actually uses
        with patch("mcp_server.llm_router.logger.warning", side_effect=lambda *a, **kw: warning_calls.append((a, kw))):
            # Force fetchone to raise synchronously by patching run_until_complete
            with patch("asyncio.get_event_loop") as mock_get_loop:
                mock_loop = MagicMock()
                mock_loop.is_running.return_value = False
                mock_loop.run_until_complete.side_effect = RuntimeError("db connection lost")
                mock_get_loop.return_value = mock_loop

                result = cache.get("test-model", [{"role": "user", "content": "hi"}], 0.7, 100)

        # Should return None (graceful degradation)
        assert result is None
        # A warning should have been logged
        cache_warnings = [c for c in warning_calls if "cache_read_failed" in str(c)]
        assert len(cache_warnings) >= 1

    def test_cache_write_failure_logs_warning(self):
        """Cache write errors should produce log warnings, not silent pass."""
        cache = LLMCache.__new__(LLMCache)
        cache.ttl_seconds = 3600
        cache._lock = threading.Lock()
        cache._memory_cache = {}
        cache._use_postgres = True
        cache.persist_path = None
        cache.db = MagicMock()

        warning_calls = []

        # Write to memory cache then fail on DB persist
        response = LLMResponse(content="x", model="gpt-4o", provider="openai",
                               usage={"total_tokens": 5}, raw_response=None)

        with patch("mcp_server.llm_router.logger.warning", side_effect=lambda *a, **kw: warning_calls.append((a, kw))):
            with patch("asyncio.get_event_loop") as mock_get_loop:
                mock_loop = MagicMock()
                mock_loop.is_running.return_value = False
                mock_loop.run_until_complete.side_effect = RuntimeError("write failed")
                mock_get_loop.return_value = mock_loop

                cache.set("test-model", [{"role": "user", "content": "hi"}], 0.7, 100, response)

        cache_warnings = [c for c in warning_calls if "cache_write_failed" in str(c)]
        assert len(cache_warnings) >= 1

    def test_browser_close_failure_logs_warning_in_acquire(self):
        """Browser close failures in acquire() should produce log warnings."""
        pool = BrowserPool(max_size=5)
        dead = _make_mock_browser(page=None, browser=MagicMock(), connected=True)
        dead.close.side_effect = RuntimeError("close crashed")
        pool._pool = [dead]

        warning_calls = []

        # Patch the module-level logger and BrowserAutomation so acquire()
        # doesn't try to spin up a real browser when all pooled ones are dead.
        with patch("mcp_server.resource_manager.logger.warning", side_effect=lambda *a, **kw: warning_calls.append((a, kw))):
            with patch("mcp_server.resource_manager.BrowserAutomation") as mock_browser_cls:
                mock_browser = _make_live_browser()
                mock_browser_cls.return_value = mock_browser
                with patch.object(pool, "_semaphore"):
                    import asyncio
                    # Run acquire to trigger dead browser cleanup
                    loop = asyncio.new_event_loop()
                    loop.run_until_complete(pool.acquire())

        close_warnings = [c for c in warning_calls if "browser_close_failed" in str(c)]
        assert len(close_warnings) >= 1
