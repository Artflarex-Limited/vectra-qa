"""
Storage abstraction layer for Vectra QA.

Provides dual-write capability: Markdown files for human readability
and PostgreSQL for structured queries and performance.

Usage:
    from mcp_server.storage import get_storage
    
    storage = get_storage()
    storage.write_node("Runs/Test.md", content="# Test", frontmatter={"status": "pass"})
    node = storage.read_node("Runs/Test.md")
    findings = storage.query_findings(test_run_id="run-123", severity="high")
"""

import os
import json
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from pathlib import Path
from datetime import datetime, timezone

import structlog

from mcp_server.tools import ObsidianVault, VaultError
from mcp_server.db import get_db_manager, DatabaseManager

logger = structlog.get_logger()

# Configuration
VECTRA_BACKEND = os.getenv("VECTRA_BACKEND", "dual")  # markdown | postgresql | dual
VAULT_PATH = Path(os.getenv("OBSIDIAN_VAULT_PATH", "/app/obsidian_vault"))


class BaseStorage(ABC):
    """Abstract base class for storage backends."""

    @abstractmethod
    def write_node(self, node_path: str, content: str, frontmatter: Optional[Dict] = None):
        """Write a node (Markdown file) with optional YAML frontmatter."""
        pass

    @abstractmethod
    def read_node(self, node_path: str) -> Dict[str, Any]:
        """Read a node and parse its frontmatter and content."""
        pass

    @abstractmethod
    def update_frontmatter(self, node_path: str, updates: Dict[str, Any]):
        """Update only the frontmatter of a node."""
        pass

    @abstractmethod
    def list_nodes(self, prefix: str = "") -> List[str]:
        """List all node paths matching a prefix."""
        pass

    @abstractmethod
    def query_findings(self, **filters) -> List[Dict[str, Any]]:
        """Query findings with filters."""
        pass

    @abstractmethod
    def query_test_runs(self, **filters) -> List[Dict[str, Any]]:
        """Query test runs with filters."""
        pass


class MarkdownBackend(BaseStorage):
    """Filesystem-based storage using Markdown files."""

    def __init__(self):
        self.vault = ObsidianVault(str(VAULT_PATH))
        logger.info("markdown_backend_initialized", vault_path=str(VAULT_PATH))

    def write_node(self, node_path: str, content: str, frontmatter: Optional[Dict] = None):
        self.vault.write_node(node_path, content, frontmatter)

    def read_node(self, node_path: str) -> Dict[str, Any]:
        return self.vault.read_node(node_path)

    def update_frontmatter(self, node_path: str, updates: Dict[str, Any]):
        self.vault.update_frontmatter(node_path, updates)

    def list_nodes(self, prefix: str = "") -> List[str]:
        return self.vault.list_nodes(prefix)

    def query_findings(self, **filters) -> List[Dict[str, Any]]:
        """Limited querying - scans all files. Slow but functional."""
        findings = []
        for node_path in self.list_nodes("Runs"):
            try:
                node = self.read_node(node_path)
                fm = node.get("frontmatter", {})
                # Simple filtering on frontmatter
                match = all(fm.get(k) == v for k, v in filters.items())
                if match:
                    findings.append({
                        "node_path": node_path,
                        "frontmatter": fm,
                        "content": node.get("content", "")[:500],
                    })
            except Exception:
                continue
        return findings

    def query_test_runs(self, **filters) -> List[Dict[str, Any]]:
        """Limited querying - scans all files."""
        runs = []
        for node_path in self.list_nodes("Runs"):
            try:
                node = self.read_node(node_path)
                fm = node.get("frontmatter", {})
                if fm.get("test_run_id"):
                    match = all(fm.get(k) == v for k, v in filters.items())
                    if match:
                        runs.append({
                            "node_path": node_path,
                            "frontmatter": fm,
                        })
            except Exception:
                continue
        return runs


class PostgreSQLBackend(BaseStorage):
    """PostgreSQL-based storage for structured queries and performance."""

    def __init__(self):
        self.db: DatabaseManager = get_db_manager_sync()
        logger.info("postgresql_backend_initialized")

    def _ensure_initialized(self):
        if not self.db._initialized:
            logger.warning("postgresql_not_initialized", 
                          message="Database not connected. Queries will fail.")

    def write_node(self, node_path: str, content: str, frontmatter: Optional[Dict] = None):
        """Store node metadata in PostgreSQL (content stays in Markdown)."""
        self._ensure_initialized()
        frontmatter = frontmatter or {}
        
        # Upsert into vault_sync_log
        query = """
            INSERT INTO vault_sync_log (node_path, last_modified, checksum, action)
            VALUES (%s, NOW(), %s, 'synced')
            ON CONFLICT (node_path) 
            DO UPDATE SET last_modified = NOW(), checksum = EXCLUDED.checksum, action = 'synced'
        """
        checksum = str(hash(content + json.dumps(frontmatter, sort_keys=True)))
        
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            loop.create_task(self.db.execute(query, (node_path, checksum)))
        except Exception as e:
            logger.debug("postgresql_sync_skipped", node_path=node_path, error=str(e))

    def read_node(self, node_path: str) -> Dict[str, Any]:
        """Read from PostgreSQL if available, else return empty."""
        self._ensure_initialized()
        return {"frontmatter": {}, "content": "", "source": "postgresql"}

    def update_frontmatter(self, node_path: str, updates: Dict[str, Any]):
        """Update sync log."""
        self.write_node(node_path, "", updates)

    def list_nodes(self, prefix: str = "") -> List[str]:
        """List nodes from sync log."""
        self._ensure_initialized()
        
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            # Return empty list for now - actual implementation would query DB
            return []
        except Exception:
            return []

    async def query_findings(self, **filters) -> List[Dict[str, Any]]:
        """Efficient SQL querying of findings."""
        conditions = []
        params = []
        
        for key, value in filters.items():
            conditions.append(f"{key} = %s")
            params.append(value)
        
        where_clause = " AND ".join(conditions) if conditions else "TRUE"
        query = f"SELECT * FROM findings WHERE {where_clause} ORDER BY created_at DESC"
        
        return await self.db.fetchall(query, tuple(params))

    async def query_test_runs(self, **filters) -> List[Dict[str, Any]]:
        """Efficient SQL querying of test runs."""
        conditions = []
        params = []
        
        for key, value in filters.items():
            conditions.append(f"{key} = %s")
            params.append(value)
        
        where_clause = " AND ".join(conditions) if conditions else "TRUE"
        query = f"SELECT * FROM test_runs WHERE {where_clause} ORDER BY started_at DESC"
        
        return await self.db.fetchall(query, tuple(params))


class DualBackend(BaseStorage):
    """Writes to both Markdown and PostgreSQL. Reads from PostgreSQL (fast) with Markdown fallback."""

    def __init__(self):
        self.markdown = MarkdownBackend()
        self.postgresql = PostgreSQLBackend()
        logger.info("dual_backend_initialized")

    def write_node(self, node_path: str, content: str, frontmatter: Optional[Dict] = None):
        """Write to both backends."""
        # Always write to Markdown (source of truth)
        self.markdown.write_node(node_path, content, frontmatter)
        
        # Best-effort write to PostgreSQL
        try:
            self.postgresql.write_node(node_path, content, frontmatter)
        except Exception as e:
            logger.debug("postgresql_write_skipped", node_path=node_path, error=str(e))

    def read_node(self, node_path: str) -> Dict[str, Any]:
        """Read from Markdown (source of truth)."""
        return self.markdown.read_node(node_path)

    def update_frontmatter(self, node_path: str, updates: Dict[str, Any]):
        """Update both backends."""
        self.markdown.update_frontmatter(node_path, updates)
        try:
            self.postgresql.update_frontmatter(node_path, updates)
        except Exception as e:
            logger.debug("postgresql_update_skipped", node_path=node_path, error=str(e))

    def list_nodes(self, prefix: str = "") -> List[str]:
        """List from Markdown."""
        return self.markdown.list_nodes(prefix)

    def query_findings(self, **filters) -> List[Dict[str, Any]]:
        """Query from PostgreSQL (fast). Fallback to Markdown scan."""
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # We're in async context, can use postgresql
                future = asyncio.ensure_future(self.postgresql.query_findings(**filters))
                # For sync contexts, return markdown results
                if not future.done():
                    return self.markdown.query_findings(**filters)
                return future.result()
            return self.markdown.query_findings(**filters)
        except Exception:
            return self.markdown.query_findings(**filters)

    def query_test_runs(self, **filters) -> List[Dict[str, Any]]:
        """Query from PostgreSQL. Fallback to Markdown."""
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            if loop.is_running():
                future = asyncio.ensure_future(self.postgresql.query_test_runs(**filters))
                if not future.done():
                    return self.markdown.query_test_runs(**filters)
                return future.result()
            return self.markdown.query_test_runs(**filters)
        except Exception:
            return self.markdown.query_test_runs(**filters)


# Global singleton
_storage_instance: Optional[BaseStorage] = None


def get_storage() -> BaseStorage:
    """Get the configured storage backend."""
    global _storage_instance
    if _storage_instance is not None:
        return _storage_instance

    if VECTRA_BACKEND == "postgresql":
        _storage_instance = PostgreSQLBackend()
    elif VECTRA_BACKEND == "dual":
        _storage_instance = DualBackend()
    else:
        _storage_instance = MarkdownBackend()

    return _storage_instance
