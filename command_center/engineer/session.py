"""Session store for the Live QA Engineer.

Provides in-memory session tracking with vault persistence.
Sessions are stored in a module-level dict and backed by YAML frontmatter
nodes in the Obsidian vault (``Runs/Engineer_Sessions/{session_id}.md``).
Credentials are held only in memory and are **never** written to disk.
"""

from __future__ import annotations

import os
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from .events import (
    AskCredentialEvent,
    AskQuestionEvent,
    BaseEngineerEvent,
    DoneEvent,
    ErrorEvent,
    GreetingEvent,
    PlanProposedEvent,
    ReportEvent,
    TestStartedEvent,
)
from .state_machine import (
    Credentials,
    SessionState,
    Stage,
)

# ---------------------------------------------------------------------------
# Module-level in-memory store (shared across all EngineerSessionStore
# instances — this is intentional for the MVP).
# ---------------------------------------------------------------------------

_store: Dict[str, EngineerSession] = {}
_lock = threading.Lock()


# ---------------------------------------------------------------------------
# EngineerSession
# ---------------------------------------------------------------------------

@dataclass
class EngineerSession:
    """Minimal wrapper around :class:`SessionState`.

    Holds the opaque ``session_id`` and the mutable ``state`` envelope.
    The ``to_event`` helper lets the conversation engine (T9) map a
    pipeline stage to the correct event type without hard-coding the
    dispatch table in multiple places.
    """

    session_id: str
    state: SessionState

    def to_event(self, stage: Stage) -> BaseEngineerEvent:
        """Return the default event for ``stage`` using this session's ID."""
        timestamp = datetime.now(timezone.utc).isoformat()
        if stage == Stage.GREETING:
            return GreetingEvent(
                session_id=self.session_id,
                stage=stage.value,
                timestamp=timestamp,
            )
        if stage == Stage.RECON:
            return AskQuestionEvent(
                session_id=self.session_id,
                stage=stage.value,
                timestamp=timestamp,
                question_id="url",
                prompt="What URL would you like me to test?",
            )
        if stage == Stage.CONTEXT:
            return AskCredentialEvent(
                session_id=self.session_id,
                stage=stage.value,
                timestamp=timestamp,
                field="username",
                reason="This site may require login credentials.",
            )
        if stage == Stage.PLAN:
            return PlanProposedEvent(
                session_id=self.session_id,
                stage=stage.value,
                timestamp=timestamp,
                tests=[],
                site_type="unknown",
            )
        if stage == Stage.EXECUTE:
            return TestStartedEvent(
                session_id=self.session_id,
                stage=stage.value,
                timestamp=timestamp,
                test_id="",
                role="",
            )
        if stage == Stage.REPORT:
            return ReportEvent(
                session_id=self.session_id,
                stage=stage.value,
                timestamp=timestamp,
                sections={},
            )
        if stage == Stage.DONE:
            return DoneEvent(
                session_id=self.session_id,
                stage=stage.value,
                timestamp=timestamp,
            )
        return ErrorEvent(
            session_id=self.session_id,
            stage=stage.value,
            timestamp=timestamp,
            code="unknown_stage",
            message=f"Unhandled stage: {stage.value}",
        )


# ---------------------------------------------------------------------------
# EngineerSessionStore
# ---------------------------------------------------------------------------

class EngineerSessionStore:
    """Manages engineer session lifecycle with vault persistence.

    All public methods are thread-safe via a module-level
    :class:`threading.Lock`.
    """

    def __init__(self, vault_path: Optional[Path] = None):
        self.vault_path = vault_path or Path(
            os.getenv("OBSIDIAN_VAULT_PATH", "/app/obsidian_vault")
        )
        self._sessions = _store
        self._lock = _lock

        self._sessions_dir = self.vault_path / "Runs" / "Engineer_Sessions"
        self._sessions_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def create(self, url: Optional[str] = None) -> EngineerSession:
        """Create a new session, persist initial vault node, and return it."""
        session_id = str(uuid.uuid4())
        state = SessionState(session_id=session_id, url=url)
        session = EngineerSession(session_id=session_id, state=state)

        with self._lock:
            self._sessions[session_id] = session
            self._write_vault_node(session)

        return session

    def get(self, session_id: str) -> Optional[EngineerSession]:
        """Retrieve an active session by ID."""
        with self._lock:
            return self._sessions.get(session_id)

    def update(self, session_id: str, **kwargs: Any) -> None:
        """Update session fields, refresh ``last_activity_at``, write vault.

        ``credentials`` is accepted in-memory but is **never** persisted
        to the vault node.
        """
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise KeyError(f"Session {session_id!r} not found")

            for key, value in kwargs.items():
                if key == "credentials" and isinstance(value, dict):
                    value = Credentials(**value)
                elif key == "current_stage" and isinstance(value, str):
                    value = Stage(value)
                elif key == "site_type" and isinstance(value, str):
                    from .site_catalog import SiteType
                    value = SiteType(value)

                if not hasattr(session.state, key):
                    raise AttributeError(
                        f"SessionState has no attribute {key!r}"
                    )
                setattr(session.state, key, value)

            session.state.last_activity_at = datetime.now(timezone.utc)
            self._write_vault_node(session)

    def delete(self, session_id: str) -> None:
        """Remove session from memory and delete its vault node."""
        with self._lock:
            self._sessions.pop(session_id, None)
            node_path = self._sessions_dir / f"{session_id}.md"
            if node_path.exists():
                node_path.unlink()

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def list_active(self) -> List[EngineerSession]:
        """Return a snapshot of all active sessions."""
        with self._lock:
            return list(self._sessions.values())

    def cleanup_idle(self, ttl_seconds: int = 1800) -> int:
        """Evict sessions whose ``last_activity_at`` is older than ``ttl``.

        Returns the number of sessions evicted.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=ttl_seconds)
        with self._lock:
            to_evict = [
                sid
                for sid, sess in self._sessions.items()
                if sess.state.last_activity_at <= cutoff
            ]
            for sid in to_evict:
                self._sessions.pop(sid, None)
                node_path = self._sessions_dir / f"{sid}.md"
                if node_path.exists():
                    node_path.unlink()
            return len(to_evict)

    # ------------------------------------------------------------------
    # Vault I/O
    # ------------------------------------------------------------------

    def _write_vault_node(self, session: EngineerSession) -> None:
        """Serialize session state to a vault markdown node.

        The ``credentials`` field is explicitly excluded for security.
        """
        state = session.state
        data = state.model_dump()

        # NEVER persist credentials
        data.pop("credentials", None)

        # Convert enum values to strings
        data["current_stage"] = data["current_stage"].value
        if data.get("site_type") is not None:
            data["site_type"] = data["site_type"].value

        # Convert datetime objects to ISO-8601 strings
        for dt_key in ("started_at", "last_activity_at"):
            if data.get(dt_key) is not None:
                data[dt_key] = data[dt_key].isoformat()

        # Convert transition rows
        if data.get("transitions_log"):
            for row in data["transitions_log"]:
                row["from_stage"] = row["from_stage"].value
                row["to_stage"] = row["to_stage"].value
                row["at"] = row["at"].isoformat()

        body = (
            f"# Engineer Session: {state.session_id}\n\n"
            f"Stage: {state.current_stage.value}\n"
        )
        if state.url:
            body += f"\nURL: {state.url}\n"

        yaml_content = yaml.dump(data, default_flow_style=False, allow_unicode=True)
        full_content = f"---\n{yaml_content}---\n\n{body}"

        node_path = self._sessions_dir / f"{state.session_id}.md"
        node_path.write_text(full_content, encoding="utf-8")
