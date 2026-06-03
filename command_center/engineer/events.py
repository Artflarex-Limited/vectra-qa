"""Structured event schema for the Live QA Engineer.

This module defines :class:`EngineerEvent`, a Pydantic v2 discriminated
union over the event types emitted by the live QA engineer stream.

Design notes
------------
* Every event carries the same three envelope fields — ``session_id``,
  ``stage`` and ``timestamp`` — defined once on :class:`BaseEngineerEvent`.
* Each concrete event class adds a ``type`` ``Literal`` discriminator so
  ``EngineerEvent.model_validate({...})`` can route to the correct class.
* ``model_config = ConfigDict(extra="forbid")`` is set on every model so
  typos / unknown fields surface immediately as ``ValidationError``
  rather than silently propagating through the SSE pipeline.
"""

from __future__ import annotations

from typing import Annotated, Any, Dict, List, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from .state_machine import Stage

# ---------------------------------------------------------------------------
# Shared envelope
# ---------------------------------------------------------------------------


class BaseEngineerEvent(BaseModel):
    """Common envelope shared by every engineer event.

    Carries the per-session routing metadata that the dashboard needs in
    order to display the event in the right panel.
    """

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(..., description="Live QA session identifier.")
    stage: Stage = Field(
        ...,
        description=(
            "Logical pipeline stage the event belongs to "
            "(e.g. 'greeting', 'context', 'recon', 'plan', 'execute', 'report', 'done')."
        ),
    )
    timestamp: str = Field(..., description="ISO-8601 UTC timestamp of event emission.")


# ---------------------------------------------------------------------------
# Concrete event types
# ---------------------------------------------------------------------------


class GreetingEvent(BaseEngineerEvent):
    """Engineer introduces itself and asks how it can help."""

    type: Literal["greeting"] = "greeting"
    message: str = Field(default="", description="Greeting text shown to the user.")


class AskQuestionEvent(BaseEngineerEvent):
    """Open-ended clarifying question with optional multiple-choice options."""

    type: Literal["ask_question"] = "ask_question"
    question_id: str
    prompt: str
    choices: List[str] | None = None


class AskCredentialEvent(BaseEngineerEvent):
    """Prompt the user for a single credential field."""

    type: Literal["ask_credential"] = "ask_credential"
    field: Literal["username", "password"]
    reason: str


class ClassifySiteEvent(BaseEngineerEvent):
    """Engineer's best guess of the target site type with supporting signals."""

    type: Literal["classify_site"] = "classify_site"
    site_type: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    signals: List[str]


class ConfirmClassificationEvent(BaseEngineerEvent):
    """Ask the user to confirm or correct the proposed site classification."""

    type: Literal["confirm_classification"] = "confirm_classification"


class PlanProposedEvent(BaseEngineerEvent):
    """Engineer proposes a test plan keyed by site type."""

    type: Literal["plan_proposed"] = "plan_proposed"
    tests: List[str]
    site_type: str


class NarrateEvent(BaseEngineerEvent):
    """Free-form status narration from an agent during execution."""

    type: Literal["narrate"] = "narrate"
    agent_id: str
    status: str
    message: str


class TestStartedEvent(BaseEngineerEvent):
    """Marks the start of a specific test within the plan."""

    type: Literal["test_started"] = "test_started"
    test_id: str
    role: str


class TestProgressEvent(BaseEngineerEvent):
    """Incremental progress update for an in-flight test."""

    type: Literal["test_progress"] = "test_progress"
    test_id: str
    progress_percent: int = Field(..., ge=0, le=100)
    message: str


class TestCompletedEvent(BaseEngineerEvent):
    """Terminal event for a test — final result + a short findings summary."""

    type: Literal["test_completed"] = "test_completed"
    test_id: str
    result: str
    findings_summary: str


class ReportEvent(BaseEngineerEvent):
    """Aggregated report ready for display, keyed by section name."""

    type: Literal["report"] = "report"
    sections: Dict[str, Any]


class DoneEvent(BaseEngineerEvent):
    """Stream finished — engineer has no more events for this session."""

    type: Literal["done"] = "done"


class ErrorEvent(BaseEngineerEvent):
    """Error surfaced from anywhere in the engineer pipeline."""

    type: Literal["error"] = "error"
    code: str
    message: str


# ---------------------------------------------------------------------------
# Discriminated union
# ---------------------------------------------------------------------------


class _EngineerEventUnion:
    """Discriminated union of all engineer event types.

    Wraps a Pydantic ``TypeAdapter`` so the public API matches the
    ``BaseModel`` ergonomics — ``EngineerEvent.model_validate({...})`` —
    while still exposing ``__discriminator__`` as a stable class
    attribute (the underlying ``TypeAdapter`` does not surface this on
    every Pydantic release line).
    """

    __discriminator__: str = "type"

    def __init__(self) -> None:
        self._adapter: TypeAdapter = TypeAdapter(
            Annotated[
                Union[
                    GreetingEvent,
                    AskQuestionEvent,
                    AskCredentialEvent,
                    ClassifySiteEvent,
                    ConfirmClassificationEvent,
                    PlanProposedEvent,
                    NarrateEvent,
                    TestStartedEvent,
                    TestProgressEvent,
                    TestCompletedEvent,
                    ReportEvent,
                    DoneEvent,
                    ErrorEvent,
                ],
                Field(discriminator="type"),
            ]
        )

    @classmethod
    def model_validate(cls, data: Any) -> BaseModel:
        """Validate ``data`` against the union and return the concrete event."""
        return cls()._adapter.validate_python(data)

    @classmethod
    def model_validate_json(cls, data: str) -> BaseModel:
        """Validate JSON ``data`` against the union and return the concrete event."""
        return cls()._adapter.validate_json(data)

    def validate_python(self, data: Any) -> BaseModel:
        """Direct passthrough to the underlying ``TypeAdapter``."""
        return self._adapter.validate_python(data)


EngineerEvent = _EngineerEventUnion()


__all__ = [
    "BaseEngineerEvent",
    "GreetingEvent",
    "AskQuestionEvent",
    "AskCredentialEvent",
    "ClassifySiteEvent",
    "ConfirmClassificationEvent",
    "PlanProposedEvent",
    "NarrateEvent",
    "TestStartedEvent",
    "TestProgressEvent",
    "TestCompletedEvent",
    "ReportEvent",
    "DoneEvent",
    "ErrorEvent",
    "EngineerEvent",
]
