"""Resilience tests for per-stage agents.

Covers graceful LLM-failure fallback, proactive narration, and
stage-specific event emission.
"""

from __future__ import annotations

import asyncio
import io
import logging
from unittest.mock import AsyncMock

import pytest

from command_center.engineer.agents import (
    ContextAgent,
    ExecuteAgent,
    GreetingAgent,
    PlanAgent,
    ReconAgent,
    ReportAgent,
    STAGE_AGENTS,
    THINKING_MESSAGES,
)
from command_center.engineer.events import (
    AskCredentialEvent,
    AskQuestionEvent,
    GreetingEvent,
    NarrateEvent,
    PlanProposedEvent,
    ReportEvent,
)
from command_center.engineer.site_catalog import SiteType
from command_center.engineer.state_machine import SessionState, Stage


def make_test_state(stage: Stage = Stage.GREETING) -> SessionState:
    return SessionState(
        session_id="test-sess-001",
        current_stage=stage,
        url="https://example.com",
    )


@pytest.mark.asyncio
async def test_greeting_agent_with_llm() -> None:
    """LLM works: calls conversation.generate_greeting."""
    conversation = AsyncMock()
    conversation.generate_greeting = AsyncMock(
        return_value=GreetingEvent(
            session_id="s1",
            stage=Stage.GREETING,
            timestamp="2024-01-01T00:00:00Z",
            message="Hello!",
        )
    )
    agent = GreetingAgent(conversation=conversation)
    state = make_test_state(Stage.GREETING)
    events = await agent.run(state, context={})

    assert any(isinstance(e, NarrateEvent) for e in events)
    assert any(isinstance(e, GreetingEvent) for e in events)
    conversation.generate_greeting.assert_awaited_once_with(state)


@pytest.mark.asyncio
async def test_greeting_agent_without_llm() -> None:
    """LLM raises: falls back to canned greeting."""
    conversation = AsyncMock()
    conversation.generate_greeting = AsyncMock(
        side_effect=RuntimeError("Provider 'openai' not initialized.")
    )
    agent = GreetingAgent(conversation=conversation)
    state = make_test_state(Stage.GREETING)
    events = await agent.run(state, context={})

    assert any(isinstance(e, NarrateEvent) for e in events)
    greeting = [e for e in events if isinstance(e, GreetingEvent)][0]
    assert "Vectra" in greeting.message


@pytest.mark.asyncio
async def test_recon_agent_classifies() -> None:
    """Happy path: classifier returns site type."""
    classifier = AsyncMock()
    classifier.classify = AsyncMock(
        return_value=AsyncMock(
            site_type=SiteType.ECOMMERCE,
            confidence=0.9,
            signals=["heuristic:ecommerce"],
        )
    )
    agent = ReconAgent(classifier=classifier)
    state = make_test_state(Stage.RECON)
    events = await agent.run(state, context={})

    assert any(isinstance(e, NarrateEvent) for e in events)
    classifier.classify.assert_awaited_once_with("https://example.com")


@pytest.mark.asyncio
async def test_recon_agent_heuristic_fallback() -> None:
    """LLM classifier raises: fallback uses LANDING."""
    classifier = AsyncMock()
    classifier.classify = AsyncMock(side_effect=RuntimeError("offline"))
    agent = ReconAgent(classifier=classifier)
    state = make_test_state(Stage.RECON)
    events = await agent.run(state, context={})

    assert any(isinstance(e, NarrateEvent) for e in events)


@pytest.mark.asyncio
async def test_context_agent_asks_credential_for_ecom() -> None:
    """Ecommerce site → AskCredentialEvent."""
    agent = ContextAgent()
    state = make_test_state(Stage.CONTEXT)
    state.site_type = SiteType.ECOMMERCE
    events = await agent.run(state, context={})

    cred_events = [e for e in events if isinstance(e, AskCredentialEvent)]
    assert len(cred_events) == 1
    assert cred_events[0].field == "password"


@pytest.mark.asyncio
async def test_context_agent_asks_question_for_landing() -> None:
    """Landing site → AskQuestionEvent."""
    agent = ContextAgent()
    state = make_test_state(Stage.CONTEXT)
    state.site_type = SiteType.LANDING
    events = await agent.run(state, context={})

    q_events = [e for e in events if isinstance(e, AskQuestionEvent)]
    assert len(q_events) == 1


@pytest.mark.asyncio
async def test_plan_agent_proposes_default() -> None:
    """Uses get_default_plan for known site type."""
    agent = PlanAgent()
    state = make_test_state(Stage.PLAN)
    state.site_type = SiteType.ECOMMERCE
    events = await agent.run(state, context={})

    plan_events = [e for e in events if isinstance(e, PlanProposedEvent)]
    assert len(plan_events) == 1
    assert "homepage" in plan_events[0].tests


@pytest.mark.asyncio
async def test_plan_agent_fallback_uses_catalog() -> None:
    """Fallback still produces plan from catalog."""
    agent = PlanAgent()
    state = make_test_state(Stage.PLAN)
    state.site_type = SiteType.BLOG
    events = agent._fallback(state, context={})

    plan_events = [e for e in events if isinstance(e, PlanProposedEvent)]
    assert len(plan_events) == 1
    assert "homepage" in plan_events[0].tests


@pytest.mark.asyncio
async def test_execute_agent_emits_narration() -> None:
    """Every test gets narrated."""
    narrator = AsyncMock()
    narrator.narrate_test_started = AsyncMock(
        return_value=NarrateEvent(
            session_id="s1",
            stage=Stage.EXECUTE,
            timestamp="2024-01-01T00:00:00Z",
            agent_id="a1",
            status="started",
            message="Started homepage.",
        )
    )
    agent = ExecuteAgent(narrator=narrator)
    state = make_test_state(Stage.EXECUTE)
    state.confirmed_plan = ["homepage"]
    events = await agent.run(state, context={})

    narrate_events = [e for e in events if isinstance(e, NarrateEvent)]
    assert len(narrate_events) >= 1


@pytest.mark.asyncio
async def test_report_agent_fallback_offline_message() -> None:
    """Fallback ReportEvent has plain-English offline message."""
    agent = ReportAgent()
    state = make_test_state(Stage.REPORT)
    events = agent._fallback(state, context={})

    report = events[0]
    assert isinstance(report, ReportEvent)
    assert "offline" in report.sections["Summary"].lower()
    assert "OPENAI_API_KEY" in report.sections["Recommendations"][0]


def test_all_stage_agents_emit_thinking_event() -> None:
    """Every agent's run() returns a list with at least one NarrateEvent
    with status='thinking'."""

    async def _check() -> None:
        for stage, cls in STAGE_AGENTS.items():
            state = make_test_state(stage)
            agent = cls()
            events = await agent.run(state, context={})
            thinking = [
                e for e in events
                if isinstance(e, NarrateEvent) and e.status == "thinking"
            ]
            assert len(thinking) >= 1, f"{cls.__name__} missing thinking event"

    asyncio.run(_check())


def test_no_warning_on_llm_failure() -> None:
    """LLM failure must not emit WARNING-level log records."""
    log_stream = io.StringIO()
    handler = logging.StreamHandler(log_stream)
    handler.setLevel(logging.WARNING)
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)

    class FailingConversation:
        async def generate_greeting(self, state):
            raise RuntimeError("Provider 'openai' not initialized.")

    agent = GreetingAgent(conversation=FailingConversation())
    state = make_test_state()
    events = asyncio.run(agent.run(state, context={}))

    handler.flush()
    log_output = log_stream.getvalue()
    assert "WARNING" not in log_output.upper()
    assert "WARN" not in log_output.upper()
    assert any(isinstance(e, GreetingEvent) for e in events)

    root_logger.removeHandler(handler)


def test_stage_agents_dict_covers_all_stages() -> None:
    """STAGE_AGENTS has all 6 non-terminal stages."""
    expected = {
        Stage.GREETING,
        Stage.RECON,
        Stage.CONTEXT,
        Stage.PLAN,
        Stage.EXECUTE,
        Stage.REPORT,
    }
    assert set(STAGE_AGENTS.keys()) == expected


def test_thinking_messages_cover_all_stages() -> None:
    """THINKING_MESSAGES has a message for every non-terminal stage."""
    for stage in STAGE_AGENTS:
        assert stage in THINKING_MESSAGES
        assert THINKING_MESSAGES[stage]
        assert len(THINKING_MESSAGES[stage].split()) <= 15
