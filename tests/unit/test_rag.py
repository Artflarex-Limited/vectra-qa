"""
Unit tests for the RAG pipeline (mcp_server.rag).

Covers DocumentChunker (chunk_text, chunk_markdown) and RAGPipeline
(ingest_document, retrieve, search_knowledge) with mocked database and
embedding providers.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from mcp_server.rag import (
    DocumentChunker,
    DocumentChunk,
    RAGPipeline,
    get_rag_pipeline,
)
from mcp_server.embeddings import EmbeddingResult

# =========================================================================
# Fixtures
# =========================================================================


@pytest.fixture
def chunker():
    """Return a DocumentChunker with small chunk size for deterministic tests."""
    return DocumentChunker(chunk_size=10, overlap=2)


@pytest.fixture
def mock_db():
    """Create a mocked DatabaseManager with async methods."""
    db = MagicMock()
    db.fetchone = AsyncMock(return_value={"id": 42})
    db.execute = AsyncMock(return_value="INSERT 0 1")
    db.fetchall = AsyncMock(
        return_value=[
            {
                "id": 1,
                "document_id": 42,
                "source_path": "Requirements/login.md",
                "chunk_text": "Login form must validate email format.",
                "chunk_index": 0,
                "similarity": 0.92,
            },
            {
                "id": 2,
                "document_id": 42,
                "source_path": "Requirements/login.md",
                "chunk_text": "Password must be at least 8 characters.",
                "chunk_index": 1,
                "similarity": 0.85,
            },
        ]
    )
    return db


@pytest.fixture
def mock_embedder():
    """Create a mocked embedding provider."""
    embedder = MagicMock()
    embedder.embed = AsyncMock(
        return_value=EmbeddingResult(
            embeddings=[[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]],
            model="text-embedding-3-small",
            provider="openai",
            total_tokens=10,
        )
    )
    return embedder


@pytest.fixture
def rag_pipeline(mock_db, mock_embedder):
    """Create a RAGPipeline with mocked dependencies."""
    # get_db_manager is async but called synchronously in __init__;
    # use a plain MagicMock so the call returns mock_db directly.
    with (
        patch("mcp_server.rag.get_db_manager", new=MagicMock(return_value=mock_db)),
        patch("mcp_server.rag.get_embedding_provider", return_value=mock_embedder),
    ):
        pipeline = RAGPipeline()
        pipeline.chunker = DocumentChunker(chunk_size=512, overlap=50)
        return pipeline


# =========================================================================
# DocumentChunker — chunk_text
# =========================================================================


class TestChunkText:
    """Tests for DocumentChunker.chunk_text (word-based splitting)."""

    @pytest.mark.unit
    def test_basic_chunking(self, chunker):
        """Should split text into chunks of at most chunk_size words."""
        text = "one two three four five six seven eight nine ten eleven twelve"
        chunks = chunker.chunk_text(text)

        assert len(chunks) == 2
        # First chunk: words[0:10]
        assert chunks[0] == "one two three four five six seven eight nine ten"
        # Second chunk: words[8:12]  (overlap of 2)
        assert chunks[1] == "nine ten eleven twelve"

    @pytest.mark.unit
    def test_overlap_is_respected(self):
        """Should produce overlapping chunks based on the overlap parameter."""
        c = DocumentChunker(chunk_size=5, overlap=2)
        text = "a b c d e f g h i j"
        chunks = c.chunk_text(text)

        # start=0 → [0:5] = a b c d e; next start = 0+(5-2)=3
        # start=3 → [3:8] = d e f g h; next start = 3+3=6
        # start=6 → [6:10] = g h i j; next start = 6+3=9
        # start=9 → [9:10] = j; next start = 9+3=12 ≥ 10, done
        assert len(chunks) == 4
        assert chunks[0] == "a b c d e"
        assert chunks[1] == "d e f g h"
        assert chunks[2] == "g h i j"
        assert chunks[3] == "j"

    @pytest.mark.unit
    def test_empty_text(self, chunker):
        """Should return empty list when text is empty."""
        assert chunker.chunk_text("") == []

    @pytest.mark.unit
    def test_text_shorter_than_chunk_size(self, chunker):
        """Should return a single chunk when text is shorter than chunk_size."""
        text = "hello world"
        chunks = chunker.chunk_text(text)
        assert len(chunks) == 1
        assert chunks[0] == "hello world"


# =========================================================================
# DocumentChunker — chunk_markdown
# =========================================================================


class TestChunkMarkdown:
    """Tests for DocumentChunker.chunk_markdown (header-aware splitting)."""

    @pytest.mark.unit
    def test_splits_by_headers(self):
        """Should split markdown content at each header boundary."""
        c = DocumentChunker(chunk_size=100, overlap=10)
        content = """# Introduction
This is the intro section.
It has multiple lines.

## Details
More detailed information here.

### Subsection
Even more detail.
"""
        chunks = c.chunk_markdown(content)

        assert len(chunks) == 3
        assert chunks[0]["header"] == "# Introduction"
        assert "intro section" in chunks[0]["text"]
        assert chunks[1]["header"] == "## Details"
        assert "detailed information" in chunks[1]["text"]
        assert chunks[2]["header"] == "### Subsection"
        assert "Even more detail" in chunks[2]["text"]

    @pytest.mark.unit
    def test_large_sections_are_sub_chunked(self):
        """Should further split sections that exceed chunk_size words."""
        c = DocumentChunker(chunk_size=5, overlap=1)
        body = " ".join(f"word{i}" for i in range(12))
        content = f"# Big Section\n{body}"

        chunks = c.chunk_markdown(content)

        # Expect at least 2 sub-chunks under the same header
        assert len(chunks) >= 2
        for ch in chunks:
            assert ch["header"] == "# Big Section"
            assert "sub_index" in ch

    @pytest.mark.unit
    def test_empty_markdown(self):
        """Should return a single chunk with empty header and text for empty content."""
        c = DocumentChunker()
        chunks = c.chunk_markdown("")
        # The current implementation produces one chunk with empty header/text
        assert len(chunks) == 1
        assert chunks[0]["header"] == ""
        assert chunks[0]["text"] == ""


# =========================================================================
# RAGPipeline — ingest_document
# =========================================================================


class TestIngestDocument:
    """Tests for RAGPipeline.ingest_document."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_successful_ingestion(self, rag_pipeline, mock_db, mock_embedder):
        """Should chunk, embed, and store a document successfully."""
        content = "# Login\n\nLogin form must validate email format.\n\n# Password\n\nPassword must be at least 8 chars."
        doc_id = await rag_pipeline.ingest_document(
            source_path="Requirements/login.md",
            content=content,
            doc_type="requirement",
            title="Login Requirements",
        )

        assert doc_id == 42
        # DB insert called for document
        mock_db.fetchone.assert_awaited_once()
        # DB delete called for old chunks
        mock_db.execute.assert_awaited()
        # Embedder called for each non-empty chunk
        assert mock_embedder.embed.await_count >= 1

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_skips_very_short_chunks(self, rag_pipeline, mock_db, mock_embedder):
        """Should skip chunks shorter than 20 characters."""
        content = (
            "# Short\n\nab\n\n# Normal\n\nThis is a normal chunk with enough text to be meaningful."
        )
        await rag_pipeline.ingest_document(
            source_path="test.md",
            content=content,
            doc_type="test",
        )

        # The "ab" chunk should be skipped — embedder should only be called
        # for chunks with text >= 20 characters
        all_calls = mock_embedder.embed.call_args_list
        # Each call's first argument is a list of texts — check none are too short
        for call in all_calls:
            texts = call[0][0] if call[0] else []
            for t in texts:
                assert len(t.strip()) >= 20, f"Chunk too short: {t!r}"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_embedder_failure_logs_and_continues(self, rag_pipeline, mock_db):
        """Should log a warning and continue when embedding a chunk fails."""
        rag_pipeline.embedder.embed = AsyncMock(
            side_effect=[
                RuntimeError("API timeout"),
                EmbeddingResult(embeddings=[[0.1]], model="test", provider="test"),
            ]
        )
        content = "# Chunk1\n\nThis is the first chunk with enough text.\n\n# Chunk2\n\nThis is the second chunk with enough text."

        doc_id = await rag_pipeline.ingest_document(
            source_path="test.md",
            content=content,
            doc_type="test",
        )

        # Should still get a document ID back even after a chunk embedding failure
        assert doc_id == 42
        # The first chunk failed, but the second should have been embedded and stored
        assert rag_pipeline.embedder.embed.await_count == 2


# =========================================================================
# RAGPipeline — retrieve
# =========================================================================


class TestRetrieve:
    """Tests for RAGPipeline.retrieve."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_successful_retrieval(self, rag_pipeline, mock_db, mock_embedder):
        """Should return DocumentChunk objects from a successful retrieval."""
        results = await rag_pipeline.retrieve("How should login work?", k=5)

        assert len(results) == 2
        assert all(isinstance(r, DocumentChunk) for r in results)
        assert results[0].document_id == 42
        assert results[0].source_path == "Requirements/login.md"
        assert results[0].similarity == 0.92
        assert results[1].similarity == 0.85
        mock_embedder.embed.assert_awaited_once()
        mock_db.fetchall.assert_awaited_once()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_retrieval_with_doc_type_filter(self, rag_pipeline, mock_db, mock_embedder):
        """Should include doc_type filter in the SQL query when specified."""
        await rag_pipeline.retrieve("How should login work?", k=3, doc_type="requirement")

        # Verify the SQL contains the doc_type filter
        call_args = mock_db.fetchall.call_args[0]
        sql = call_args[0]
        params = call_args[1]
        assert "d.doc_type = %s" in sql
        assert "requirement" in params

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_retrieval_embedding_failure_returns_empty(self, rag_pipeline, mock_db):
        """Should return an empty list when query embedding fails."""
        rag_pipeline.embedder.embed = AsyncMock(side_effect=RuntimeError("Embedding failed"))

        results = await rag_pipeline.retrieve("How should login work?", k=5)

        assert results == []
        mock_db.fetchall.assert_not_awaited()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_retrieval_db_failure_returns_empty(self, rag_pipeline, mock_db, mock_embedder):
        """Should return an empty list when the database query fails."""
        mock_db.fetchall = AsyncMock(side_effect=RuntimeError("Connection lost"))

        results = await rag_pipeline.retrieve("How should login work?", k=5)

        assert results == []


# =========================================================================
# RAGPipeline — search_knowledge
# =========================================================================


class TestSearchKnowledge:
    """Tests for RAGPipeline.search_knowledge."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_formats_results_correctly(self, rag_pipeline, mock_db, mock_embedder):
        """Should return formatted dicts with source, text, relevance, chunk_index."""
        results = await rag_pipeline.search_knowledge("How should login work?", k=5)

        assert len(results) == 2
        for r in results:
            assert "source" in r
            assert "text" in r
            assert "relevance" in r
            assert "chunk_index" in r
            # Text should be truncated to 500 chars
            assert len(r["text"]) <= 500
            # Relevance should be rounded to 3 decimals
            assert isinstance(r["relevance"], float)

        assert results[0]["source"] == "Requirements/login.md"
        assert results[0]["relevance"] == 0.92

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_passes_doc_type_filter(self, rag_pipeline, mock_db, mock_embedder):
        """Should pass doc_type from filters dict to retrieve."""
        await rag_pipeline.search_knowledge(
            "How should login work?",
            k=3,
            filters={"doc_type": "story"},
        )

        call_args = mock_db.fetchall.call_args[0]
        sql = call_args[0]
        assert "d.doc_type = %s" in sql
        params = call_args[1]
        assert "story" in params


# =========================================================================
# Singleton
# =========================================================================


class TestRAGSingleton:
    """Tests for get_rag_pipeline singleton."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_rag_pipeline(self):
        """Should return a RAGPipeline instance."""
        # Clear global singleton
        import mcp_server.rag as rag_mod

        rag_mod._rag_pipeline = None

        with (
            patch("mcp_server.rag.get_db_manager", new=MagicMock(return_value=AsyncMock())),
            patch("mcp_server.rag.get_embedding_provider", new=MagicMock(return_value=AsyncMock())),
        ):
            pipeline = await get_rag_pipeline()
            assert isinstance(pipeline, RAGPipeline)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_singleton_returns_same_instance(self):
        """Should return the same instance on repeated calls."""
        import mcp_server.rag as rag_mod

        rag_mod._rag_pipeline = None

        with (
            patch("mcp_server.rag.get_db_manager", new=MagicMock(return_value=AsyncMock())),
            patch("mcp_server.rag.get_embedding_provider", new=MagicMock(return_value=AsyncMock())),
        ):
            p1 = await get_rag_pipeline()
            p2 = await get_rag_pipeline()

            assert p1 is p2
