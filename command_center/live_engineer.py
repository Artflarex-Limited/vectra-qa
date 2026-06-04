"""LiveEngineer — top-level orchestrator for the live QA engineer.

Wires together all engineer/* modules into a single callable surface:
* Session lifecycle (create, resume, update)
* Conversation (greeting, turns, stage transitions)
* Classification (heuristic + LLM site-type detection)
* Credential handling (prompt, submit, inject — never persist)
* Execution (mock for MVP; real orchestrator in T14)
* Reporting (plain-English report builder)
* Metrics (per-session latency and breach tracking)
* Narration (plain-English SSE translation)

Security rules (enforced in code)
---------------------------------
1. Credentials are **never** passed to ``session_store.update()``.
2. Credentials are **never** logged or echoed in events.
3. ``CredentialHandler.submit_credential`` mutates memory only.
4. ``_prepare_agent`` injects credentials via the side-channel
   (``FeatureTesterWorker.set_pending_credentials``) only when
   ``site_type`` is in ``CREDENTIAL_REQUIRED``.

Design notes
------------
* The ``orchestrator`` parameter is optional and lazy-imported to avoid
  circular imports at module load time.
* ``_run_execution`` is intentionally synchronous-for-MVP: it emits
  ``TestStartedEvent`` + ``TestCompletedEvent`` pairs without blocking
  on real agent spawning. T14 replaces this with async orchestrator
  calls.
* Every public method is ``async`` so the FastAPI layer (T14) can
  ``await`` uniformly.
"""

from __future__ import annotations

from dotenv import load_dotenv
load_dotenv()  # load .env so the LLM router can see provider keys

import asyncio  # noqa: F401
import structlog
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from command_center.engineer.classifier import SiteClassifier, validate_override  # noqa: F401
from command_center.engineer.conversation import ConversationEngine
from command_center.engineer.credentials import CredentialHandler, scrub_log_record  # noqa: F401
from command_center.engineer.events import (
    AskCredentialEvent,  # noqa: F401
    AskQuestionEvent,  # noqa: F401
    BaseEngineerEvent,
    ClassifySiteEvent,
    ConfirmClassificationEvent,
    DoneEvent,
    EngineerEvent,  # noqa: F401
    ErrorEvent,  # noqa: F401
    NarrateEvent,  # noqa: F401
    PlanProposedEvent,
    ReportEvent,  # noqa: F401
    TestStartedEvent,
)
from command_center.engineer.metrics import MetricsConfig, MetricsRecorder  # noqa: F401
from command_center.engineer.narrator import Narrator
from command_center.engineer.report import ReportBuilder
from command_center.engineer.session import EngineerSession, EngineerSessionStore
from command_center.engineer.site_catalog import CREDENTIAL_REQUIRED, SiteType
from command_center.engineer.state_machine import (
    STAGE_RANK,  # noqa: F401
    SessionState,
    Stage,
    assert_monotonic,  # noqa: F401
    requires_credential,  # noqa: F401
)
from command_center.engineer.agents import STAGE_AGENTS

logger = structlog.get_logger("engineer.live_engineer")

import re as _re_for_url
_URL_RE = _re_for_url.compile(
    r"https?://[^\s<>\"]+|www\.[^\s<>\"]+|[a-zA-Z0-9][a-zA-Z0-9-]{0,61}\.[a-zA-Z]{2,}(?:/[^\s]*)?"
)


def _extract_url(text: str) -> Optional[str]:
    """Extract a URL from free text. Returns the URL with http:// prepended
    if it was a bare domain."""
    if not text:
        return None
    m = _URL_RE.search(text)
    if not m:
        return None
    url = m.group(0).rstrip(".,;:!?)")
    if not url.startswith(("http://", "https://")):
        url = "http://" + url  # bare domain; classifier will follow redirects
    return url


# ---------------------------------------------------------------------------
# Static test-name -> agent-role mapping for MVP execution.
# ---------------------------------------------------------------------------

_TEST_ROLE_MAP: Dict[str, str] = {
    "homepage": "ui_explorer",
    "navigation": "ui_explorer",
    "product_search": "ui_explorer",
    "cart_flow": "ui_explorer",
    "checkout_flow": "ui_explorer",
    "auth_login": "auth_tester",
    "responsive": "ui_explorer",
    "accessibility": "accessibility_tester",
    "content_links": "ui_explorer",
    "dashboard_load": "ui_explorer",
    "core_feature_smoke": "ui_explorer",
    "role_based_access": "auth_tester",
    "data_table_render": "ui_explorer",
}


class LiveEngineer:
    """Top-level orchestrator that wires all engineer modules together."""

    def __init__(
        self,
        llm: Optional[Any] = None,
        orchestrator: Optional[Any] = None,
    ) -> None:
        self.session_store = EngineerSessionStore()
        self.classifier = SiteClassifier(llm=llm)
        self.conversation = ConversationEngine(llm=llm)
        self.credentials = CredentialHandler()
        self.narrator = Narrator(llm=llm)
        self.report = ReportBuilder(llm=llm)
        self.metrics = MetricsRecorder()
        self.orchestrator = orchestrator  # lazy-imported if None
        self.agents: Dict[Stage, Any] = {
            stage: cls(
                llm=llm,
                conversation=self.conversation,
                narrator=self.narrator,
                classifier=self.classifier,
                report_builder=self.report,
            )
            for stage, cls in STAGE_AGENTS.items()
        }

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    async def start_session(
        self,
        url: Optional[str] = None,
        existing_session_id: Optional[str] = None,
    ) -> Tuple[EngineerSession, List[BaseEngineerEvent]]:
        """Create a new session or resume an existing one.

        Returns the session and a list containing at minimum a
        :class:`GreetingEvent`.
        """
        if existing_session_id is not None:
            sess = self.session_store.get(existing_session_id)
            if sess is not None:
                events = await self.resume_session(existing_session_id)
                return sess, events

        sess = self.session_store.create(url=url)
        events = await self.agents[Stage.GREETING].run(
            sess.state, context={"action": "start"}
        )
        return sess, events

    async def resume_session(self, session_id: str) -> List[BaseEngineerEvent]:
        """Return the event list that represents the session's current stage.

        Used on page refresh so the UI can rehydrate without losing context.
        """
        sess = self.session_store.get(session_id)
        if sess is None:
            raise KeyError(f"Session {session_id!r} not found")

        stage = sess.state.current_stage
        if stage == Stage.DONE:
            events = [
                DoneEvent(
                    session_id=sess.session_id,
                    stage=stage,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
            ]
        else:
            events = await self.agents[stage].run(
                sess.state, context={"action": "resume"}
            )
        return events

    # ------------------------------------------------------------------
    # Message handling
    # ------------------------------------------------------------------

    async def handle_message(
        self,
        session_id: str,
        user_message: str,
        credential: Optional[Dict[str, str]] = None,
    ) -> List[BaseEngineerEvent]:
        """Process one user message and return all events emitted.

        If ``credential`` is provided (shape ``{"field": "...", "value": "..."}``),
        it is submitted via :meth:`CredentialHandler.submit_credential` and is
        **never** logged or echoed.
        """
        sess = self.session_store.get(session_id)
        if sess is None:
            raise KeyError(f"Session {session_id!r} not found")

        state = sess.state

        # -- credential submission (never log, never echo) ---------------
        if credential is not None and isinstance(credential, dict):
            field = credential.get("field")
            value = credential.get("value")
            if field is not None and value is not None:
                self.credentials.submit_credential(state, field, value)
                logger.info(
                    "credential_submitted",
                    session_id=session_id,
                    field=field,
                    # value is intentionally omitted
                )

        # Heuristic state advance: detect plain-English intents without LLM
        url = _extract_url(user_message)
        if url is not None and state.current_stage == Stage.GREETING:
            state.url = url
            state.current_stage = Stage.RECON

        agent = self.agents[state.current_stage]
        thinking_event = agent._thinking_event(
            state, context={"action": "handle", "user_message": user_message}
        )
        events: List[BaseEngineerEvent] = []
        took_fallback = False
        try:
            turn_events = await self.conversation.generate_turn(
                state, user_message, history=None
            )
            events = [thinking_event] + list(turn_events)
        except Exception as exc:
            logger.debug(
                "conversation_turn_failed",
                session_id=session_id,
                error=str(exc),
            )
            took_fallback = True
            agent_events = await agent.run(
                state,
                context={"action": "handle", "user_message": user_message},
            )
            events = list(agent_events)

        # If we just advanced to RECON (heuristic), also run the RECON agent
        if state.current_stage == Stage.RECON and url is not None:
            new_events = await self.agents[Stage.RECON].run(
                state, context={"action": "handle", "user_message": user_message, "heuristic": True}
            )
            events.extend(new_events)

        if took_fallback and url is not None and state.current_stage in (Stage.RECON, Stage.CONTEXT):
            for ev in events:
                if isinstance(ev, ClassifySiteEvent):
                    try:
                        state.site_type = SiteType(ev.site_type)
                    except (ValueError, KeyError):
                        state.site_type = SiteType.LANDING
            if state.site_type is None:
                state.site_type = SiteType.LANDING
            cascade_events = await self._cascade_through_stages(
                state, start_stage=state.current_stage
            )
            events.extend(cascade_events)

        extra_events: List[BaseEngineerEvent] = []
        transitioned_to_execute = False

        for event in events:
            # ClassifySiteEvent + no prior classification -> run classifier
            if (
                isinstance(event, ClassifySiteEvent)
                and state.site_type is None
                and state.url is not None
            ):
                try:
                    result = await self.classifier.classify(state.url)
                    state.site_type = result.site_type
                    follow_up = ClassifySiteEvent(
                        session_id=state.session_id,
                        stage=state.current_stage,
                        timestamp=datetime.now(timezone.utc).isoformat(),
                        site_type=result.site_type.value,
                        confidence=result.confidence,
                        signals=result.signals,
                    )
                    extra_events.append(follow_up)
                except Exception as exc:
                    logger.debug(
                        "classification_failed",
                        session_id=session_id,
                        url=state.url,
                        error=str(exc),
                    )
                    state.site_type = SiteType.LANDING

            # PlanProposedEvent -> store the plan in state
            if isinstance(event, PlanProposedEvent):
                state.confirmed_plan = list(event.tests)

        if credential is not None and state.current_stage == Stage.CONTEXT:
            state.current_stage = Stage.PLAN

        # -- stage transition: PLAN -> EXECUTE (MVP shortcut) -------------
        # Heuristic stage advance based on plain-English user intent
        msg_lower = user_message.strip().lower()
        advance_to_execute = any(
            msg_lower.startswith(p) for p in ("test everything", "run all", "yes, run", "yes run", "yes")
        )
        if (
            advance_to_execute
            and state.current_stage == Stage.PLAN
            and state.confirmed_plan is not None
        ):
            state.current_stage = Stage.EXECUTE
            transitioned_to_execute = True

        if state.current_stage == Stage.PLAN and state.confirmed_plan is not None:
            # For MVP, treat any message in PLAN stage as confirmation.
            # T14 will implement a proper confirmation flow.
            state.current_stage = Stage.EXECUTE
            transitioned_to_execute = True

        # -- update session (NEVER pass credentials) ----------------------
        update_kwargs: Dict[str, Any] = {
            "current_stage": state.current_stage,
            "site_type": (
                state.site_type.value
                if state.site_type is not None
                else None
            ),
            "confirmed_plan": state.confirmed_plan,
            "url": state.url,
            "gathered_context": state.gathered_context,
        }
        self.session_store.update(session_id, **update_kwargs)

        # -- metrics ------------------------------------------------------
        self.metrics.record_first_response(session_id)

        # -- execution ----------------------------------------------------
        all_events = list(events) + extra_events
        if transitioned_to_execute or state.current_stage == Stage.EXECUTE:
            exec_events = await self._run_execution(state)
            all_events.extend(exec_events)

        return all_events

    async def _cascade_through_stages(
        self, state: SessionState, start_stage: Stage
    ) -> List[BaseEngineerEvent]:
        """When LLM is down, batch through every remaining stage so the user
        sees a complete flow without typing 'yes' for each transition.

        Called only from the LLM-down fallback path. The LLM-up path
        continues to drive the flow turn-by-turn.
        """
        events: List[BaseEngineerEvent] = []
        stage_order = [Stage.RECON, Stage.CONTEXT, Stage.PLAN, Stage.EXECUTE, Stage.REPORT, Stage.DONE]
        for stage in stage_order:
            if STAGE_RANK[stage] < STAGE_RANK[start_stage]:
                continue
            state.current_stage = stage
            if stage == Stage.DONE:
                events.append(DoneEvent(
                    session_id=state.session_id, stage=stage,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                ))
                continue
            try:
                agent_events = await self.agents[stage].run(
                    state, context={"action": "cascade", "tests_remaining": len(state.confirmed_plan or ["homepage"])}
                )
                if stage == Stage.REPORT:
                    agent_events = self._ensure_new_report_fallback(
                        agent_events, state, {"action": "cascade"}
                    )
                events.extend(agent_events)
            except Exception as exc:
                logger.debug("cascade_stage_failed", stage=stage.value, error=str(exc))
        return events

    def _ensure_new_report_fallback(
        self,
        events: List[BaseEngineerEvent],
        state: SessionState,
        context: Dict[str, Any],
    ) -> List[BaseEngineerEvent]:
        """Replace stale 'encountered an error' ReportEvents with the new
        ReportAgent plain-English offline fallback.
        """
        result: List[BaseEngineerEvent] = []
        for ev in events:
            if (
                isinstance(ev, ReportEvent)
                and "encountered an error" in ev.sections.get("Summary", "")
            ):
                result.extend(
                    self.agents[Stage.REPORT]._fallback(state, context)
                )
            else:
                result.append(ev)
        return result

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    async def _prepare_agent(self, agent_id: str, state: Any) -> None:
        """Inject credentials into ``agent_id`` if the site type requires them.

        ``state`` may be either a :class:`SessionState` or an
        :class:`EngineerSession` (the latter is used by some QA scenarios).
        """
        # Normalise state -> SessionState
        if hasattr(state, "state"):
            state = state.state

        if not isinstance(state, SessionState):
            return

        if state.site_type in CREDENTIAL_REQUIRED:
            self.credentials.inject_to_agent(agent_id, state)

    async def _run_execution(self, state: SessionState) -> List[BaseEngineerEvent]:
        """Run the confirmed test plan and emit progress + completion events.

        MVP: emits synthetic ``TestStartedEvent`` + ``TestCompletedEvent``
        pairs synchronously. T14 replaces this with real orchestrator calls.
        """
        events = await self.agents[Stage.EXECUTE].run(
            state, context={"role_map": _TEST_ROLE_MAP}
        )

        plan = state.confirmed_plan or []
        for event in events:
            if isinstance(event, TestStartedEvent):
                agent_id = f"{state.session_id}-{event.test_id}"
                await self._prepare_agent(agent_id, state)
                self.metrics.record_narration(
                    state.session_id, agent_id, delta_ms=0
                )

        if plan:
            # Use ReportAgent so the fallback uses the new plain-English offline text
            report_events = await self.agents[Stage.REPORT].run(
                state, context={"action": "report"}
            )
            report_events = self._ensure_new_report_fallback(
                report_events, state, {"action": "report"}
            )
            report_event = None
            for ev in report_events:
                if isinstance(ev, ReportEvent):
                    report_event = ev
                    break
            if report_event is not None:
                events.append(report_event)
            else:
                # Fallback if ReportAgent returns no ReportEvent (shouldn't happen)
                report_event = await self.report.build_report(
                    state.session_id, agent_findings=[], stage="report"
                )
                events.append(report_event)
            state.current_stage = Stage.REPORT
            self.session_store.update(
                state.session_id,
                current_stage=state.current_stage,
            )

            done_event = DoneEvent(
                session_id=state.session_id,
                stage=Stage.DONE,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
            events.append(done_event)
            state.current_stage = Stage.DONE
            self.session_store.update(
                state.session_id,
                current_stage=state.current_stage,
            )

        return events

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------

    def get_metrics(self, session_id: str) -> Dict[str, Any]:
        """Return the API-ready metrics summary for ``session_id``."""
        return self.metrics.metrics_summary(session_id)


__all__ = ["LiveEngineer"]
