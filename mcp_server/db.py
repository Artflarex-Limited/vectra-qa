"""
PostgreSQL Connection Manager for Vectra QA.

Provides async connection pooling, health checks, and retry logic.
Uses psycopg[binary] for async PostgreSQL operations.
"""

import os
import asyncio
from typing import Any, Dict, List, Optional
from contextlib import asynccontextmanager

import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

try:
    import psycopg
    from psycopg.rows import dict_row

    PSYCOPG_AVAILABLE = True
except ImportError:
    PSYCOPG_AVAILABLE = False

logger = structlog.get_logger()

# Configuration
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://vectra:vectra_dev_password_change_in_production@localhost:5432/vectra_qa",
)
DB_POOL_MIN_SIZE = int(os.getenv("DB_POOL_MIN_SIZE", "2"))
DB_POOL_MAX_SIZE = int(os.getenv("DB_POOL_MAX_SIZE", "10"))


class DatabaseManager:
    """Manages PostgreSQL connection pool and queries."""

    def __init__(self):
        self.pool: Optional[Any] = None
        self._initialized = False
        self._lock = asyncio.Lock()

    async def initialize(self) -> bool:
        """Initialize the connection pool."""
        if self._initialized:
            return True

        if not PSYCOPG_AVAILABLE:
            logger.warning(
                "psycopg_not_installed",
                message="PostgreSQL support disabled. Install with: pip install psycopg[binary]",
            )
            return False

        async with self._lock:
            if self._initialized:
                return True

            try:
                self.pool = await psycopg.AsyncConnectionPool(
                    conninfo=DATABASE_URL,
                    min_size=DB_POOL_MIN_SIZE,
                    max_size=DB_POOL_MAX_SIZE,
                    kwargs={"row_factory": dict_row},
                )
                self._initialized = True
                logger.info(
                    "database_pool_initialized",
                    min_size=DB_POOL_MIN_SIZE,
                    max_size=DB_POOL_MAX_SIZE,
                )
                return True
            except Exception as e:
                logger.error("database_pool_init_failed", error=str(e))
                return False

    async def close(self):
        """Close the connection pool."""
        if self.pool:
            await self.pool.close()
            self._initialized = False
            logger.info("database_pool_closed")

    @asynccontextmanager
    async def connection(self):
        """Get a connection from the pool."""
        if not self._initialized:
            await self.initialize()

        if not self.pool:
            raise RuntimeError("Database pool not initialized")

        async with self.pool.connection() as conn:
            yield conn

    @asynccontextmanager
    async def transaction(self):
        """Get a connection with transaction."""
        async with self.connection() as conn:
            async with conn.transaction():
                yield conn

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
    async def execute(self, query: str, params: Optional[tuple] = None) -> str:
        """Execute a query and return command status."""
        async with self.connection() as conn:
            result = await conn.execute(query, params)
            return result.statusmessage

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
    async def fetchone(
        self, query: str, params: Optional[tuple] = None
    ) -> Optional[Dict[str, Any]]:
        """Fetch a single row."""
        async with self.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(query, params)
                return await cur.fetchone()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
    async def fetchall(self, query: str, params: Optional[tuple] = None) -> List[Dict[str, Any]]:
        """Fetch all rows."""
        async with self.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(query, params)
                return await cur.fetchall()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
    async def fetchval(self, query: str, params: Optional[tuple] = None) -> Any:
        """Fetch a single value."""
        row = await self.fetchone(query, params)
        if row:
            return next(iter(row.values()))
        return None

    async def health_check(self) -> Dict[str, Any]:
        """Check database health."""
        try:
            start = asyncio.get_event_loop().time()
            await self.fetchval("SELECT 1")
            latency = (asyncio.get_event_loop().time() - start) * 1000
            return {
                "status": "healthy",
                "connected": True,
                "latency_ms": round(latency, 2),
                "pool_initialized": self._initialized,
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "connected": False,
                "error": str(e),
                "pool_initialized": self._initialized,
            }


# Global singleton instance
_db_manager: Optional[DatabaseManager] = None


async def get_db_manager() -> DatabaseManager:
    """Get or create the DatabaseManager singleton."""
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
        await _db_manager.initialize()
    return _db_manager


def get_db_manager_sync() -> DatabaseManager:
    """Synchronous access to db manager (for non-async contexts)."""
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
        # Note: initialize() must be called in async context
    return _db_manager
