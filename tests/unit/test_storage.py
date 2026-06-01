"""
Unit tests for the storage abstraction layer.

Tests all three backends (MarkdownBackend, PostgreSQLBackend, DualBackend)
and the get_storage() factory function using mocked dependencies.
"""

import pytest
from unittest.mock import MagicMock, patch, call
from decimal import Decimal


# ---------------------------------------------------------------------------
#  MarkdownBackend Tests
# ---------------------------------------------------------------------------

class TestMarkdownBackend:
    """Tests for the filesystem-based Markdown storage backend."""

    @pytest.fixture
    def mock_vault(self):
        """Mock ObsidianVault used by MarkdownBackend."""
        with patch("mcp_server.storage.ObsidianVault") as mock_cls:
            instance = MagicMock()
            mock_cls.return_value = instance
            yield instance

    @pytest.fixture
    def backend(self, mock_vault):
        """Create a MarkdownBackend with a mocked vault."""
        from mcp_server.storage import MarkdownBackend
        return MarkdownBackend()

    # -- CRUD operations ------------------------------------------------

    @pytest.mark.unit
    def test_write_node_delegates_to_vault(self, backend, mock_vault):
        """Should delegate write_node to vault.write_node with all args."""
        backend.write_node("Runs/test.md", "# Test content", {"status": "pass"})
        mock_vault.write_node.assert_called_once_with(
            "Runs/test.md", "# Test content", {"status": "pass"}
        )

    @pytest.mark.unit
    def test_write_node_without_frontmatter(self, backend, mock_vault):
        """Should delegate write_node when frontmatter is omitted."""
        backend.write_node("Runs/plain.md", "# Plain content")
        mock_vault.write_node.assert_called_once_with(
            "Runs/plain.md", "# Plain content", None
        )

    @pytest.mark.unit
    def test_read_node_returns_parsed_data(self, backend, mock_vault):
        """Should return frontmatter and content parsed by vault."""
        mock_vault.read_node.return_value = {
            "path": "Runs/test.md",
            "frontmatter": {"title": "Test Run", "status": "pass"},
            "content": "# Test\n\nResults here.",
        }
        result = backend.read_node("Runs/test.md")
        assert result["frontmatter"]["title"] == "Test Run"
        assert result["frontmatter"]["status"] == "pass"
        assert "Results here." in result["content"]
        mock_vault.read_node.assert_called_once_with("Runs/test.md")

    @pytest.mark.unit
    def test_update_frontmatter_delegates_to_vault(self, backend, mock_vault):
        """Should delegate update_frontmatter to vault with merged updates."""
        backend.update_frontmatter("Runs/test.md", {"status": "completed"})
        mock_vault.update_frontmatter.assert_called_once_with(
            "Runs/test.md", {"status": "completed"}
        )

    @pytest.mark.unit
    def test_list_nodes_delegates_to_vault(self, backend, mock_vault):
        """Should delegate list_nodes to vault and return results."""
        mock_vault.list_nodes.return_value = [
            "Runs/a.md", "Runs/b.md", "Runs/sub/c.md",
        ]
        result = backend.list_nodes("Runs")
        assert result == ["Runs/a.md", "Runs/b.md", "Runs/sub/c.md"]
        mock_vault.list_nodes.assert_called_once_with("Runs")

    # -- Query / filtering ----------------------------------------------

    @pytest.mark.unit
    def test_query_findings_filters_on_frontmatter(self, backend, mock_vault):
        """Should return only findings whose frontmatter matches all filters."""
        mock_vault.list_nodes.return_value = [
            "Runs/a.md", "Runs/b.md", "Runs/c.md",
        ]
        mock_vault.read_node.side_effect = [
            {
                "frontmatter": {"severity": "high", "status": "open"},
                "content": "Finding A",
            },
            {
                "frontmatter": {"severity": "low", "status": "open"},
                "content": "Finding B",
            },
            {
                "frontmatter": {"severity": "high", "status": "closed"},
                "content": "Finding C",
            },
        ]

        results = backend.query_findings(severity="high")

        assert len(results) == 2
        assert all(r["frontmatter"]["severity"] == "high" for r in results)

    @pytest.mark.unit
    def test_query_findings_skips_read_errors(self, backend, mock_vault):
        """Should skip nodes that fail to read and continue scanning."""
        mock_vault.list_nodes.return_value = ["Runs/a.md", "Runs/b.md"]
        mock_vault.read_node.side_effect = [
            FileNotFoundError("Node deleted"),
            {"frontmatter": {"severity": "high"}, "content": "Found it"},
        ]

        results = backend.query_findings(severity="high")

        assert len(results) == 1
        assert results[0]["frontmatter"]["severity"] == "high"

    @pytest.mark.unit
    def test_query_findings_returns_empty_when_no_matches(self, backend, mock_vault):
        """Should return empty list when no findings match the filters."""
        mock_vault.list_nodes.return_value = ["Runs/a.md"]
        mock_vault.read_node.return_value = {
            "frontmatter": {"severity": "low", "status": "closed"},
            "content": "Irrelevant",
        }

        results = backend.query_findings(severity="critical")

        assert results == []

    @pytest.mark.unit
    def test_query_test_runs_returns_matching_runs(self, backend, mock_vault):
        """Should return test runs whose frontmatter matches filters."""
        mock_vault.list_nodes.return_value = ["Runs/run1.md", "Runs/run2.md"]
        mock_vault.read_node.side_effect = [
            {
                "frontmatter": {"test_run_id": "run-001", "status": "pass"},
                "content": "",
            },
            {
                "frontmatter": {"test_run_id": "run-002", "status": "fail"},
                "content": "",
            },
        ]

        results = backend.query_test_runs(status="pass")

        assert len(results) == 1
        assert results[0]["frontmatter"]["test_run_id"] == "run-001"

    @pytest.mark.unit
    def test_query_test_runs_ignores_nodes_without_test_run_id(self, backend, mock_vault):
        """Should skip nodes that lack a test_run_id frontmatter key."""
        mock_vault.list_nodes.return_value = [
            "Runs/run1.md", "Runs/note.md",
        ]
        mock_vault.read_node.side_effect = [
            {"frontmatter": {"test_run_id": "run-001", "status": "pass"}, "content": ""},
            {"frontmatter": {"title": "Just a note"}, "content": "# Note"},
        ]

        results = backend.query_test_runs()

        assert len(results) == 1
        assert results[0]["frontmatter"]["test_run_id"] == "run-001"


# ---------------------------------------------------------------------------
#  PostgreSQLBackend Tests
# ---------------------------------------------------------------------------

class TestPostgreSQLBackend:
    """Tests for the PostgreSQL-backed storage backend."""

    @pytest.fixture
    def mock_db_manager(self):
        """Mock get_db_manager_sync and asyncio event loop for PG backend."""
        with patch("mcp_server.storage.get_db_manager_sync") as mock_get_db:
            mock_db = MagicMock()
            mock_db._initialized = True
            mock_get_db.return_value = mock_db

            with patch("asyncio.get_event_loop") as mock_get_loop:
                mock_loop = MagicMock()
                mock_loop.is_running.return_value = False
                mock_get_loop.return_value = mock_loop

                yield mock_db, mock_loop

    @pytest.fixture
    def backend(self, mock_db_manager):
        """Create a PostgreSQLBackend with mocked DB dependencies."""
        from mcp_server.storage import PostgreSQLBackend
        return PostgreSQLBackend()

    # -- CRUD operations ------------------------------------------------

    @pytest.mark.unit
    def test_write_node_upserts_to_vault_sync_log(self, backend, mock_db_manager):
        """Should upsert node metadata into vault_sync_log table."""
        mock_db, mock_loop = mock_db_manager

        backend.write_node("Runs/test.md", "# Content", {"status": "pass"})

        mock_db.execute.assert_called_once()
        sql, params = mock_db.execute.call_args[0]
        assert "INSERT INTO vault_sync_log" in sql
        assert params[0] == "Runs/test.md"
        assert mock_loop.create_task.called

    @pytest.mark.unit
    def test_write_node_resilient_to_db_failure(self, backend, mock_db_manager):
        """Should not raise when db.execute raises (best-effort write)."""
        mock_db, mock_loop = mock_db_manager
        mock_db.execute.side_effect = RuntimeError("Connection refused")

        # Should not raise
        backend.write_node("Runs/test.md", "# Content")
        # The exception is caught and logged in the try/except in write_node

    # -- Query operations -----------------------------------------------

    @pytest.mark.unit
    def test_query_findings_builds_filtered_sql(self, backend, mock_db_manager):
        """Should build SQL with WHERE conditions from keyword filters."""
        mock_db, mock_loop = mock_db_manager
        mock_loop.run_until_complete.return_value = [
            {"id": 1, "severity": "high", "status": "open"},
        ]

        results = backend.query_findings(severity="high", status="open")

        mock_db.fetchall.assert_called_once()
        sql, params = mock_db.fetchall.call_args[0]
        assert "severity = %s" in sql
        assert "status = %s" in sql
        assert "findings" in sql
        assert params == ("high", "open")
        assert len(results) == 1

    @pytest.mark.unit
    def test_query_findings_without_filters_uses_where_true(self, backend, mock_db_manager):
        """Should use WHERE TRUE when no filters provided."""
        mock_db, mock_loop = mock_db_manager
        mock_loop.run_until_complete.return_value = [
            {"id": 1}, {"id": 2}, {"id": 3},
        ]

        results = backend.query_findings()

        mock_db.fetchall.assert_called_once()
        sql = mock_db.fetchall.call_args[0][0]
        assert "WHERE TRUE" in sql
        assert len(results) == 3

    @pytest.mark.unit
    def test_query_findings_returns_empty_list_on_db_error(self, backend, mock_db_manager):
        """Should return empty list when the database query fails."""
        mock_db, mock_loop = mock_db_manager
        mock_db.fetchall.side_effect = RuntimeError("Connection lost")

        results = backend.query_findings(severity="high")

        assert results == []

    @pytest.mark.unit
    def test_query_test_runs_builds_correct_sql(self, backend, mock_db_manager):
        """Should query from test_runs table with filters."""
        mock_db, mock_loop = mock_db_manager
        mock_loop.run_until_complete.return_value = [
            {"id": 1, "test_run_id": "run-001", "status": "pass"},
        ]

        results = backend.query_test_runs(status="pass")

        mock_db.fetchall.assert_called_once()
        sql, params = mock_db.fetchall.call_args[0]
        assert "test_runs" in sql
        assert "status = %s" in sql
        assert params == ("pass",)
        assert len(results) == 1

    @pytest.mark.unit
    def test_query_test_runs_returns_empty_on_db_error(self, backend, mock_db_manager):
        """Should return empty list when test run query fails."""
        mock_db, mock_loop = mock_db_manager
        mock_db.fetchall.side_effect = RuntimeError("DB timeout")

        results = backend.query_test_runs(status="fail")

        assert results == []


# ---------------------------------------------------------------------------
#  DualBackend Tests
# ---------------------------------------------------------------------------

class TestDualBackend:
    """Tests for the dual-write (Markdown + PostgreSQL) backend."""

    @pytest.fixture
    def mock_backends(self):
        """Mock both sub-backends so DualBackend uses test doubles."""
        with (
            patch("mcp_server.storage.MarkdownBackend", autospec=True) as mock_md_cls,
            patch("mcp_server.storage.PostgreSQLBackend", autospec=True) as mock_pg_cls,
        ):
            mock_md = MagicMock()
            mock_pg = MagicMock()
            mock_md_cls.return_value = mock_md
            mock_pg_cls.return_value = mock_pg
            yield mock_md, mock_pg

    @pytest.fixture
    def backend(self, mock_backends):
        """Create a DualBackend with mocked Markdown + PostgreSQL."""
        from mcp_server.storage import DualBackend
        return DualBackend()

    # -- Dual writes ----------------------------------------------------

    @pytest.mark.unit
    def test_writes_to_both_backends(self, backend, mock_backends):
        """Should write to Markdown first, then PostgreSQL."""
        mock_md, mock_pg = mock_backends

        backend.write_node("Runs/test.md", "# Content", {"key": "val"})

        mock_md.write_node.assert_called_once_with(
            "Runs/test.md", "# Content", {"key": "val"}
        )
        mock_pg.write_node.assert_called_once_with(
            "Runs/test.md", "# Content", {"key": "val"}
        )

    @pytest.mark.unit
    def test_writes_to_markdown_even_when_pg_fails(self, backend, mock_backends):
        """Should still write to Markdown if PostgreSQL write raises."""
        mock_md, mock_pg = mock_backends
        mock_pg.write_node.side_effect = RuntimeError("PG unavailable")

        # Should not raise — PG failure is swallowed
        backend.write_node("Runs/test.md", "# Content")

        mock_md.write_node.assert_called_once()

    # -- Reads from Markdown (source of truth) --------------------------

    @pytest.mark.unit
    def test_reads_from_markdown_only(self, backend, mock_backends):
        """Should read exclusively from Markdown (source of truth)."""
        mock_md, mock_pg = mock_backends
        mock_md.read_node.return_value = {
            "frontmatter": {"title": "Test"},
            "content": "# Hello",
        }

        result = backend.read_node("Runs/test.md")

        assert result["frontmatter"]["title"] == "Test"
        assert result["content"] == "# Hello"
        mock_md.read_node.assert_called_once_with("Runs/test.md")
        mock_pg.read_node.assert_not_called()

    @pytest.mark.unit
    def test_list_nodes_delegates_to_markdown(self, backend, mock_backends):
        """Should list nodes from Markdown only."""
        mock_md, mock_pg = mock_backends
        mock_md.list_nodes.return_value = ["Runs/a.md", "Runs/b.md"]

        result = backend.list_nodes("Runs")

        assert result == ["Runs/a.md", "Runs/b.md"]
        mock_md.list_nodes.assert_called_once_with("Runs")

    @pytest.mark.unit
    def test_queries_delegate_to_markdown(self, backend, mock_backends):
        """Should delegate query_findings and query_test_runs to Markdown."""
        mock_md, mock_pg = mock_backends
        mock_md.query_findings.return_value = [{"id": 1, "severity": "high"}]
        mock_md.query_test_runs.return_value = [{"id": 2, "status": "pass"}]

        findings = backend.query_findings(severity="high")
        runs = backend.query_test_runs(status="pass")

        assert findings == [{"id": 1, "severity": "high"}]
        assert runs == [{"id": 2, "status": "pass"}]
        mock_md.query_findings.assert_called_once_with(severity="high")
        mock_md.query_test_runs.assert_called_once_with(status="pass")

    @pytest.mark.unit
    def test_update_frontmatter_writes_to_both(self, backend, mock_backends):
        """Should update frontmatter in both backends."""
        mock_md, mock_pg = mock_backends

        backend.update_frontmatter("Runs/test.md", {"status": "completed"})

        mock_md.update_frontmatter.assert_called_once_with(
            "Runs/test.md", {"status": "completed"}
        )
        mock_pg.update_frontmatter.assert_called_once_with(
            "Runs/test.md", {"status": "completed"}
        )


# ---------------------------------------------------------------------------
#  get_storage() Factory Tests
# ---------------------------------------------------------------------------

class TestGetStorage:
    """Tests for the get_storage() factory singleton function."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset the _storage_instance singleton before each test."""
        import mcp_server.storage as storage_mod
        storage_mod._storage_instance = None
        yield
        storage_mod._storage_instance = None

    @pytest.mark.unit
    def test_default_creates_markdown_backend(self):
        """Should create MarkdownBackend when VECTRA_BACKEND is 'markdown'."""
        with (
            patch("mcp_server.storage.VECTRA_BACKEND", "markdown"),
            patch("mcp_server.storage.ObsidianVault"),
        ):
            from mcp_server.storage import get_storage, MarkdownBackend
            storage = get_storage()
            assert isinstance(storage, MarkdownBackend)

    @pytest.mark.unit
    def test_postgresql_creates_pg_backend(self):
        """Should create PostgreSQLBackend when VECTRA_BACKEND is 'postgresql'."""
        with (
            patch("mcp_server.storage.VECTRA_BACKEND", "postgresql"),
            patch("mcp_server.storage.get_db_manager_sync"),
        ):
            from mcp_server.storage import get_storage, PostgreSQLBackend
            storage = get_storage()
            assert isinstance(storage, PostgreSQLBackend)

    @pytest.mark.unit
    def test_dual_creates_dual_backend(self):
        """Should create DualBackend when VECTRA_BACKEND is 'dual'."""
        with (
            patch("mcp_server.storage.VECTRA_BACKEND", "dual"),
            patch("mcp_server.storage.ObsidianVault"),
            patch("mcp_server.storage.get_db_manager_sync"),
        ):
            from mcp_server.storage import get_storage, DualBackend
            storage = get_storage()
            assert isinstance(storage, DualBackend)

    @pytest.mark.unit
    def test_get_storage_returns_singleton(self):
        """Should return the same instance on repeated calls."""
        with (
            patch("mcp_server.storage.VECTRA_BACKEND", "markdown"),
            patch("mcp_server.storage.ObsidianVault"),
        ):
            from mcp_server.storage import get_storage
            s1 = get_storage()
            s2 = get_storage()
            assert s1 is s2
