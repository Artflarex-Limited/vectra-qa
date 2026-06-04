"""Live QA narrator — translates technical SSE events into plain English.

Subscribes to SSE streams and narrates agent progress using a tight LLM
prompt with vocabulary scrubbing and word-budget enforcement.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from typing import Dict, Optional

import structlog

from command_center.engineer.events import NarrateEvent
from command_center.engineer.metrics import MetricsRecorder
from command_center.engineer.vocabulary import enforce_word_budget, scrub_forbidden

logger = structlog.get_logger("engineer.narrator")

NARRATOR_MODEL = os.getenv("NARRATOR_MODEL", "openai/gpt-4o")

# Module-level cache keyed by SHA256 of serialized input.
_cache: Dict[str, NarrateEvent] = {}


def _make_cache_key(payload: dict) -> str:
    """Return a SHA256 hex digest of a sorted JSON serialization."""
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode()
    ).hexdigest()


class Narrator:
    """Translate technical QA events into plain-English narration."""

    def __init__(
        self,
        llm=None,
        metrics_recorder: Optional[MetricsRecorder] = None,
    ) -> None:
        if llm is None:
            try:
                from mcp_server.llm_router import LLMRouter

                llm = LLMRouter()
            except Exception:
                llm = None
        self.llm = llm
        self.metrics = metrics_recorder or MetricsRecorder()
        self._last_narration_time: Dict[str, float] = {}

    def _compute_delta_ms(self, session_id: str) -> int:
        now = time.monotonic()
        last = self._last_narration_time.get(session_id)
        if last is None:
            delta_ms = 0
        else:
            delta_ms = int((now - last) * 1000)
        self._last_narration_time[session_id] = now
        return delta_ms

    def _build_narrate_event(
        self,
        session_id: str,
        agent_id: str,
        status: str,
        message: str,
    ) -> NarrateEvent:
        return NarrateEvent(
            session_id=session_id,
            stage="execute",
            timestamp=datetime.now(timezone.utc).isoformat(),
            agent_id=agent_id,
            status=status,
            message=message,
        )

    async def _call_llm(self, prompt: str) -> str:
        if self.llm is None:
            return prompt

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a QA engineer narrating test progress to a non-technical user. "
                    "Translate technical events into plain English. "
                    "Use 15 words or fewer. No jargon."
                ),
            },
            {"role": "user", "content": prompt},
        ]

        raw = self.llm.complete(
            model=NARRATOR_MODEL,
            messages=messages,
            temperature=0.3,
            max_tokens=50,
        )
        if asyncio.iscoroutine(raw):
            raw = await raw

        return getattr(raw, "content", str(raw))

    async def _narrate(
        self,
        cache_key: str,
        session_id: str,
        agent_id: str,
        status: str,
        prompt: str,
    ) -> NarrateEvent:
        cached = _cache.get(cache_key)
        if cached is not None:
            logger.debug("narrator.cache_hit", cache_key=cache_key)
            return cached

        raw_message = await self._call_llm(prompt)
        cleaned, _ = scrub_forbidden(raw_message)
        message = enforce_word_budget(cleaned, 15)

        event = self._build_narrate_event(session_id, agent_id, status, message)
        _cache[cache_key] = event

        delta_ms = self._compute_delta_ms(session_id)
        self.metrics.record_narration(session_id, agent_id, delta_ms)

        return event

    async def narrate_event(self, sse_event: dict) -> NarrateEvent:
        cache_key = hashlib.sha256(
            json.dumps(sse_event, sort_keys=True, default=str).encode()
        ).hexdigest()
        session_id = sse_event.get("session_id", "default")
        agent_id = sse_event.get("agent_id", "unknown")
        status = sse_event.get("status", "unknown")
        prompt = json.dumps(sse_event, sort_keys=True, default=str)
        return await self._narrate(cache_key, session_id, agent_id, status, prompt)

    async def narrate_test_started(self, test_id: str, role: str) -> NarrateEvent:
        cache_key = _make_cache_key(
            {"method": "narrate_test_started", "test_id": test_id, "role": role}
        )
        prompt = f"Test {test_id} started. Role: {role}."
        return await self._narrate(cache_key, test_id, role, "started", prompt)

    async def narrate_test_progress(
        self, test_id: str, percent: int, message: str
    ) -> NarrateEvent:
        cache_key = _make_cache_key(
            {
                "method": "narrate_test_progress",
                "test_id": test_id,
                "percent": percent,
                "message": message,
            }
        )
        prompt = f"Test {test_id} progress: {percent}%. {message}"
        return await self._narrate(cache_key, test_id, "progress", "in_progress", prompt)

    async def narrate_test_completed(
        self, test_id: str, result: str, findings_summary: str
    ) -> NarrateEvent:
        cache_key = _make_cache_key(
            {
                "method": "narrate_test_completed",
                "test_id": test_id,
                "result": result,
                "findings_summary": findings_summary,
            }
        )
        prompt = f"Test {test_id} completed. Result: {result}. Findings: {findings_summary}"
        return await self._narrate(cache_key, test_id, result, "completed", prompt)
