"""
RAG (Retrieval-Augmented Generation) system for Vectra QA.

Ingests test requirements, user stories, and previous test results into
PostgreSQL + pgvector. Retrieves relevant context for LLM queries.

Usage:
    from mcp_server.rag import RAGPipeline

    rag = RAGPipeline()
    await rag.ingest_document("Requirements/login.md", content, doc_type="requirement")
    results = await rag.retrieve("How should the login flow behave?", k=5)
"""

import json
import os
import re
from typing import Any, Dict, List, Optional
from dataclasses import dataclass
from pathlib import Path

import structlog

from mcp_server.embeddings import get_embedding_provider
from mcp_server.db import get_db_manager

logger = structlog.get_logger()

# Configuration
VAULT_PATH = Path(os.getenv("OBSIDIAN_VAULT_PATH", "/app/obsidian_vault"))
CHUNK_SIZE = int(os.getenv("RAG_CHUNK_SIZE", "512"))
CHUNK_OVERLAP = int(os.getenv("RAG_CHUNK_OVERLAP", "50"))


@dataclass
class DocumentChunk:
    """A chunk of a document with metadata."""

    id: int
    document_id: int
    source_path: str
    chunk_text: str
    chunk_index: int
    similarity: float = 0.0


class DocumentChunker:
    """Splits text into overlapping chunks."""

    def __init__(self, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP):
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk_text(self, text: str) -> List[str]:
        """Split text into overlapping chunks by approximate token count."""
        # Simple word-based chunking
        words = text.split()
        chunks = []
        start = 0

        while start < len(words):
            end = min(start + self.chunk_size, len(words))
            chunk = " ".join(words[start:end])
            chunks.append(chunk)
            start += self.chunk_size - self.overlap

        return chunks

    def chunk_markdown(self, content: str) -> List[Dict[str, Any]]:
        """Chunk markdown by headers, preserving structure."""
        chunks = []
        current_chunk = []
        current_header = ""

        for line in content.split("\n"):
            if line.startswith("#"):
                # Save previous chunk
                if current_chunk:
                    chunks.append(
                        {
                            "header": current_header,
                            "text": "\n".join(current_chunk),
                        }
                    )
                current_header = line
                current_chunk = [line]
            else:
                current_chunk.append(line)

        # Save final chunk
        if current_chunk:
            chunks.append(
                {
                    "header": current_header,
                    "text": "\n".join(current_chunk),
                }
            )

        # If chunks are too large, split further
        result = []
        for chunk in chunks:
            words = chunk["text"].split()
            if len(words) > self.chunk_size:
                sub_chunks = self.chunk_text(chunk["text"])
                for i, sub in enumerate(sub_chunks):
                    result.append(
                        {
                            "header": chunk["header"],
                            "text": sub,
                            "sub_index": i,
                        }
                    )
            else:
                result.append(chunk)

        return result


class RAGPipeline:
    """End-to-end RAG pipeline: ingest, embed, store, retrieve."""

    def __init__(self):
        self.db = get_db_manager()
        self.embedder = get_embedding_provider()
        self.chunker = DocumentChunker()

    async def ingest_document(
        self,
        source_path: str,
        content: str,
        doc_type: str = "unknown",
        title: Optional[str] = None,
        metadata: Optional[Dict] = None,
    ) -> int:
        """
        Ingest a document: chunk, embed, store.

        Returns:
            document_id
        """
        metadata = metadata or {}

        # Create document record
        doc_query = """
            INSERT INTO documents (source_path, content, doc_type, title, metadata)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (source_path) DO UPDATE SET
                content = EXCLUDED.content,
                doc_type = EXCLUDED.doc_type,
                title = EXCLUDED.title,
                metadata = EXCLUDED.metadata,
                updated_at = NOW()
            RETURNING id
        """
        doc_result = await self.db.fetchone(
            doc_query, (source_path, content, doc_type, title, json.dumps(metadata))
        )
        document_id = doc_result["id"]

        # Chunk the document
        chunks = self.chunker.chunk_markdown(content)

        # Delete old chunks
        await self.db.execute("DELETE FROM document_chunks WHERE document_id = %s", (document_id,))

        # Embed and store chunks
        for idx, chunk in enumerate(chunks):
            chunk_text = chunk["text"]
            if len(chunk_text.strip()) < 20:  # Skip very short chunks
                continue

            # Embed chunk
            try:
                embedding_result = await self.embedder.embed([chunk_text])
                embedding = embedding_result.embeddings[0]
            except Exception as e:
                logger.warning("chunk_embedding_failed", chunk_index=idx, error=str(e))
                continue

            # Store chunk
            chunk_query = """
                INSERT INTO document_chunks (document_id, chunk_text, chunk_index, embedding, metadata)
                VALUES (%s, %s, %s, %s, %s)
            """
            chunk_meta = {
                "header": chunk.get("header", ""),
                "sub_index": chunk.get("sub_index", 0),
            }
            await self.db.execute(
                chunk_query,
                (document_id, chunk_text, idx, embedding, json.dumps(chunk_meta)),
            )

        logger.info(
            "document_ingested",
            source_path=source_path,
            document_id=document_id,
            chunks=len(chunks),
            doc_type=doc_type,
        )

        return document_id

    async def retrieve(
        self,
        query: str,
        k: int = 5,
        doc_type: Optional[str] = None,
        similarity_threshold: float = 0.7,
    ) -> List[DocumentChunk]:
        """
        Retrieve relevant chunks for a query.

        Uses vector similarity search via pgvector.
        """
        # Embed query
        try:
            query_embedding = await self.embedder.embed([query])
            embedding = query_embedding.embeddings[0]
        except Exception as e:
            logger.error("query_embedding_failed", error=str(e))
            return []

        # Search
        search_query = """
            SELECT 
                dc.id,
                dc.document_id,
                d.source_path,
                dc.chunk_text,
                dc.chunk_index,
                1 - (dc.embedding <=> %s::vector) AS similarity
            FROM document_chunks dc
            JOIN documents d ON dc.document_id = d.id
            WHERE 1 - (dc.embedding <=> %s::vector) > %s
        """
        params = [embedding, embedding, similarity_threshold]

        if doc_type:
            search_query += " AND d.doc_type = %s"
            params.append(doc_type)

        search_query += " ORDER BY dc.embedding <=> %s::vector LIMIT %s"
        params.extend([embedding, k])

        try:
            rows = await self.db.fetchall(search_query, tuple(params))
            return [
                DocumentChunk(
                    id=row["id"],
                    document_id=row["document_id"],
                    source_path=row["source_path"],
                    chunk_text=row["chunk_text"],
                    chunk_index=row["chunk_index"],
                    similarity=row["similarity"],
                )
                for row in rows
            ]
        except Exception as e:
            logger.error("rag_retrieval_failed", error=str(e))
            return []

    async def ingest_vault_documents(self, doc_types: Optional[List[str]] = None):
        """
        Batch ingest all documents from the Obsidian vault.

        Scans Requirements/, Stories/, and previous test runs.
        """
        doc_types = doc_types or ["requirement", "story", "test_result"]
        folders = {
            "requirement": VAULT_PATH / "Requirements",
            "story": VAULT_PATH / "Stories",
            "test_result": VAULT_PATH / "Runs",
        }

        for doc_type, folder in folders.items():
            if not folder.exists():
                continue

            for md_file in folder.rglob("*.md"):
                try:
                    content = md_file.read_text(encoding="utf-8")
                    rel_path = str(md_file.relative_to(VAULT_PATH))

                    # Extract title from first heading
                    title_match = re.search(r"^# (.+)$", content, re.MULTILINE)
                    title = title_match.group(1) if title_match else md_file.stem

                    await self.ingest_document(
                        source_path=rel_path,
                        content=content,
                        doc_type=doc_type,
                        title=title,
                    )
                except Exception as e:
                    logger.warning("vault_ingest_failed", file=str(md_file), error=str(e))

        logger.info("vault_ingest_complete", types=doc_types)

    async def search_knowledge(
        self,
        query: str,
        k: int = 5,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        High-level search interface for knowledge retrieval.

        Returns formatted results with source and relevance.
        """
        filters = filters or {}
        doc_type = filters.get("doc_type")

        chunks = await self.retrieve(query, k=k, doc_type=doc_type)

        results = []
        for chunk in chunks:
            results.append(
                {
                    "source": chunk.source_path,
                    "text": chunk.chunk_text[:500],  # Truncate for LLM context
                    "relevance": round(chunk.similarity, 3),
                    "chunk_index": chunk.chunk_index,
                }
            )

        return results


# Global singleton
_rag_pipeline: Optional[RAGPipeline] = None


async def get_rag_pipeline() -> RAGPipeline:
    """Get or create the RAGPipeline singleton."""
    global _rag_pipeline
    if _rag_pipeline is None:
        _rag_pipeline = RAGPipeline()
    return _rag_pipeline
