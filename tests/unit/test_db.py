"""
Unit tests for the PostgreSQL connection manager (mcp_server.db).

Tests pool initialization, retry logic, health checks, CRUD helpers,
graceful degradation when psycopg is unavailable, and cleanup/shutdown.
All external dependencies are mocked at the module boundary.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def _mock_pool_with_conn(mock_conn):
    """Build a mock pool whose connection() context manager yields mock_conn."""
    mock_pool = MagicMock()
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=mock_conn)
    cm.__aexit__ = AsyncMock(return_value=False)
    mock_pool.connection.return_value = cm
    mock_pool.close = AsyncMock()
    return mock_pool


def _mock_cursor(mock_cur):
    """Build an async-context-manager mock that yields mock_cur."""
    cur_cm = MagicMock()
    cur_cm.__aenter__ = AsyncMock(return_value=mock_cur)
    cur_cm.__aexit__ = AsyncMock(return_value=False)
    return cur_cm


class TestDatabaseManagerInit:
    """Tests for DatabaseManager initialization and pool setup."""

    @pytest.fixture
    def db_manager(self):
        """Create a fresh DatabaseManager for each test."""
        from mcp_server.db import DatabaseManager

        return DatabaseManager()

    # ------------------------------------------------------------------
    # Pool initialization
    # ------------------------------------------------------------------

    @pytest.mark.unit
    async def test_initialize_success(self, db_manager):
        """Should create an AsyncConnectionPool and mark as initialized."""
        mock_pool = MagicMock()
        mock_pool.close = AsyncMock()
        # psycopg.AsyncConnectionPool does not exist in this environment,
        # so patch with create=True.
        with (
            patch("mcp_server.db.PSYCOPG_AVAILABLE", True),
            patch(
                "mcp_server.db.psycopg.AsyncConnectionPool",
                new=AsyncMock(return_value=mock_pool),
                create=True,
            ) as mock_cls,
        ):
            result = await db_manager.initialize()

        assert result is True
        assert db_manager._initialized is True
        assert db_manager.pool is mock_pool
        mock_cls.assert_called_once()

    @pytest.mark.unit
    async def test_initialize_failure_returns_false(self, db_manager):
        """Should return False when AsyncConnectionPool creation fails."""
        with (
            patch("mcp_server.db.PSYCOPG_AVAILABLE", True),
            patch(
                "mcp_server.db.psycopg.AsyncConnectionPool",
                side_effect=RuntimeError("Connection refused"),
                create=True,
            ),
        ):
            result = await db_manager.initialize()

        assert result is False
        assert db_manager._initialized is False
        assert db_manager.pool is None

    @pytest.mark.unit
    async def test_initialize_psycopg_not_installed(self, db_manager):
        """Should return False gracefully when psycopg is not available."""
        with patch("mcp_server.db.PSYCOPG_AVAILABLE", False):
            result = await db_manager.initialize()

        assert result is False
        assert db_manager._initialized is False
        assert db_manager.pool is None

    @pytest.mark.unit
    async def test_initialize_is_idempotent(self, db_manager):
        """Should only create the pool once when initialize is called twice."""
        mock_pool = MagicMock()
        mock_pool.close = AsyncMock()

        with (
            patch("mcp_server.db.PSYCOPG_AVAILABLE", True),
            patch(
                "mcp_server.db.psycopg.AsyncConnectionPool",
                new=AsyncMock(return_value=mock_pool),
                create=True,
            ) as mock_cls,
        ):
            result1 = await db_manager.initialize()
            result2 = await db_manager.initialize()

        assert result1 is True
        assert result2 is True
        # AsyncConnectionPool should only be called once
        mock_cls.assert_called_once()

    # ------------------------------------------------------------------
    # Cleanup / shutdown
    # ------------------------------------------------------------------

    @pytest.mark.unit
    async def test_close_cleans_up_pool(self, db_manager):
        """Should close the pool and reset initialization flag."""
        mock_pool = MagicMock()
        mock_pool.close = AsyncMock()
        db_manager.pool = mock_pool
        db_manager._initialized = True

        await db_manager.close()

        mock_pool.close.assert_awaited_once()
        assert db_manager._initialized is False

    @pytest.mark.unit
    async def test_close_when_no_pool_does_nothing(self, db_manager):
        """Should not raise when close is called without an initialized pool."""
        db_manager.pool = None
        db_manager._initialized = False

        # Should not raise
        await db_manager.close()

        assert db_manager._initialized is False

    # ------------------------------------------------------------------
    # Connection context manager
    # ------------------------------------------------------------------

    @pytest.mark.unit
    async def test_connection_yields_pool_connection(self, db_manager):
        """Should yield a connection from the pool via the context manager."""
        mock_conn = MagicMock()
        mock_pool = _mock_pool_with_conn(mock_conn)
        db_manager.pool = mock_pool
        db_manager._initialized = True

        async with db_manager.connection() as conn:
            assert conn is mock_conn

        mock_pool.connection.assert_called_once()

    @pytest.mark.unit
    async def test_connection_raises_when_no_pool(self, db_manager):
        """Should raise RuntimeError when pool is not initialized."""
        db_manager.pool = None
        db_manager._initialized = False

        with pytest.raises(RuntimeError, match="Database pool not initialized"):
            async with db_manager.connection():
                pass  # pragma: no cover

    # ------------------------------------------------------------------
    # CRUD helpers
    # ------------------------------------------------------------------

    @pytest.mark.unit
    async def test_execute_runs_query(self, db_manager):
        """Should execute a query and return the status message."""
        mock_conn = MagicMock()
        mock_conn.execute = AsyncMock()
        mock_conn.execute.return_value.statusmessage = "INSERT 0 1"
        mock_pool = _mock_pool_with_conn(mock_conn)
        db_manager.pool = mock_pool
        db_manager._initialized = True

        result = await db_manager.execute("INSERT INTO test VALUES (%s)", (1,))

        assert result == "INSERT 0 1"
        mock_conn.execute.assert_called_once_with("INSERT INTO test VALUES (%s)", (1,))

    @pytest.mark.unit
    async def test_fetchone_returns_single_row(self, db_manager):
        """Should fetch and return a single row as a dict."""
        mock_cur = MagicMock()
        mock_cur.execute = AsyncMock()
        mock_cur.fetchone = AsyncMock(return_value={"id": 1, "name": "test"})
        mock_conn = MagicMock()
        mock_conn.cursor = MagicMock(return_value=_mock_cursor(mock_cur))
        mock_pool = _mock_pool_with_conn(mock_conn)
        db_manager.pool = mock_pool
        db_manager._initialized = True

        row = await db_manager.fetchone("SELECT * FROM test WHERE id = %s", (1,))

        assert row == {"id": 1, "name": "test"}
        mock_cur.execute.assert_called_once_with("SELECT * FROM test WHERE id = %s", (1,))

    @pytest.mark.unit
    async def test_fetchone_returns_none_when_no_row(self, db_manager):
        """Should return None when no row matches the query."""
        mock_cur = MagicMock()
        mock_cur.execute = AsyncMock()
        mock_cur.fetchone = AsyncMock(return_value=None)
        mock_conn = MagicMock()
        mock_conn.cursor = MagicMock(return_value=_mock_cursor(mock_cur))
        mock_pool = _mock_pool_with_conn(mock_conn)
        db_manager.pool = mock_pool
        db_manager._initialized = True

        row = await db_manager.fetchone("SELECT * FROM test WHERE id = %s", (999,))

        assert row is None

    @pytest.mark.unit
    async def test_fetchall_returns_all_rows(self, db_manager):
        """Should fetch and return all matching rows as a list of dicts."""
        mock_cur = MagicMock()
        mock_cur.execute = AsyncMock()
        mock_cur.fetchall = AsyncMock(
            return_value=[
                {"id": 1, "name": "alpha"},
                {"id": 2, "name": "beta"},
            ]
        )
        mock_conn = MagicMock()
        mock_conn.cursor = MagicMock(return_value=_mock_cursor(mock_cur))
        mock_pool = _mock_pool_with_conn(mock_conn)
        db_manager.pool = mock_pool
        db_manager._initialized = True

        rows = await db_manager.fetchall("SELECT * FROM test")

        assert len(rows) == 2
        assert rows[0]["name"] == "alpha"
        assert rows[1]["name"] == "beta"

    @pytest.mark.unit
    async def test_fetchall_returns_empty_list(self, db_manager):
        """Should return an empty list when no rows match."""
        mock_cur = MagicMock()
        mock_cur.execute = AsyncMock()
        mock_cur.fetchall = AsyncMock(return_value=[])
        mock_conn = MagicMock()
        mock_conn.cursor = MagicMock(return_value=_mock_cursor(mock_cur))
        mock_pool = _mock_pool_with_conn(mock_conn)
        db_manager.pool = mock_pool
        db_manager._initialized = True

        rows = await db_manager.fetchall("SELECT * FROM test WHERE false")

        assert rows == []

    @pytest.mark.unit
    async def test_fetchval_returns_first_column(self, db_manager):
        """Should return the first column value from the fetched row."""
        mock_cur = MagicMock()
        mock_cur.execute = AsyncMock()
        mock_cur.fetchone = AsyncMock(return_value={"count": 42})
        mock_conn = MagicMock()
        mock_conn.cursor = MagicMock(return_value=_mock_cursor(mock_cur))
        mock_pool = _mock_pool_with_conn(mock_conn)
        db_manager.pool = mock_pool
        db_manager._initialized = True

        val = await db_manager.fetchval("SELECT count(*) FROM test")

        assert val == 42

    @pytest.mark.unit
    async def test_fetchval_returns_none_when_no_row(self, db_manager):
        """Should return None when fetchone returns None."""
        mock_cur = MagicMock()
        mock_cur.execute = AsyncMock()
        mock_cur.fetchone = AsyncMock(return_value=None)
        mock_conn = MagicMock()
        mock_conn.cursor = MagicMock(return_value=_mock_cursor(mock_cur))
        mock_pool = _mock_pool_with_conn(mock_conn)
        db_manager.pool = mock_pool
        db_manager._initialized = True

        val = await db_manager.fetchval("SELECT max(id) FROM empty_table")

        assert val is None

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    @pytest.mark.unit
    async def test_health_check_returns_healthy(self, db_manager):
        """Should return a healthy status dict when the DB query succeeds."""
        mock_cur = MagicMock()
        mock_cur.execute = AsyncMock()
        mock_cur.fetchone = AsyncMock(return_value={"1": 1})
        mock_conn = MagicMock()
        mock_conn.cursor = MagicMock(return_value=_mock_cursor(mock_cur))
        mock_pool = _mock_pool_with_conn(mock_conn)
        db_manager.pool = mock_pool
        db_manager._initialized = True

        result = await db_manager.health_check()

        assert result["status"] == "healthy"
        assert result["connected"] is True
        assert isinstance(result["latency_ms"], float)
        assert result["pool_initialized"] is True

    @pytest.mark.unit
    async def test_health_check_returns_unhealthy_on_failure(self, db_manager):
        """Should return an unhealthy status dict when the DB query fails."""
        mock_pool = MagicMock()
        conn_cm = MagicMock()
        conn_cm.__aenter__ = AsyncMock(side_effect=RuntimeError("Connection lost"))
        conn_cm.__aexit__ = AsyncMock(return_value=False)
        mock_pool.connection.return_value = conn_cm
        db_manager.pool = mock_pool
        db_manager._initialized = True

        result = await db_manager.health_check()

        assert result["status"] == "unhealthy"
        assert result["connected"] is False
        assert "error" in result
        assert result["pool_initialized"] is True

    # ------------------------------------------------------------------
    # Singleton helpers
    # ------------------------------------------------------------------

    @pytest.mark.unit
    async def test_get_db_manager_creates_and_initializes(self):
        """Should create a new DatabaseManager and initialize it on first call."""
        mock_instance = MagicMock()
        mock_instance.initialize = AsyncMock(return_value=True)

        with (
            patch("mcp_server.db.DatabaseManager", return_value=mock_instance) as mock_cls,
            patch("mcp_server.db._db_manager", None),
        ):
            from mcp_server.db import get_db_manager

            result = await get_db_manager()

        assert result is mock_instance
        mock_cls.assert_called_once()
        mock_instance.initialize.assert_awaited_once()

    @pytest.mark.unit
    async def test_get_db_manager_returns_singleton(self):
        """Should return the same DatabaseManager instance on repeated calls."""
        mock_instance = MagicMock()
        mock_instance.initialize = AsyncMock(return_value=True)

        with (
            patch("mcp_server.db.DatabaseManager", return_value=mock_instance),
            patch("mcp_server.db._db_manager", None),
        ):
            from mcp_server.db import get_db_manager

            first = await get_db_manager()
            second = await get_db_manager()

        assert first is second
        # initialize should only be called once
        mock_instance.initialize.assert_awaited_once()
