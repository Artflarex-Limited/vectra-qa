"""State machine for the Live QA Engineer intake conversation.

This module is the **rule-based** authority for which pipeline stage the
conversation is in, which stages it may move to next, and whether the
move is *monotonic* (forward, step-by-step, no skipping) or a
*backward* move that needs explicit user intent.

The state machine is intentionally **not** LLM-driven.  The LLM may
emit free-form conversation content, but the LLM never decides which
stage we are in and never decides when to transition.  All transitions
are decided by code in :mod:`command_center.engineer.conversation`
(T9) based on the static rules encoded here.

Pipeline overview
-----------------

::

    GREETING → RECON → CONTEXT → PLAN → EXECUTE → REPORT → DONE
                  ↑       ↑       ↑       (DONE is terminal)

Same-stage self-transitions are allowed where they make sense (re-recon
on URL change, re-context on user correction, re-plan after a "go
back").  Backward transitions are permitted **only** when the user
uttered the explicit "go back" keyword — that intent is forwarded to
:func:`assert_monotonic` as ``go_back_keyword`` so the guard is
synchronous and self-evident in the call-site.

Public surface
--------------

* :class:`Stage` — the seven-stage enum.
* :class:`Credentials` — username / password pair, **never** persisted
  to disk (the ``SessionState`` only holds it in memory).
* :class:`Transition` — one row in the audit log.
* :class:`SessionState` — the full per-session state envelope.
* :data:`ALLOWED_TRANSITIONS` — static map of legal next stages.
* :func:`can_transition` — pure function over the static map.
* :func:`assert_monotonic` — *dynamic* check; raises on illegal moves.
* :func:`requires_credential` — credential-need predicate used by the
  ``CONTEXT`` stage to decide whether to ask for a password.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Union

from pydantic import BaseModel, ConfigDict, Field

from .site_catalog import CREDENTIAL_REQUIRED, SiteType


# ---------------------------------------------------------------------------
# Stage enum
# ---------------------------------------------------------------------------


class Stage(str, Enum):
    """The seven logical stages of a live QA engineer session.

    The string value is the public wire format — it shows up in
    ``EngineerEvent.stage`` and in the dashboard URL.  ``str`` mixin
    keeps the value flat for JSON and matches the convention used by
    :class:`SiteType` in :mod:`.site_catalog`.
    """

    GREETING = "greeting"
    RECON = "recon"
    CONTEXT = "context"
    PLAN = "plan"
    EXECUTE = "execute"
    REPORT = "report"
    DONE = "done"


# Canonical numeric rank of each stage.  Used by ``assert_monotonic``
# to detect skips and to drive the (deliberately small) finite-state
# machine.  Order is significant: it mirrors the happy path the user
# is guided through.
STAGE_RANK: Dict[Stage, int] = {
    Stage.GREETING: 0,
    Stage.RECON: 1,
    Stage.CONTEXT: 2,
    Stage.PLAN: 3,
    Stage.EXECUTE: 4,
    Stage.REPORT: 5,
    Stage.DONE: 6,
}


# ---------------------------------------------------------------------------
# Allowed transitions
# ---------------------------------------------------------------------------


#: Static, exhaustive list of legal ``(from_stage -> next_stage)`` moves.
#:
#: This is the single source of truth for *what may happen*.  Same-stage
#: self-transitions are intentionally included where they make sense
#: (``RECON`` for a URL change, ``CONTEXT`` for user correction).  The
#: terminal ``DONE`` stage has an empty target set.
#:
#: .. note::
#:
#:    The map is *static*.  The dynamic guard
#:    :func:`assert_monotonic` still rejects backward moves unless the
#:    user supplies a "go back" keyword — so e.g. ``PLAN -> CONTEXT``
#:    passes ``can_transition`` but raises from ``assert_monotonic``
#:    without that keyword.
ALLOWED_TRANSITIONS: Dict[Stage, Set[Stage]] = {
    Stage.GREETING: {Stage.RECON},
    Stage.RECON: {Stage.RECON, Stage.CONTEXT},  # re-recon on URL change
    Stage.CONTEXT: {Stage.CONTEXT, Stage.PLAN},
    Stage.PLAN: {Stage.CONTEXT, Stage.EXECUTE},  # back if user wants to change context
    Stage.EXECUTE: {Stage.REPORT},
    Stage.REPORT: {Stage.DONE},
    Stage.DONE: set(),  # terminal
}


# ---------------------------------------------------------------------------
# Credential model
# ---------------------------------------------------------------------------


class Credentials(BaseModel):
    """In-memory username / password pair.

    The instance lives only on :class:`SessionState` while the
    conversation is active.  It is **never** serialised to the Obsidian
    vault, the structured log, the agent objective, or any persistent
    store.  See T10 for the ``never-persist`` assertion.
    """

    model_config = ConfigDict(extra="forbid")

    username: Optional[str] = Field(default=None, description="Login username / email.")
    password: Optional[str] = Field(default=None, description="Login password. Never logged.")


# ---------------------------------------------------------------------------
# Transition audit row
# ---------------------------------------------------------------------------


class Transition(BaseModel):
    """One row in :attr:`SessionState.transitions_log`.

    The full audit trail lets post-mortem tooling (and the report
    builder in T12) reconstruct the exact path the user took, including
    rejected attempts and re-recons.  ``by`` is a free-form string so
    we can record ``"user"``, ``"system"``, or any future source such
    as ``"classifier:re-recon"``.
    """

    model_config = ConfigDict(extra="forbid")

    from_stage: Stage = Field(..., description="Stage the session left.")
    to_stage: Stage = Field(..., description="Stage the session entered.")
    at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp of the transition.",
    )
    by: str = Field(
        default="system",
        description=(
            "Initiator of the transition. ``\"user\"`` when triggered "
            "by user input, ``\"system\"`` when the pipeline itself "
            "advanced the state, ``\"classifier:...\"`` etc. for "
            "machine-driven moves."
        ),
    )


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------


def _utcnow() -> datetime:
    """``datetime.now(timezone.utc)`` helper (also used as a default factory)."""
    return datetime.now(timezone.utc)


class SessionState(BaseModel):
    """Per-session state for one live QA engineer conversation.

    A single :class:`SessionState` instance represents the full
    lifetime of one user-driven run — from greeting to done.  It is
    constructed in T7 (``EngineerSession.__init__``) and mutated by the
    conversation engine (T9) as the user makes progress.
    """

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(..., description="Opaque session identifier.")
    current_stage: Stage = Field(
        default=Stage.GREETING,
        description="Pipeline stage the session is currently in.",
    )
    site_type: Optional[SiteType] = Field(
        default=None,
        description="Classified site type, ``None`` until recon finishes.",
    )
    url: Optional[str] = Field(
        default=None,
        description="Target URL the user wants tested. Set during recon.",
    )
    credentials: Optional[Credentials] = Field(
        default=None,
        description=(
            "In-memory credentials. Populated during the CONTEXT stage "
            "for site types in ``CREDENTIAL_REQUIRED``; never persisted."
        ),
    )
    gathered_context: Dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Free-form facts collected during CONTEXT (audience, "
            "critical flows, devices, etc.). Keys are plain English."
        ),
    )
    confirmed_plan: Optional[List[str]] = Field(
        default=None,
        description=(
            "User-confirmed test list. ``None`` until the PLAN stage "
            "is approved; a non-empty list once the user signs off."
        ),
    )
    started_at: datetime = Field(
        default_factory=_utcnow,
        description="UTC timestamp of session creation.",
    )
    last_activity_at: datetime = Field(
        default_factory=_utcnow,
        description="UTC timestamp of the most recent user / system action.",
    )
    transitions_log: List[Transition] = Field(
        default_factory=list,
        description=(
            "Append-only audit log of every stage change (including "
            "same-stage self-transitions and rejected attempts)."
        ),
    )


# ---------------------------------------------------------------------------
# Pure transition predicates
# ---------------------------------------------------------------------------


def can_transition(from_stage: Stage, to_stage: Stage) -> bool:
    """Return ``True`` iff the static rules allow ``from_stage -> to_stage``.

    This is the *static* guard.  It does not know about session state
    and does not enforce monotonicity.  Use :func:`assert_monotonic`
    for that.

    Same-stage self-transitions are reported honestly: ``can_transition``
    returns ``True`` for them if (and only if) the stage is listed as a
    legal target of itself in :data:`ALLOWED_TRANSITIONS`.
    """
    if from_stage not in ALLOWED_TRANSITIONS:
        return False
    return to_stage in ALLOWED_TRANSITIONS[from_stage]


def assert_monotonic(
    state: SessionState,
    new_stage: Stage,
    *,
    go_back_keyword: Optional[str] = None,
) -> None:
    """Assert that ``state`` may legally move to ``new_stage``.

    Two failure modes raise :class:`ValueError`:

    1. **Forward skip** — ``new_stage`` is more than one rank ahead of
       ``state.current_stage``.  For example, ``GREETING -> EXECUTE``
       skips ``RECON``, ``CONTEXT``, and ``PLAN`` and is rejected even
       if the user explicitly asked for it.  The pipeline enforces a
       stage-by-stage narrative; the LLM is not allowed to compress it.

    2. **Backward move without consent** — ``new_stage`` is ranked
       below ``state.current_stage`` and the caller did not pass a
       ``go_back_keyword``.  The caller is expected to detect the
       explicit user intent ("go back", "change my answer", ...) and
       forward the matched token through here.

    Passing a non-empty ``go_back_keyword`` *unconditionally* authorises
    any backward move: the keyword is treated as proof of user intent,
    not as a stage-specific magic string.  Forward skips are **never**
    authorised by the keyword.

    Same-stage self-transitions are always allowed (they represent
    re-asking or re-confirmation, not pipeline progress).

    Parameters
    ----------
    state:
        The current :class:`SessionState`.  Only ``state.current_stage``
        is consulted.
    new_stage:
        The stage the caller intends to move into.
    go_back_keyword:
        Non-empty string captured from the user message that
        unambiguously signals "go back".  Required for any backward
        move; ignored for forward / same-stage moves.

    Raises
    ------
    ValueError
        On forward skip or on backward move without
        ``go_back_keyword``.  The error message names the offending
        move so it is easy to surface in a ``narrate`` event.
    """
    if not isinstance(new_stage, Stage):
        # Guard against stringly-typed callers; we want a clean error
        # at the boundary rather than a confusing KeyError later.
        raise TypeError(
            f"assert_monotonic: new_stage must be a Stage member, "
            f"got {type(new_stage).__name__}: {new_stage!r}"
        )

    current = state.current_stage
    if new_stage == current:
        # Self-transition (re-recon, re-context, re-plan) is fine.
        return

    current_rank = STAGE_RANK[current]
    new_rank = STAGE_RANK[new_stage]

    if new_rank < current_rank:
        # Backward move: must be explicitly authorised.
        if not go_back_keyword or not go_back_keyword.strip():
            raise ValueError(
                f"Backward transition {current.value!r} -> {new_stage.value!r} "
                f"requires the user-supplied 'go back' keyword. "
                f"Pass it as the go_back_keyword argument to assert_monotonic."
            )
        # Keyword present: authorise.  We deliberately do not match
        # against a fixed string; the caller is responsible for
        # detecting the user's intent and forwarding the matched token.
        return

    # Forward move.  Reject any skip > 1 stage.  (Rank diff == 1 is
    # the only legal forward move; same-rank was already handled.)
    if new_rank - current_rank > 1:
        raise ValueError(
            f"Skipping stages is not allowed: {current.value!r} -> "
            f"{new_stage.value!r} jumps {new_rank - current_rank} "
            f"stages. Advance one stage at a time."
        )


def requires_credential(stage: Stage, site_type: Optional[Union[SiteType, str]]) -> bool:
    """Return ``True`` iff ``stage`` should request credentials for ``site_type``.

    The policy is intentionally narrow:

    * The credential request is fired **only** at the ``CONTEXT`` stage.
      Other stages do not need the user to re-enter a password and
      must not re-prompt (it would be both annoying and a sign of
      session-state leakage).
    * The site must be in :data:`CREDENTIAL_REQUIRED`.  Public-facing
      site types (landing pages, blogs) never need a login.

    Accepts ``site_type`` as either a :class:`SiteType` member or its
    string value (``"ecommerce"``) so the function is convenient at
    the conversation-engine call-site, which may have either form in
    hand.  ``None`` and unknown strings both correctly return
    ``False``.
    """
    if stage != Stage.CONTEXT:
        return False
    if site_type is None:
        return False
    return site_type in CREDENTIAL_REQUIRED


__all__ = [
    "Stage",
    "STAGE_RANK",
    "ALLOWED_TRANSITIONS",
    "Credentials",
    "Transition",
    "SessionState",
    "can_transition",
    "assert_monotonic",
    "requires_credential",
]
