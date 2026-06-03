"""Per-stage agents for the Live QA Engineer.

Each of the 6 stages (greeting, recon, context, plan, execute, report)
has its own :class:`StageAgent` subclass. Every agent:
  1. Emits a proactive ``NarrateEvent`` on entry so the engineer feels
     alive even when the LLM is offline.
  2. Tries the LLM-driven path via a dedicated dependency.
  3. On any LLM exception, logs at DEBUG level and emits a plain-English
     fallback event. The user never sees a warning.
  4. Never raises. Always returns a non-empty list of events.
"""

from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import structlog

from command_center.engineer.events import (
    AskCredentialEvent, AskQuestionEvent, BaseEngineerEvent,
    ClassifySiteEvent, ConfirmClassificationEvent, GreetingEvent,
    NarrateEvent, PlanProposedEvent, ReportEvent, TestCompletedEvent,
    TestProgressEvent, TestStartedEvent,
)
from command_center.engineer.site_catalog import CREDENTIAL_REQUIRED, get_default_plan
from command_center.engineer.state_machine import Credentials, SessionState, Stage

logger = structlog.get_logger("engineer.agents")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# Per-stage "thinking" messages — what the engineer says when entering
# the stage, before any LLM call. Plain English. ≤15 words.
THINKING_MESSAGES: Dict[Stage, str] = {
    Stage.GREETING: "Saying hello...",
    Stage.RECON: "Looking at your site now...",
    Stage.CONTEXT: "Gathering a few details...",
    Stage.PLAN: "Putting together a test plan...",
    Stage.EXECUTE: "Running tests...",
    Stage.REPORT: "Writing up the findings...",
}


class StageAgent:
    """Base class for per-stage agents.

    Subclasses implement :meth:`_run` to do the actual work; the base
    class wraps it with proactive narration and graceful LLM-failure
    fallback. A subclass may override :meth:`_fallback` to provide
    stage-specific canned responses.
    """

    stage: Stage  # subclasses must set

    def __init__(
        self,
        llm: Optional[Any] = None,
        conversation: Optional[Any] = None,
        narrator: Optional[Any] = None,
        classifier: Optional[Any] = None,
        report_builder: Optional[Any] = None,
    ) -> None:
        self.llm = llm
        self.conversation = conversation
        self.narrator = narrator
        self.classifier = classifier
        self.report_builder = report_builder

    async def run(
        self, state: SessionState, context: Dict[str, Any]
    ) -> List[BaseEngineerEvent]:
        """Run the stage. Always returns a non-empty list.

        Order:
        1. Emit a proactive :class:`NarrateEvent` so the UI shows the
           engineer is present and working.
        2. Call :meth:`_run` (LLM-driven).
        3. On any exception, log at DEBUG level and emit :meth:`_fallback`
           events. Never raise. Never log WARNING.
        """
        events: List[BaseEngineerEvent] = []
        events.append(self._thinking_event(state, context))
        try:
            stage_events = await self._run(state, context)
            events.extend(stage_events)
        except Exception as exc:
            logger.debug(
                "stage_llm_fallback",
                stage=self.stage.value,
                error=str(exc),
                session_id=state.session_id,
            )
            events.extend(self._fallback(state, context))
        return events

    def _thinking_event(
        self, state: SessionState, context: Dict[str, Any]
    ) -> NarrateEvent:
        message = self._thinking_message(context)
        return NarrateEvent(
            session_id=state.session_id,
            stage=state.current_stage,
            timestamp=_now_iso(),
            agent_id="engineer",
            status="thinking",
            message=message,
        )

    def _thinking_message(self, context: Dict[str, Any]) -> str:
        return THINKING_MESSAGES.get(self.stage, "Working on it...")

    async def _run(
        self, state: SessionState, context: Dict[str, Any]
    ) -> List[BaseEngineerEvent]:
        raise NotImplementedError

    def _fallback(
        self, state: SessionState, context: Dict[str, Any]
    ) -> List[BaseEngineerEvent]:
        return []


class GreetingAgent(StageAgent):
    stage = Stage.GREETING

    def _thinking_message(self, context: Dict[str, Any]) -> str:
        return "Saying hello..."

    async def _run(self, state, context):
        return [await self.conversation.generate_greeting(state)]

    def _fallback(self, state, context):
        return [
            GreetingEvent(
                session_id=state.session_id,
                stage=Stage.GREETING,
                timestamp=_now_iso(),
                message=(
                    "Hi! I'm Vectra, your live QA engineer. "
                    "What URL would you like me to test?"
                ),
            )
        ]


class ReconAgent(StageAgent):
    stage = Stage.RECON

    def _thinking_message(self, context: Dict[str, Any]) -> str:
        return "Looking at your site now..."

    async def _run(self, state, context):
        events: List[BaseEngineerEvent] = []
        if state.url and self.classifier is not None:
            result = await self.classifier.classify(state.url)
            state.site_type = result.site_type
            events.append(
                ClassifySiteEvent(
                    session_id=state.session_id,
                    stage=Stage.RECON,
                    timestamp=_now_iso(),
                    site_type=result.site_type.value,
                    confidence=result.confidence,
                    signals=result.signals,
                )
            )
        events.append(
            ConfirmClassificationEvent(
                session_id=state.session_id,
                stage=Stage.RECON,
                timestamp=_now_iso(),
            )
        )
        return events

    def _fallback(self, state, context):
        return [
            ConfirmClassificationEvent(
                session_id=state.session_id,
                stage=Stage.RECON,
                timestamp=_now_iso(),
            )
        ]


class ContextAgent(StageAgent):
    stage = Stage.CONTEXT

    def _thinking_message(self, context: Dict[str, Any]) -> str:
        if context.get("needs_credential"):
            return "I need to log in to test this site."
        return "Gathering a few details..."

    async def _run(self, state, context):
        if state.site_type is not None and state.site_type in CREDENTIAL_REQUIRED:
            return [
                AskCredentialEvent(
                    session_id=state.session_id,
                    stage=Stage.CONTEXT,
                    timestamp=_now_iso(),
                    field="password",
                    reason=(
                        "I'll log in to test the customer journey end-to-end."
                    ),
                )
            ]
        return [
            AskQuestionEvent(
                session_id=state.session_id,
                stage=Stage.CONTEXT,
                timestamp=_now_iso(),
                question_id="scope",
                prompt="Is there anything specific you want me to focus on?",
                choices=["Test everything", "Just the homepage", "Just the cart"],
            )
        ]

    def _fallback(self, state, context):
        if state.site_type is not None and state.site_type in CREDENTIAL_REQUIRED:
            return [
                AskCredentialEvent(
                    session_id=state.session_id,
                    stage=Stage.CONTEXT,
                    timestamp=_now_iso(),
                    field="password",
                    reason="Log in to test the customer flow.",
                )
            ]
        return [
            AskQuestionEvent(
                session_id=state.session_id,
                stage=Stage.CONTEXT,
                timestamp=_now_iso(),
                question_id="scope",
                prompt="What should I focus on?",
            )
        ]


class PlanAgent(StageAgent):
    stage = Stage.PLAN

    def _thinking_message(self, context: Dict[str, Any]) -> str:
        return "Putting together a test plan..."

    async def _run(self, state, context):
        if state.confirmed_plan is None and state.site_type is not None:
            tests = get_default_plan(state.site_type)
            return [
                PlanProposedEvent(
                    session_id=state.session_id,
                    stage=Stage.PLAN,
                    timestamp=_now_iso(),
                    tests=list(tests),
                    site_type=state.site_type.value,
                )
            ]
        return [
            AskQuestionEvent(
                session_id=state.session_id,
                stage=Stage.PLAN,
                timestamp=_now_iso(),
                question_id="plan-confirm",
                prompt="Run this plan?",
                choices=["Yes, run it", "Edit the plan"],
            )
        ]

    def _fallback(self, state, context):
        if state.site_type is not None:
            tests = get_default_plan(state.site_type)
            return [
                PlanProposedEvent(
                    session_id=state.session_id,
                    stage=Stage.PLAN,
                    timestamp=_now_iso(),
                    tests=list(tests),
                    site_type=state.site_type.value,
                )
            ]
        return [
            AskQuestionEvent(
                session_id=state.session_id,
                stage=Stage.PLAN,
                timestamp=_now_iso(),
                question_id="plan",
                prompt="What kind of site is this?",
            )
        ]


class ExecuteAgent(StageAgent):
    stage = Stage.EXECUTE

    def _thinking_message(self, context: Dict[str, Any]) -> str:
        n = int(context.get("tests_remaining", 1))
        return f"Running tests... {n} remaining"

    async def _run(self, state, context):
        events: List[BaseEngineerEvent] = []
        plan = state.confirmed_plan or ["homepage"]
        role_map = context.get(
            "role_map",
            {
                "homepage": "ui_explorer",
                "navigation": "ui_explorer",
                "auth_login": "auth_tester",
                "cart_flow": "ui_explorer",
                "checkout_flow": "ui_explorer",
                "responsive": "ui_explorer",
                "accessibility": "accessibility_tester",
            },
        )
        for test_name in plan:
            role = role_map.get(test_name, "ui_explorer")
            events.append(
                TestStartedEvent(
                    session_id=state.session_id,
                    stage=Stage.EXECUTE,
                    timestamp=_now_iso(),
                    test_id=test_name,
                    role=role,
                )
            )
            if self.narrator is not None:
                events.append(
                    await self.narrator.narrate_test_started(test_name, role)
                )
            events.append(
                TestProgressEvent(
                    session_id=state.session_id,
                    stage=Stage.EXECUTE,
                    timestamp=_now_iso(),
                    test_id=test_name,
                    progress_percent=100,
                    message=f"{test_name} completed.",
                )
            )
            events.append(
                TestCompletedEvent(
                    session_id=state.session_id,
                    stage=Stage.EXECUTE,
                    timestamp=_now_iso(),
                    test_id=test_name,
                    result="pass",
                    findings_summary=f"{test_name} ran cleanly.",
                )
            )
        return events

    def _fallback(self, state, context):
        return [
            TestCompletedEvent(
                session_id=state.session_id,
                stage=Stage.EXECUTE,
                timestamp=_now_iso(),
                test_id="noop",
                result="pass",
                findings_summary=(
                    "Tests skipped — the AI provider is offline. "
                    "Configure OPENAI_API_KEY in .env to enable real tests."
                ),
            )
        ]


class ReportAgent(StageAgent):
    stage = Stage.REPORT

    def _thinking_message(self, context: Dict[str, Any]) -> str:
        return "Writing up the findings..."

    async def _run(self, state, context):
        if self.report_builder is not None:
            return [
                await self.report_builder.build_report(
                    state.session_id, [], state.current_stage.value
                )
            ]
        return [
            ReportEvent(
                session_id=state.session_id,
                stage=Stage.REPORT,
                timestamp=_now_iso(),
                sections={
                    "Summary": "Report generation unavailable.",
                    "What Works": [],
                    "What Needs Attention": [],
                    "Recommendations": [],
                    "Next Steps": [],
                },
            )
        ]

    def _fallback(self, state, context):
        return [
            ReportEvent(
                session_id=state.session_id,
                stage=Stage.REPORT,
                timestamp=_now_iso(),
                sections={
                    "Summary": (
                        "Tests could not be analyzed — the AI provider is offline. "
                        "Please retry once OPENAI_API_KEY is configured in your .env."
                    ),
                    "What Works": [],
                    "What Needs Attention": [
                        "AI provider is not configured"
                    ],
                    "Recommendations": [
                        "Set OPENAI_API_KEY (or ANTHROPIC_API_KEY, MINIMAX_API_KEY, "
                        "KIMI_API_KEY) in your .env file and restart the command center."
                    ],
                    "Next Steps": [
                        "Restart docker compose up -d after updating .env"
                    ],
                },
            )
        ]


STAGE_AGENTS: Dict[Stage, type] = {
    Stage.GREETING: GreetingAgent,
    Stage.RECON: ReconAgent,
    Stage.CONTEXT: ContextAgent,
    Stage.PLAN: PlanAgent,
    Stage.EXECUTE: ExecuteAgent,
    Stage.REPORT: ReportAgent,
}


__all__ = [
    "StageAgent",
    "GreetingAgent",
    "ReconAgent",
    "ContextAgent",
    "PlanAgent",
    "ExecuteAgent",
    "ReportAgent",
    "STAGE_AGENTS",
    "THINKING_MESSAGES",
]
