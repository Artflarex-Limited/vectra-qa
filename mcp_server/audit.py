"""
Audit logging for Vectra QA MCP Server.
Dual output: structlog (stdout JSON) + PostgreSQL audit_log table.
"""

import json
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any

import structlog

logger = structlog.get_logger()

# Audit event types
EVENT_AGENT_SPAWN = "agent_spawn"
EVENT_AGENT_TERMINATE = "agent_terminate"
EVENT_AGENT_EXIT = "agent_exit"
EVENT_TEST_RUN_START = "test_run_start"
EVENT_TEST_RUN_COMPLETE = "test_run_complete"
EVENT_TOOL_CALL = "tool_call"
EVENT_VAULT_ACCESS = "vault_access"
EVENT_AUTH_ATTEMPT = "auth_attempt"
EVENT_ERROR = "error"


class AuditLogger:
    """Dual-output audit logger: structlog + PostgreSQL."""

    def __init__(self, db_pool=None):
        self.db_pool = db_pool

    async def log(
        self,
        event_type: str,
        actor: Optional[str] = None,
        resource: Optional[str] = None,
        action: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        event_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()

        # 1. Log to structlog (stdout JSON)
        log_details = details or {}
        logger.info(
            "audit_event",
            event_id=event_id,
            event_type=event_type,
            actor=actor,
            resource=resource,
            action=action,
            timestamp=timestamp,
            **log_details
        )

        # 2. Persist to PostgreSQL if pool available
        if self.db_pool:
            try:
                await self._persist_to_db(event_id, timestamp, event_type, actor, resource, action, details)
            except Exception as e:
                logger.error("audit_db_persist_failed", event_id=event_id, error=str(e))

    async def _persist_to_db(self, event_id, timestamp, event_type, actor, resource, action, details):
        """Persist audit event to PostgreSQL."""
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO audit_log (event_id, timestamp, event_type, actor, resource, action, details)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (event_id) DO NOTHING
                """,
                event_id, timestamp, event_type, actor, resource, action, json.dumps(details)
            )


# Global audit logger instance
_audit_logger: Optional[AuditLogger] = None


def get_audit_logger() -> AuditLogger:
    """Get or create the AuditLogger singleton."""
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
    return _audit_logger


def set_db_pool(db_pool):
    """Set the database pool for audit logging."""
    audit = get_audit_logger()
    audit.db_pool = db_pool


# Convenience functions
async def log_agent_spawn(agent_id: str, role: str, objective: str, actor: str = "system"):
    """Log agent spawn event."""
    await get_audit_logger().log(
        event_type=EVENT_AGENT_SPAWN,
        actor=actor,
        resource=f"agents/{agent_id}",
        action="spawn",
        details={"agent_id": agent_id, "role": role, "objective_hash": hash(objective)}
    )


async def log_agent_terminate(agent_id: str, reason: str, actor: str = "system"):
    """Log agent terminate event."""
    await get_audit_logger().log(
        event_type=EVENT_AGENT_TERMINATE,
        actor=actor,
        resource=f"agents/{agent_id}",
        action="terminate",
        details={"reason": reason}
    )


async def log_test_run_start(test_id: str, test_type: str, target_url: str):
    """Log test run start."""
    await get_audit_logger().log(
        event_type=EVENT_TEST_RUN_START,
        resource=f"tests/{test_id}",
        action="start",
        details={"test_type": test_type, "target_url": target_url}
    )


async def log_test_run_complete(test_id: str, status: str, duration_ms: int):
    """Log test run completion."""
    await get_audit_logger().log(
        event_type=EVENT_TEST_RUN_COMPLETE,
        resource=f"tests/{test_id}",
        action="complete",
        details={"status": status, "duration_ms": duration_ms}
    )


async def log_tool_call(tool_name: str, params: Dict[str, Any], actor: str = "system"):
    """Log tool call (params sanitized)."""
    sanitized = {k: v for k, v in params.items() if k not in ("password", "token", "secret", "api_key")}
    await get_audit_logger().log(
        event_type=EVENT_TOOL_CALL,
        actor=actor,
        resource=f"tools/{tool_name}",
        action="call",
        details={"params": sanitized}
    )


# SQL for creating the audit_log table
AUDIT_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS audit_log (
    id BIGSERIAL PRIMARY KEY,
    event_id VARCHAR(36) UNIQUE NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    actor VARCHAR(100),
    resource VARCHAR(255),
    action VARCHAR(100),
    details JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_audit_log_timestamp ON audit_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_log_event_type ON audit_log(event_type);
CREATE INDEX IF NOT EXISTS idx_audit_log_actor ON audit_log(actor);
CREATE INDEX IF NOT EXISTS idx_audit_log_resource ON audit_log(resource);
"""