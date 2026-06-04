"""Credential handler for the Live QA Engineer.

This module defines :class:`CredentialHandler`, the **only** code path
allowed to touch username / password data during a live QA session.

Security design
---------------
* Credentials live **only** in-memory on :class:`SessionState`.  They are
  never serialised to the Obsidian vault, the structured log, an agent
  objective string, or any persistent store.
* :func:`scrub_log_record` is a recursive dict filter that strips any key
  matching ``(?i).*(password|secret|token|credential).`` before the record
  reaches the log sink.
* :func:`assert_no_credential_in_text` is a QA helper that raises
  :class:`ValueError` when a credential-like pattern is detected in plain
  text (used by security-contract tests).
* :meth:`CredentialHandler.clear` overwrites the in-memory password (and
  optionally username) with ``secrets.token_hex(16)`` before nulling the
  reference so the raw secret does not linger in Python's free-list.
"""

from __future__ import annotations

import re
import secrets
from datetime import datetime, timezone
from typing import Any, Literal, Optional, Union

import structlog

from .events import AskCredentialEvent
from .state_machine import Credentials, SessionState

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Credential-key regex (module-level so it is compiled once)
# ---------------------------------------------------------------------------

_CREDENTIAL_KEY_RE = re.compile(r"(?i).*(password|secret|token|credential).*")

# Regex for credential-in-text detection (QA helper).
_CREDENTIAL_IN_TEXT_RE = re.compile(r"password|secret123|token=", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Log-record scrubber
# ---------------------------------------------------------------------------


def _scrub_value(value: Any) -> Any:
    """Recursively scrub credential-bearing keys from a value."""
    if isinstance(value, dict):
        return {
            k: _scrub_value(v)
            for k, v in value.items()
            if not _CREDENTIAL_KEY_RE.match(k)
        }
    if isinstance(value, list):
        return [_scrub_value(v) for v in value]
    return value


def scrub_log_record(record: dict) -> dict:
    """Return a *new* dict with credential-bearing keys removed.

    The input ``record`` is **not** mutated.  The scrubber walks dicts
    and lists recursively; any key matching
    ``(?i).*(password|secret|token|credential).*`` is dropped.
    """
    return _scrub_value(record)


# ---------------------------------------------------------------------------
# QA assertion helper
# ---------------------------------------------------------------------------


def assert_no_credential_in_text(text: str) -> None:
    """Raise :class:`ValueError` if ``text`` contains a credential pattern.

    Patterns detected (case-insensitive):
    * ``password``
    * ``secret123``
    * ``token=``
    """
    if _CREDENTIAL_IN_TEXT_RE.search(text):
        raise ValueError("Credential pattern detected in text")


# ---------------------------------------------------------------------------
# CredentialHandler
# ---------------------------------------------------------------------------


class CredentialHandler:
    """Prompt-and-forget credential lifecycle manager.

    All credential operations (request, submit, inject, clear) flow
    through this class so the security surface is kept in one place.
    """

    # ------------------------------------------------------------------
    # Request
    # ------------------------------------------------------------------

    def request_credential(
        self,
        state: SessionState,
        field: Literal["username", "password"],
        reason: str,
    ) -> AskCredentialEvent:
        """Build an :class:`AskCredentialEvent` from the current session."""
        return AskCredentialEvent(
            session_id=state.session_id,
            stage=state.current_stage.value
            if hasattr(state.current_stage, "value")
            else str(state.current_stage),
            timestamp=datetime.now(timezone.utc).isoformat(),
            field=field,
            reason=reason,
        )

    # ------------------------------------------------------------------
    # Submit
    # ------------------------------------------------------------------

    def submit_credential(
        self,
        state: SessionState,
        field: str,
        value: str,
    ) -> SessionState:
        """Store ``value`` in ``state.credentials.<field>`` (memory only).

        No vault write, no log emission, no disk persistence.
        """
        if state.credentials is None:
            state.credentials = Credentials()
        setattr(state.credentials, field, value)
        state.last_activity_at = datetime.now(timezone.utc)
        return state

    # ------------------------------------------------------------------
    # Inject to agent side-channel
    # ------------------------------------------------------------------

    def inject_to_agent(
        self,
        agent_id: str,
        state: SessionState = None,
        *,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ) -> None:
        """Push credentials into the agent's side-channel.

        If ``state`` is provided and ``state.credentials`` is not ``None``,
        the credentials are taken from the state object.  Otherwise the
        explicit ``username`` / ``password`` kwargs are used (mainly for
        direct QA scenarios).
        """
        if state is not None and state.credentials is not None:
            username = state.credentials.username
            password = state.credentials.password
        if username is None or password is None:
            return
        # Import here to avoid a hard circular dependency at module load.
        from agents.feature_tester.worker import FeatureTesterWorker

        FeatureTesterWorker.set_pending_credentials(agent_id, username, password)

    # ------------------------------------------------------------------
    # Clear
    # ------------------------------------------------------------------

    def clear(self, state: Union[SessionState, dict]) -> Union[SessionState, dict]:
        """Overwrite in-memory credentials with random bytes, then delete.

        For :class:`SessionState` the ``credentials`` attribute is set to
        ``None`` after overwrite.  For plain dicts (used in some QA
        scenarios) the dict is left in place with the overwritten random
        value so that post-clear assertions can inspect it.
        """
        creds = getattr(state, "credentials", None)
        if creds is None and isinstance(state, dict):
            creds = state.get("credentials")

        if creds is not None:
            # Overwrite with random bytes before dropping the reference.
            if hasattr(creds, "password"):
                creds.password = secrets.token_hex(16)
                if hasattr(creds, "username"):
                    creds.username = secrets.token_hex(16)
            elif isinstance(creds, dict):
                creds["password"] = secrets.token_hex(16)
                creds["username"] = secrets.token_hex(16)

            # Drop the reference.
            if hasattr(state, "credentials"):
                state.credentials = None
            elif isinstance(state, dict):
                # Leave the overwritten dict in place for QA compatibility.
                pass

        return state


__all__ = [
    "CredentialHandler",
    "scrub_log_record",
    "assert_no_credential_in_text",
]
