"""
Extended unit tests for LLM Router.

Tests cover:
- Cache hit/miss paths
- Cost tracking
- Provider fallback behavior
- Disk cache persistence
"""

import os
import pytest
import time
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, mock_open

from mcp_server.llm_router import LLMRouter, LLMResponse, LLMCache


# ──────────────────────────────────────────────
# LLMCache
# ──────────────────────────────────────────────


class TestLLMCacheHitMiss:
    """Test cache hit and miss behavior."""

    @pytest.fixture
    def cache(self):
        """Create a cache without postgres or disk."""
        return LLMCache(ttl_seconds=3600, persist_path=None)

    @pytest.mark.unit
    def test_cache_miss_empty(self, cache):
        """Should return None when cache is empty."""
        result = cache.get("openai/gpt-4o", [{"role": "user", "content": "Hello"}], 0.7, 100)
        assert result is None

    @pytest.mark.unit
    def test_cache_hit_memory(self, cache):
        """Should return cached response from memory."""
        response = LLMResponse(
            content="Cached hello",
            model="gpt-4o",
            provider="openai",
            usage={"total_tokens": 10},
            raw_response=None,
        )
        cache.set("openai/gpt-4o", [{"role": "user", "content": "Hello"}], 0.7, 100, response)

        result = cache.get("openai/gpt-4o", [{"role": "user", "content": "Hello"}], 0.7, 100)

        assert result is not None
        assert result.content == "Cached hello"
        assert result.model == "gpt-4o"
        assert result.provider == "openai"

    @pytest.mark.unit
    def test_cache_miss_different_params(self, cache):
        """Should miss when parameters differ."""
        response = LLMResponse(
            content="Cached hello",
            model="gpt-4o",
            provider="openai",
            usage={"total_tokens": 10},
            raw_response=None,
        )
        cache.set("openai/gpt-4o", [{"role": "user", "content": "Hello"}], 0.7, 100, response)

        result = cache.get("openai/gpt-4o", [{"role": "user", "content": "Different"}], 0.7, 100)
        assert result is None

    @pytest.mark.unit
    def test_cache_expired(self, cache):
        """Should miss when cache entry is expired."""
        response = LLMResponse(
            content="Cached hello",
            model="gpt-4o",
            provider="openai",
            usage={"total_tokens": 10},
            raw_response=None,
        )
        cache.ttl_seconds = 1
        cache.set("openai/gpt-4o", [{"role": "user", "content": "Hello"}], 0.7, 100, response)

        time.sleep(1.1)

        result = cache.get("openai/gpt-4o", [{"role": "user", "content": "Hello"}], 0.7, 100)
        assert result is None

    @pytest.mark.unit
    def test_cache_clear(self, cache):
        """Should clear all cached entries."""
        response = LLMResponse(
            content="Cached hello",
            model="gpt-4o",
            provider="openai",
            usage={"total_tokens": 10},
            raw_response=None,
        )
        cache.set("model1", [{"role": "user", "content": "Hello"}], 0.7, 100, response)
        cache.set("model2", [{"role": "user", "content": "Hello"}], 0.7, 100, response)

        cache.clear()

        assert cache.get("model1", [{"role": "user", "content": "Hello"}], 0.7, 100) is None
        assert cache.get("model2", [{"role": "user", "content": "Hello"}], 0.7, 100) is None

    @pytest.mark.unit
    def test_cache_key_generation_consistency(self, cache):
        """Should generate same key for same params."""
        key1 = cache._generate_key("model", [{"role": "user", "content": "Hello"}], 0.7, 100)
        key2 = cache._generate_key("model", [{"role": "user", "content": "Hello"}], 0.7, 100)
        assert key1 == key2

    @pytest.mark.unit
    def test_cache_key_generation_uniqueness(self, cache):
        """Should generate different keys for different params."""
        key1 = cache._generate_key("model", [{"role": "user", "content": "Hello"}], 0.7, 100)
        key2 = cache._generate_key("model", [{"role": "user", "content": "World"}], 0.7, 100)
        assert key1 != key2


class TestLLMCacheDiskPersistence:
    """Test disk-based cache persistence."""

    @pytest.mark.unit
    def test_save_to_disk(self):
        """Should persist cache to disk."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            path = f.name

        try:
            cache = LLMCache(ttl_seconds=3600, persist_path=path)
            response = LLMResponse(
                content="Hello",
                model="gpt-4o",
                provider="openai",
                usage={"total_tokens": 5},
                raw_response=None,
            )
            cache.set("model", [{"role": "user", "content": "Hi"}], 0.7, 100, response)

            assert Path(path).exists()
            with open(path, "r") as f:
                data = json.load(f)
            assert len(data) == 1
        finally:
            Path(path).unlink(missing_ok=True)

    @pytest.mark.unit
    def test_load_from_disk(self):
        """Should load cache from disk."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            path = f.name

        try:
            # Pre-populate cache file
            cache_data = {
                "key1": {
                    "content": "Cached response",
                    "model": "gpt-4o",
                    "provider": "openai",
                    "usage": {"total_tokens": 10},
                    "timestamp": time.time(),
                }
            }
            with open(path, "w") as f:
                json.dump(cache_data, f)

            cache = LLMCache(ttl_seconds=3600, persist_path=path)
            result = cache.get("model", [{"role": "user", "content": "Hi"}], 0.7, 100)
            # Note: keys are generated from params, so direct key lookup won't match
            # unless we use the same key. Let's verify load happened by checking memory.
            assert len(cache._memory_cache) >= 1
        finally:
            Path(path).unlink(missing_ok=True)

    @pytest.mark.unit
    def test_load_from_disk_expired_entries(self):
        """Should filter expired entries when loading from disk."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            path = f.name

        try:
            cache_data = {
                "fresh": {
                    "content": "Fresh",
                    "model": "gpt-4o",
                    "provider": "openai",
                    "usage": {},
                    "timestamp": time.time(),
                },
                "expired": {
                    "content": "Expired",
                    "model": "gpt-4o",
                    "provider": "openai",
                    "usage": {},
                    "timestamp": time.time() - 10000,
                },
            }
            with open(path, "w") as f:
                json.dump(cache_data, f)

            cache = LLMCache(ttl_seconds=3600, persist_path=path)
            assert "expired" not in cache._memory_cache
            assert "fresh" in cache._memory_cache
        finally:
            Path(path).unlink(missing_ok=True)

    @pytest.mark.unit
    def test_load_from_disk_missing_file(self):
        """Should handle missing file gracefully."""
        cache = LLMCache(ttl_seconds=3600, persist_path="/nonexistent/path/cache.json")
        # Should not raise
        assert cache._memory_cache == {}

    @pytest.mark.unit
    def test_clear_removes_disk_file(self):
        """Should remove disk file on clear."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            path = f.name

        try:
            cache = LLMCache(ttl_seconds=3600, persist_path=path)
            response = LLMResponse(
                content="Hello", model="gpt-4o", provider="openai", usage={}, raw_response=None
            )
            cache.set("m", [{"role": "u", "content": "h"}], 0.7, 100, response)
            cache.clear()
            assert not Path(path).exists()
        finally:
            Path(path).unlink(missing_ok=True)

    @pytest.mark.unit
    def test_disk_save_error_handling(self):
        """Should handle disk save errors gracefully."""
        with patch("pathlib.Path.mkdir", side_effect=OSError("Permission denied")):
            cache = LLMCache(ttl_seconds=3600, persist_path="/fake/path.json")
            response = LLMResponse(
                content="Hello", model="gpt-4o", provider="openai", usage={}, raw_response=None
            )
            # Should not raise
            cache.set("m", [{"role": "u", "content": "h"}], 0.7, 100, response)


class TestLLMCachePostgresFallback:
    """Test cache behavior when postgres is unavailable."""

    @pytest.mark.unit
    def test_init_postgres_failure(self):
        """Should handle postgres initialization failure."""
        with patch("mcp_server.db.get_db_manager_sync", side_effect=ImportError("No db")):
            cache = LLMCache(ttl_seconds=3600, persist_path=None)
            assert cache._use_postgres is False

    @pytest.mark.unit
    def test_get_with_postgres_error(self):
        """Should handle postgres read errors gracefully."""
        cache = LLMCache(ttl_seconds=3600, persist_path=None)
        cache._use_postgres = True
        cache.db = MagicMock()
        cache.db.fetchone.side_effect = Exception("DB error")

        result = cache.get("model", [{"role": "user", "content": "Hello"}], 0.7, 100)
        assert result is None

    @pytest.mark.unit
    def test_set_with_postgres_error(self):
        """Should handle postgres write errors gracefully."""
        cache = LLMCache(ttl_seconds=3600, persist_path=None)
        cache._use_postgres = True
        cache.db = MagicMock()
        cache.db.execute.side_effect = Exception("DB error")

        response = LLMResponse(
            content="Hello", model="gpt-4o", provider="openai", usage={}, raw_response=None
        )
        # Should not raise
        cache.set("model", [{"role": "user", "content": "Hello"}], 0.7, 100, response)
        assert len(cache._memory_cache) == 1


# ──────────────────────────────────────────────
# LLMRouter Complete with Cache
# ──────────────────────────────────────────────


class TestLLMRouterCacheIntegration:
    """Test LLMRouter integration with cache."""

    @pytest.mark.unit
    def test_complete_cache_hit(self):
        """Should return cached response on cache hit."""
        router = LLMRouter.__new__(LLMRouter)
        router.clients = {"openai": MagicMock()}
        cached_response = LLMResponse(
            content="Cached",
            model="gpt-4o",
            provider="openai",
            usage={"total_tokens": 0},
            raw_response=None,
        )
        router.cache = MagicMock()
        router.cache.get.return_value = cached_response

        with patch("mcp_server.cost_tracker.get_cost_tracker") as mock_tracker:
            result = router.complete(
                model="openai/gpt-4o",
                messages=[{"role": "user", "content": "Hello"}],
            )

        assert result.content == "Cached"
        router.cache.get.assert_called_once()
        # Verify cost tracker was called for cache hit
        mock_tracker.return_value.track_usage.assert_called_once_with(
            model="openai/gpt-4o",
            input_tokens=0,
            output_tokens=0,
            provider="cache",
            cache_hit=True,
        )

    @pytest.mark.unit
    def test_complete_cache_miss(self):
        """Should call provider and cache response on miss."""
        router = LLMRouter.__new__(LLMRouter)
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Fresh response"))]
        mock_response.usage.prompt_tokens = 10
        mock_response.usage.completion_tokens = 5
        mock_response.usage.total_tokens = 15
        mock_client.chat.completions.create.return_value = mock_response
        router.clients = {"openai": mock_client}
        router.cache = MagicMock()
        router.cache.get.return_value = None

        with patch("mcp_server.cost_tracker.get_cost_tracker") as mock_tracker:
            result = router.complete(
                model="openai/gpt-4o",
                messages=[{"role": "user", "content": "Hello"}],
            )

        assert result.content == "Fresh response"
        router.cache.set.assert_called_once()
        mock_tracker.return_value.track_usage.assert_called_once()

    @pytest.mark.unit
    def test_complete_no_cache(self):
        """Should work without cache."""
        router = LLMRouter.__new__(LLMRouter)
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="No cache"))]
        mock_response.usage.prompt_tokens = 5
        mock_response.usage.completion_tokens = 3
        mock_response.usage.total_tokens = 8
        mock_client.chat.completions.create.return_value = mock_response
        router.clients = {"openai": mock_client}
        router.cache = None

        result = router.complete(
            model="openai/gpt-4o",
            messages=[{"role": "user", "content": "Hello"}],
        )

        assert result.content == "No cache"


class TestLLMRouterCostTracking:
    """Test cost tracking behavior."""

    @pytest.mark.unit
    def test_cost_tracking_success(self):
        """Should track usage on successful completion."""
        router = LLMRouter.__new__(LLMRouter)
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Hello"))]
        mock_response.usage.prompt_tokens = 10
        mock_response.usage.completion_tokens = 5
        mock_response.usage.total_tokens = 15
        mock_client.chat.completions.create.return_value = mock_response
        router.clients = {"openai": mock_client}
        router.cache = None

        with patch("mcp_server.cost_tracker.get_cost_tracker") as mock_tracker:
            router.complete(
                model="openai/gpt-4o",
                messages=[{"role": "user", "content": "Hello"}],
            )

            mock_tracker.return_value.track_usage.assert_called_once_with(
                model="openai/gpt-4o",
                input_tokens=10,
                output_tokens=5,
                provider="openai",
            )

    @pytest.mark.unit
    def test_cost_tracking_failure(self):
        """Should handle cost tracker failure gracefully."""
        router = LLMRouter.__new__(LLMRouter)
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Hello"))]
        mock_response.usage.prompt_tokens = 10
        mock_response.usage.completion_tokens = 5
        mock_response.usage.total_tokens = 15
        mock_client.chat.completions.create.return_value = mock_response
        router.clients = {"openai": mock_client}
        router.cache = None

        with patch("mcp_server.cost_tracker.get_cost_tracker", side_effect=Exception("Tracker error")):
            result = router.complete(
                model="openai/gpt-4o",
                messages=[{"role": "user", "content": "Hello"}],
            )
            assert result.content == "Hello"


class TestLLMRouterProviderFallback:
    """Test provider fallback and error handling."""

    @pytest.mark.unit
    def test_unknown_provider(self):
        """Should raise error for unknown provider."""
        router = LLMRouter.__new__(LLMRouter)
        router.clients = {}

        with pytest.raises(ValueError, match="not initialized"):
            router.complete(
                model="unknown/model",
                messages=[{"role": "user", "content": "Hello"}],
            )

    @pytest.mark.unit
    def test_uninitialized_provider(self):
        """Should raise error for uninitialized provider."""
        router = LLMRouter.__new__(LLMRouter)
        router.clients = {"openai": None}

        with pytest.raises(ValueError, match="not initialized"):
            router.complete(
                model="minimax/model",
                messages=[{"role": "user", "content": "Hello"}],
            )

    @pytest.mark.unit
    def test_google_completion(self):
        """Should handle Google provider completion."""
        router = LLMRouter.__new__(LLMRouter)
        mock_genai = MagicMock()
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "Google response"
        mock_model.generate_content.return_value = mock_response
        mock_genai.GenerativeModel.return_value = mock_model
        router.clients = {"google": mock_genai}
        router.cache = None

        result = router._google_complete(
            model="gemini-2.5-pro",
            messages=[{"role": "user", "content": "Hello"}],
            temperature=0.7,
            max_tokens=100,
        )

        assert result.content == "Google response"
        assert result.provider == "google"

    @pytest.mark.unit
    def test_get_available_models(self):
        """Should return available models per provider."""
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
        assert "gpt-4o" in models["openai"]
        assert "claude-3-5-sonnet-20241022" in models["anthropic"]

    @pytest.mark.unit
    def test_get_available_models_empty(self):
        """Should return empty dict when no clients initialized."""
        router = LLMRouter.__new__(LLMRouter)
        router.clients = {}

        models = router.get_available_models()
        assert models == {}


class TestLLMRouterInitialization:
    """Test router client initialization."""

    @pytest.mark.unit
    def test_init_with_env_vars(self):
        """Should initialize clients from environment variables."""
        env = {
            "OPENAI_API_KEY": "test-key",
            "MINIMAX_API_KEY": "test-key",
            "KIMI_API_KEY": "test-key",
            "LOCAL_LLM_BASE_URL": "http://localhost:11434",
        }
        with patch.dict(os.environ, env, clear=True):
            with patch("openai.OpenAI") as mock_openai:
                router = LLMRouter(cache_enabled=False)
                assert "openai" in router.clients
                assert "minimax" in router.clients
                assert "kimi" in router.clients
                assert "local" in router.clients

    @pytest.mark.unit
    def test_init_without_env_vars(self):
        """Should not initialize clients without API keys."""
        with patch.dict(os.environ, {}, clear=True):
            router = LLMRouter(cache_enabled=False)
            assert router.clients == {}

    @pytest.mark.unit
    def test_cache_disabled(self):
        """Should not create cache when disabled."""
        with patch.dict(os.environ, {"VECTRA_LLM_CACHE": "false"}, clear=True):
            router = LLMRouter(cache_enabled=True)
            assert router.cache is None
