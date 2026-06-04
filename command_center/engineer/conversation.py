"""Conversation engine for the Live QA Engineer.

Handles stage-guarded, structured event emission via JSON-mode LLM calls
with vocabulary scrubbing and word-budget enforcement.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import structlog

from mcp_server.llm_router import llm_router

from .events import (
    AskCredentialEvent,
    AskQuestionEvent,
    ClassifySiteEvent,
    ConfirmClassificationEvent,
    DoneEvent,
    EngineerEvent,
    ErrorEvent,
    GreetingEvent,
    NarrateEvent,
    PlanProposedEvent,
    ReportEvent,
    TestCompletedEvent,
    TestProgressEvent,
    TestStartedEvent,
)
from .site_catalog import CREDENTIAL_REQUIRED, get_default_plan
from .state_machine import (
    SessionState,
    Stage,
    assert_monotonic,
)
from .vocabulary import VOCABULARY_GLOSSARY, enforce_word_budget, scrub_forbidden

logger = structlog.get_logger("engineer.conversation")

# Stage-specific word budgets for user-facing text.
_STAGE_WORD_BUDGET: Dict[Stage, int] = {
    Stage.GREETING: 25,
    Stage.RECON: 50,
    Stage.CONTEXT: 50,
    Stage.PLAN: 50,
    Stage.EXECUTE: 50,
    Stage.REPORT: 150,
    Stage.DONE: 25,
}

# Mapping of stage -> event types that are allowed at that stage.
_STAGE_ALLOWED_EVENTS: Dict[Stage, List[str]] = {
    Stage.GREETING: ["greeting"],
    Stage.RECON: ["ask_question", "classify_site"],
    Stage.CONTEXT: ["ask_question", "ask_credential", "confirm_classification"],
    Stage.PLAN: ["plan_proposed", "ask_question"],
    Stage.EXECUTE: ["test_started", "test_progress", "test_completed", "narrate"],
    Stage.REPORT: ["report", "narrate"],
    Stage.DONE: ["done"],
}

# Text-field names that may contain user-facing copy and need scrubbing.
_TEXT_FIELDS: Tuple[str, ...] = ("message", "prompt", "reason", "findings_summary")


class ConversationEngine:
    """Stage-guarded conversation engine.

    Emits structured :class:`EngineerEvent` instances via JSON-mode LLM
    calls.  Every event message is run through the vocabulary scrubber
    and word-budget enforcer before being surfaced.
    """

    def __init__(self, llm=None):
        if llm is None:
            llm = llm_router
        self.llm = llm

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    async def _call_llm_async(
        self,
        model: str,
        messages: List[Dict[str, str]],
        **kwargs,
    ) -> Any:
        """Invoke the LLM and normalise sync / async return values."""
        raw = self.llm.complete(model=model, messages=messages, **kwargs)
        if asyncio.iscoroutine(raw):
            raw = await raw
        return raw

    def _build_system_prompt(self, state: SessionState) -> str:
        """Return a stage-specific system prompt for the LLM."""
        current = state.current_stage
        allowed = _STAGE_ALLOWED_EVENTS.get(current, [])
        budget = _STAGE_WORD_BUDGET.get(current, 50)

        prompt_parts = [
            "You are Vectra, a live QA engineer.",
            f"Current pipeline stage: {current.value}",
            f"Allowed event types at this stage: {', '.join(allowed)}",
            "",
            "Vocabulary hint — use plain English instead of jargon:",
        ]
        for word, plain in VOCABULARY_GLOSSARY.items():
            prompt_parts.append(f'  - Instead of "{word}", say: "{plain}"')
        prompt_parts.append("")
        prompt_parts.append(f"Word budget for user-facing text: {budget} words.")

        if current == Stage.CONTEXT:
            prompt_parts.append(
                f"Rule: NEVER ask for credentials unless site_type in "
                f"{sorted(str(s) for s in CREDENTIAL_REQUIRED)}."
            )
        elif current == Stage.PLAN:
            prompt_parts.append(
                "Rule: ALWAYS call get_default_plan; never invent test names."
            )

        prompt_parts.append("")
        prompt_parts.append(
            "Respond with a JSON object exactly in this shape: "
            '{"events": [{"type": "<event_type>", ...other fields...}]}'
        )
        prompt_parts.append(
            "Each event must include a 'type' field from the allowed list. "
            "Do not invent new event types."
        )

        return "\n".join(prompt_parts)

    def _enrich_event_dict(
        self, event_dict: Dict[str, Any], state: SessionState
    ) -> Dict[str, Any]:
        """Inject envelope fields into an event dict from the LLM."""
        enriched = dict(event_dict)
        enriched.setdefault("session_id", state.session_id)
        enriched.setdefault("stage", state.current_stage.value)
        enriched.setdefault("timestamp", self._now())
        return enriched

    def _scrub_event(self, event: Any, stage: Stage) -> Any:
        """Run all text fields on an event through scrub + word budget."""
        budget = _STAGE_WORD_BUDGET.get(stage, 50)
        for field_name in _TEXT_FIELDS:
            if hasattr(event, field_name):
                raw_text = getattr(event, field_name) or ""
                cleaned, _ = scrub_forbidden(raw_text)
                budgeted = enforce_word_budget(cleaned, budget)
                object.__setattr__(event, field_name, budgeted)
        return event

    # ------------------------------------------------------------------
    # Main turn generator
    # ------------------------------------------------------------------

    async def generate_turn(
        self,
        state: SessionState,
        user_message: str,
        history: Optional[List[Any]] = None,
    ) -> List[Any]:
        """Generate the next turn of events for the conversation.

        1. Detects the current stage.
        2. Handles the ``'test everything'`` / ``'run all'`` shortcut.
        3. Builds a stage-specific system prompt.
        4. Calls the LLM in JSON mode.
        5. Validates, scrubs, and enforces word budgets.
        6. Asserts monotonic stage transitions.
        """
        current = state.current_stage

        # ---- Shortcut: auto-derive plan ---------------------------------
        if (
            ("test everything" in user_message.lower() or "run all" in user_message.lower())
            and state.site_type is not None
        ):
            tests = get_default_plan(state.site_type)
            event = PlanProposedEvent(
                session_id=state.session_id,
                stage=current,
                timestamp=self._now(),
                tests=tests,
                site_type=(
                    state.site_type.value
                    if hasattr(state.site_type, "value")
                    else str(state.site_type)
                ),
            )
            return [event]

        # ---- Build prompt and call LLM ----------------------------------
        system_prompt = self._build_system_prompt(state)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        raw = await self._call_llm_async(
            model="openai/gpt-4o",
            messages=messages,
            temperature=0.3,
            max_tokens=1024,
            response_format={"type": "json_object"},
        )

        content = getattr(raw, "content", str(raw))
        parsed = json.loads(content)

        if not isinstance(parsed, dict) or "events" not in parsed:
            raise ValueError(
                f"LLM did not return {{'events': [...]}} shape. Got: {content}"
            )

        events: List[Any] = []
        for event_dict in parsed["events"]:
            enriched = self._enrich_event_dict(event_dict, state)
            validated = EngineerEvent.model_validate(enriched)

            # Check stage transition before scrubbing
            event_stage = getattr(validated, "stage", None)
            if event_stage is not None and event_stage != current:
                assert_monotonic(state, event_stage)

            # Scrub text fields
            self._scrub_event(validated, current)
            events.append(validated)

        return events

    # ------------------------------------------------------------------
    # Direct event generators
    # ------------------------------------------------------------------

    async def generate_greeting(self, state: SessionState) -> GreetingEvent:
        """Return a greeting event."""
        prompt = (
            "Greet the user as Vectra, a live QA engineer. ≤25 words. Ask for a URL. "
            'Respond with JSON: {"message": "..."}'
        )
        messages = [
            {"role": "system", "content": prompt},
        ]
        raw = await self._call_llm_async(
            model="openai/gpt-4o",
            messages=messages,
            temperature=0.3,
            max_tokens=100,
            response_format={"type": "json_object"},
        )
        content = getattr(raw, "content", str(raw))
        parsed = json.loads(content)
        message = parsed.get("message", "")

        # Validate and enforce word budget
        word_count = len(message.split())
        if word_count > 25:
            message = enforce_word_budget(message, 25)

        cleaned, _ = scrub_forbidden(message)

        return GreetingEvent(
            session_id=state.session_id,
            stage=Stage.GREETING,
            timestamp=self._now(),
            message=cleaned,
        )

    async def generate_ask_question(
        self,
        state: SessionState,
        question_id: str,
        prompt: str,
        choices: Optional[List[str]] = None,
    ) -> AskQuestionEvent:
        """Return an ask-question event."""
        return AskQuestionEvent(
            session_id=state.session_id,
            stage=state.current_stage,
            timestamp=self._now(),
            question_id=question_id,
            prompt=prompt,
            choices=choices,
        )

    async def generate_ask_credential(
        self,
        state: SessionState,
        field: str,
        reason: str,
    ) -> AskCredentialEvent:
        """Return an ask-credential event."""
        return AskCredentialEvent(
            session_id=state.session_id,
            stage=state.current_stage,
            timestamp=self._now(),
            field=field,  # type: ignore[arg-type]
            reason=reason,
        )

    async def generate_classify_site(
        self,
        state: SessionState,
        site_type: str,
        confidence: float,
        signals: List[str],
    ) -> ClassifySiteEvent:
        """Return a classify-site event."""
        return ClassifySiteEvent(
            session_id=state.session_id,
            stage=state.current_stage,
            timestamp=self._now(),
            site_type=site_type,
            confidence=confidence,
            signals=signals,
        )

    async def generate_confirm_classification(
        self,
        state: SessionState,
    ) -> ConfirmClassificationEvent:
        """Return a confirm-classification event."""
        return ConfirmClassificationEvent(
            session_id=state.session_id,
            stage=state.current_stage,
            timestamp=self._now(),
        )

    async def generate_plan_proposed(
        self,
        state: SessionState,
        tests: List[str],
        site_type: str,
    ) -> PlanProposedEvent:
        """Return a plan-proposed event."""
        return PlanProposedEvent(
            session_id=state.session_id,
            stage=state.current_stage,
            timestamp=self._now(),
            tests=tests,
            site_type=site_type,
        )

    async def generate_narrate(
        self,
        state: SessionState,
        agent_id: str,
        status: str,
        message: str,
    ) -> NarrateEvent:
        """Return a narrate event."""
        return NarrateEvent(
            session_id=state.session_id,
            stage=state.current_stage,
            timestamp=self._now(),
            agent_id=agent_id,
            status=status,
            message=message,
        )

    async def generate_test_started(
        self,
        state: SessionState,
        test_id: str,
        role: str,
    ) -> TestStartedEvent:
        """Return a test-started event."""
        return TestStartedEvent(
            session_id=state.session_id,
            stage=state.current_stage,
            timestamp=self._now(),
            test_id=test_id,
            role=role,
        )

    async def generate_test_progress(
        self,
        state: SessionState,
        test_id: str,
        progress_percent: int,
        message: str,
    ) -> TestProgressEvent:
        """Return a test-progress event."""
        return TestProgressEvent(
            session_id=state.session_id,
            stage=state.current_stage,
            timestamp=self._now(),
            test_id=test_id,
            progress_percent=progress_percent,
            message=message,
        )

    async def generate_test_completed(
        self,
        state: SessionState,
        test_id: str,
        result: str,
        findings_summary: str,
    ) -> TestCompletedEvent:
        """Return a test-completed event."""
        return TestCompletedEvent(
            session_id=state.session_id,
            stage=state.current_stage,
            timestamp=self._now(),
            test_id=test_id,
            result=result,
            findings_summary=findings_summary,
        )

    async def generate_report(
        self,
        state: SessionState,
        sections: Dict[str, Any],
    ) -> ReportEvent:
        """Return a report event."""
        return ReportEvent(
            session_id=state.session_id,
            stage=state.current_stage,
            timestamp=self._now(),
            sections=sections,
        )

    async def generate_done(self, state: SessionState) -> DoneEvent:
        """Return a done event."""
        return DoneEvent(
            session_id=state.session_id,
            stage=state.current_stage,
            timestamp=self._now(),
        )

    async def generate_error(
        self,
        state: SessionState,
        code: str,
        message: str,
    ) -> ErrorEvent:
        """Return an error event."""
        return ErrorEvent(
            session_id=state.session_id,
            stage=state.current_stage,
            timestamp=self._now(),
            code=code,
            message=message,
        )
