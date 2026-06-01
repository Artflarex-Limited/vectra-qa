"""
Multi-provider embedding system for Vectra QA RAG.

Supports:
- OpenAI (cloud API, text-embedding-3-small, 1536 dims)
- sentence-transformers (local CPU, all-MiniLM-L6-v2, 384 dims)
- Ollama (self-hosted, nomic-embed-text)

Usage:
    from mcp_server.embeddings import get_embedding_provider

    provider = get_embedding_provider()
    embeddings = await provider.embed(["text to embed", "another text"])
"""

import os
import asyncio
from abc import ABC, abstractmethod
from typing import List, Optional
from dataclasses import dataclass

import structlog

logger = structlog.get_logger()

# Configuration
EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "openai")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
OLLAMA_EMBEDDING_URL = os.getenv("OLLAMA_EMBEDDING_URL", "http://localhost:11434/api/embeddings")
OLLAMA_EMBEDDING_MODEL = os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text")


@dataclass
class EmbeddingResult:
    """Result from an embedding provider."""

    embeddings: List[List[float]]
    model: str
    provider: str
    total_tokens: int = 0


class EmbeddingProvider(ABC):
    """Abstract base class for embedding providers."""

    @abstractmethod
    async def embed(self, texts: List[str]) -> EmbeddingResult:
        """Embed a list of texts into vectors."""
        pass

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Return the dimension of embeddings."""
        pass


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """OpenAI API embedding provider."""

    def __init__(self, model: str = EMBEDDING_MODEL):
        self.model = model
        self.dimension = 1536 if "3-small" in model else 3072
        self._client = None

    @property
    def dimension(self) -> int:
        return self._dimension

    @dimension.setter
    def dimension(self, value: int):
        self._dimension = value

    async def embed(self, texts: List[str]) -> EmbeddingResult:
        """Embed texts using OpenAI API."""
        if self._client is None:
            try:
                import openai

                self._client = openai.AsyncOpenAI()
            except ImportError:
                raise RuntimeError("openai package not installed. Run: pip install openai")

        try:
            response = await self._client.embeddings.create(
                model=self.model,
                input=texts,
            )
            embeddings = [item.embedding for item in response.data]
            total_tokens = response.usage.total_tokens

            logger.debug(
                "openai_embeddings_created",
                model=self.model,
                count=len(texts),
                tokens=total_tokens,
            )

            return EmbeddingResult(
                embeddings=embeddings,
                model=self.model,
                provider="openai",
                total_tokens=total_tokens,
            )
        except Exception as e:
            logger.error("openai_embedding_error", error=str(e))
            raise


class SentenceTransformersProvider(EmbeddingProvider):
    """Local embedding provider using sentence-transformers."""

    def __init__(self, model: str = "all-MiniLM-L6-v2"):
        self.model_name = model
        self._model = None
        self._dimension = 384  # all-MiniLM-L6-v2

    @property
    def dimension(self) -> int:
        return self._dimension

    def _load_model(self):
        """Lazy load the model."""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer

                self._model = SentenceTransformer(self.model_name)
                self._dimension = self._model.get_sentence_embedding_dimension()
                logger.info(
                    "sentence_transformers_loaded", model=self.model_name, dimension=self._dimension
                )
            except ImportError:
                raise RuntimeError(
                    "sentence-transformers not installed. Run: pip install sentence-transformers"
                )

    async def embed(self, texts: List[str]) -> EmbeddingResult:
        """Embed texts locally using sentence-transformers."""
        self._load_model()

        # Run in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        embeddings = await loop.run_in_executor(None, self._model.encode, texts)

        # Convert numpy arrays to lists
        embeddings_list = [emb.tolist() for emb in embeddings]

        logger.debug(
            "local_embeddings_created",
            model=self.model_name,
            count=len(texts),
            dimension=self._dimension,
        )

        return EmbeddingResult(
            embeddings=embeddings_list,
            model=self.model_name,
            provider="local",
            total_tokens=sum(len(t.split()) for t in texts),  # Rough estimate
        )


class OllamaEmbeddingProvider(EmbeddingProvider):
    """Ollama self-hosted embedding provider."""

    def __init__(self, model: str = OLLAMA_EMBEDDING_MODEL):
        self.model = model
        self._dimension = 768  # nomic-embed-text

    @property
    def dimension(self) -> int:
        return self._dimension

    async def embed(self, texts: List[str]) -> EmbeddingResult:
        """Embed texts using Ollama API."""
        import httpx

        embeddings = []
        async with httpx.AsyncClient() as client:
            for text in texts:
                try:
                    response = await client.post(
                        OLLAMA_EMBEDDING_URL,
                        json={"model": self.model, "prompt": text},
                        timeout=30.0,
                    )
                    response.raise_for_status()
                    data = response.json()
                    embeddings.append(data["embedding"])
                except Exception as e:
                    logger.error("ollama_embedding_error", text=text[:50], error=str(e))
                    raise

        logger.debug(
            "ollama_embeddings_created",
            model=self.model,
            count=len(texts),
        )

        return EmbeddingResult(
            embeddings=embeddings,
            model=self.model,
            provider="ollama",
            total_tokens=sum(len(t.split()) for t in texts),
        )


# Global singleton
_embedding_provider: Optional[EmbeddingProvider] = None


def get_embedding_provider() -> EmbeddingProvider:
    """Get the configured embedding provider."""
    global _embedding_provider
    if _embedding_provider is not None:
        return _embedding_provider

    if EMBEDDING_PROVIDER == "openai":
        _embedding_provider = OpenAIEmbeddingProvider()
    elif EMBEDDING_PROVIDER == "local":
        _embedding_provider = SentenceTransformersProvider()
    elif EMBEDDING_PROVIDER == "ollama":
        _embedding_provider = OllamaEmbeddingProvider()
    else:
        logger.warning("unknown_embedding_provider", provider=EMBEDDING_PROVIDER, fallback="openai")
        _embedding_provider = OpenAIEmbeddingProvider()

    return _embedding_provider
