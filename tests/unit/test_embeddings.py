"""
Unit tests for the multi-provider embedding system (mcp_server.embeddings).

Tests all three providers (OpenAI, sentence-transformers, Ollama), their
initialization, embed methods, fallback behaviour, and error handling.
No real network requests are made — all external calls are mocked.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock


# ---------------------------------------------------------------------------
#  OpenAIEmbeddingProvider Tests
# ---------------------------------------------------------------------------

class TestOpenAIEmbeddingProvider:
    """Tests for the OpenAI API embedding provider."""

    @pytest.fixture
    def provider(self):
        """Create an OpenAIEmbeddingProvider with default model."""
        from mcp_server.embeddings import OpenAIEmbeddingProvider

        return OpenAIEmbeddingProvider()

    @pytest.mark.unit
    def test_init_sets_default_dimension(self):
        """Should set dimension to 1536 for text-embedding-3-small."""
        from mcp_server.embeddings import OpenAIEmbeddingProvider

        provider = OpenAIEmbeddingProvider()
        assert provider.dimension == 1536
        assert provider.model == "text-embedding-3-small"

    @pytest.mark.unit
    def test_init_sets_large_dimension_for_large_model(self):
        """Should set dimension to 3072 for text-embedding-3-large."""
        from mcp_server.embeddings import OpenAIEmbeddingProvider

        provider = OpenAIEmbeddingProvider(model="text-embedding-3-large")
        assert provider.dimension == 3072

    @pytest.mark.unit
    async def test_embed_returns_embedding_result(self, provider):
        """Should embed texts via OpenAI API and return an EmbeddingResult."""
        mock_embedding_item = MagicMock()
        mock_embedding_item.embedding = [0.1, 0.2, 0.3]

        mock_usage = MagicMock()
        mock_usage.total_tokens = 15

        mock_response = MagicMock()
        mock_response.data = [mock_embedding_item, mock_embedding_item]
        mock_response.usage = mock_usage

        mock_client = AsyncMock()
        mock_client.embeddings.create = AsyncMock(return_value=mock_response)

        with patch("openai.AsyncOpenAI", return_value=mock_client):
            result = await provider.embed(["hello", "world"])

        assert result.provider == "openai"
        assert result.model == "text-embedding-3-small"
        assert result.total_tokens == 15
        assert len(result.embeddings) == 2
        assert result.embeddings[0] == [0.1, 0.2, 0.3]

    @pytest.mark.unit
    async def test_embed_raises_on_api_error(self, provider):
        """Should raise when the OpenAI API call fails."""
        mock_client = AsyncMock()
        mock_client.embeddings.create = AsyncMock(
            side_effect=RuntimeError("API rate limit exceeded")
        )

        with patch("openai.AsyncOpenAI", return_value=mock_client):
            with pytest.raises(RuntimeError, match="API rate limit exceeded"):
                await provider.embed(["hello"])

    @pytest.mark.unit
    async def test_embed_raises_when_openai_not_installed(self, provider):
        """Should raise RuntimeError when the openai package is missing."""
        with patch("openai.AsyncOpenAI", side_effect=ImportError("no openai")):
            with pytest.raises(RuntimeError, match="openai package not installed"):
                await provider.embed(["test"])


# ---------------------------------------------------------------------------
#  SentenceTransformersProvider Tests
# ---------------------------------------------------------------------------

class TestSentenceTransformersProvider:
    """Tests for the local sentence-transformers embedding provider."""

    @pytest.fixture
    def provider(self):
        """Create a SentenceTransformersProvider with default model."""
        from mcp_server.embeddings import SentenceTransformersProvider

        return SentenceTransformersProvider()

    @pytest.mark.unit
    def test_init_sets_default_dimension(self):
        """Should default to 384 dimensions for all-MiniLM-L6-v2."""
        from mcp_server.embeddings import SentenceTransformersProvider

        provider = SentenceTransformersProvider()
        assert provider.dimension == 384
        assert provider.model_name == "all-MiniLM-L6-v2"

    @pytest.mark.unit
    async def test_embed_returns_embedding_result(self, provider):
        """Should embed texts locally and return an EmbeddingResult."""
        mock_model = MagicMock()
        # encode returns numpy arrays — mock .tolist() conversion
        mock_embedding_1 = MagicMock()
        mock_embedding_1.tolist.return_value = [0.5, 0.6, 0.7]
        mock_embedding_2 = MagicMock()
        mock_embedding_2.tolist.return_value = [0.8, 0.9, 1.0]

        mock_model.encode.return_value = [mock_embedding_1, mock_embedding_2]
        mock_model.get_sentence_embedding_dimension.return_value = 384

        with patch(
            "sentence_transformers.SentenceTransformer",
            return_value=mock_model,
        ):
            result = await provider.embed(["text one", "text two"])

        assert result.provider == "local"
        assert result.model == "all-MiniLM-L6-v2"
        assert len(result.embeddings) == 2
        assert result.embeddings[0] == [0.5, 0.6, 0.7]
        assert result.embeddings[1] == [0.8, 0.9, 1.0]
        assert isinstance(result.total_tokens, int)

    @pytest.mark.unit
    async def test_embed_raises_when_sentence_transformers_not_installed(self, provider):
        """Should raise RuntimeError when sentence-transformers is missing."""
        with patch(
            "sentence_transformers.SentenceTransformer",
            side_effect=ImportError("no sentence-transformers"),
        ):
            with pytest.raises(RuntimeError, match="sentence-transformers not installed"):
                await provider.embed(["test"])


# ---------------------------------------------------------------------------
#  OllamaEmbeddingProvider Tests
# ---------------------------------------------------------------------------

class TestOllamaEmbeddingProvider:
    """Tests for the Ollama self-hosted embedding provider."""

    @pytest.fixture
    def provider(self):
        """Create an OllamaEmbeddingProvider with default model."""
        from mcp_server.embeddings import OllamaEmbeddingProvider

        return OllamaEmbeddingProvider()

    @pytest.mark.unit
    def test_init_sets_default_values(self):
        """Should set default model and dimension for nomic-embed-text."""
        from mcp_server.embeddings import OllamaEmbeddingProvider

        provider = OllamaEmbeddingProvider()
        assert provider.model == "nomic-embed-text"
        assert provider.dimension == 768

    @pytest.mark.unit
    async def test_embed_returns_embedding_result(self, provider):
        """Should embed texts via the Ollama API and return an EmbeddingResult."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"embedding": [0.1, 0.2, 0.3]}

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await provider.embed(["hello world"])

        assert result.provider == "ollama"
        assert result.model == "nomic-embed-text"
        assert len(result.embeddings) == 1
        assert result.embeddings[0] == [0.1, 0.2, 0.3]
        assert isinstance(result.total_tokens, int)

    @pytest.mark.unit
    async def test_embed_raises_on_ollama_error(self, provider):
        """Should raise when the Ollama API call fails."""
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post = AsyncMock(
            side_effect=RuntimeError("Ollama service unavailable")
        )

        with patch("httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(RuntimeError, match="Ollama service unavailable"):
                await provider.embed(["hello"])

    @pytest.mark.unit
    async def test_embed_raises_on_http_error_status(self, provider):
        """Should raise when Ollama returns a non-2xx status code."""
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = RuntimeError("HTTP 500")

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(RuntimeError, match="HTTP 500"):
                await provider.embed(["hello"])


# ---------------------------------------------------------------------------
#  Factory function tests
# ---------------------------------------------------------------------------

class TestGetEmbeddingProvider:
    """Tests for the get_embedding_provider() factory singleton."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset the _embedding_provider singleton before each test."""
        import mcp_server.embeddings as emb_mod

        emb_mod._embedding_provider = None
        yield
        emb_mod._embedding_provider = None

    @pytest.mark.unit
    def test_get_provider_returns_openai_by_default(self):
        """Should create an OpenAIEmbeddingProvider when EMBEDDING_PROVIDER is 'openai'."""
        with patch("mcp_server.embeddings.EMBEDDING_PROVIDER", "openai"):
            from mcp_server.embeddings import get_embedding_provider, OpenAIEmbeddingProvider

            provider = get_embedding_provider()
            assert isinstance(provider, OpenAIEmbeddingProvider)

    @pytest.mark.unit
    def test_get_provider_returns_local(self):
        """Should create a SentenceTransformersProvider when EMBEDDING_PROVIDER is 'local'."""
        with patch("mcp_server.embeddings.EMBEDDING_PROVIDER", "local"):
            from mcp_server.embeddings import (
                get_embedding_provider,
                SentenceTransformersProvider,
            )

            provider = get_embedding_provider()
            assert isinstance(provider, SentenceTransformersProvider)

    @pytest.mark.unit
    def test_get_provider_returns_ollama(self):
        """Should create an OllamaEmbeddingProvider when EMBEDDING_PROVIDER is 'ollama'."""
        with patch("mcp_server.embeddings.EMBEDDING_PROVIDER", "ollama"):
            from mcp_server.embeddings import get_embedding_provider, OllamaEmbeddingProvider

            provider = get_embedding_provider()
            assert isinstance(provider, OllamaEmbeddingProvider)

    @pytest.mark.unit
    def test_get_provider_falls_back_to_openai_for_unknown(self):
        """Should fall back to OpenAI when an unknown provider is configured."""
        with patch("mcp_server.embeddings.EMBEDDING_PROVIDER", "invalid_provider"):
            from mcp_server.embeddings import get_embedding_provider, OpenAIEmbeddingProvider

            provider = get_embedding_provider()
            assert isinstance(provider, OpenAIEmbeddingProvider)

    @pytest.mark.unit
    def test_get_provider_returns_singleton(self):
        """Should return the same instance on repeated calls."""
        with patch("mcp_server.embeddings.EMBEDDING_PROVIDER", "openai"):
            from mcp_server.embeddings import get_embedding_provider

            first = get_embedding_provider()
            second = get_embedding_provider()
            assert first is second
