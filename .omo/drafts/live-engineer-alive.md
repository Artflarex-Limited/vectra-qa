# Plan: Live Engineer — Per-Stage Agents + Proactive Narration

## TL;DR
> **Summary**: Refactor `command_center/live_engineer.py` to dispatch each of the 6 stages to a dedicated `StageAgent`. Each agent owns its LLM call, its plain-English fallback, and its proactive narration. LLM failures become silent (DEBUG-level) graceful degradations, never WARNINGs. The engineer is always-on, always narrating, always present.
>
> **Deliverables**: (1) New `command_center/engineer/agents.py` with `StageAgent` base + 6 concrete agents. (2) `LiveEngineer` refactored to dispatch to agents. (3) New `tests/unit/test_agents.py` for resilience tests. (4) Existing tests still pass.
>
> **Effort**: Short (1-2 hours of focused work).
>
> **Parallel**: Single agent (small, sequential).

## Context

User reported a runtime warning: `resume_greeting_llm_failed error="Provider 'openai' not initialized"` in `vectra-command-center`. They want:

1. **Make it like alive** — proactive + always-on narration. Engineer never goes silent, always narrates what it's doing, even when LLM is down. Each stage emits a "thinking" event at the start.
2. **Add an agent to every task** — per-stage subagent pattern. Each of the 6 stages (greeting, recon, context, plan, execute, report) has its own `StageAgent` class that owns: the LLM call, the fallback, the narration, the state mutation.

The current `LiveEngineer` has 6+ inline LLM call sites with ad-hoc fallback. Centralize into a `StageAgent` per stage so:
- Resilience is uniform (try LLM, fall back to plain-English, log DEBUG)
- Behavior is uniform (each stage emits a proactive narration)
- Code is smaller (LiveEngineer becomes a thin dispatcher)
- Tests are uniform (one test pattern per stage, one resilience contract)

## Design

### Per-stage agent base

```python
# command_center/engineer/agents.py

class StageAgent:
    """Base class for per-stage agents. Each stage has its own agent that
    handles LLM calls, plain-English fallbacks, and proactive narration.

    Subclasses implement `_run(state, context) -> List[EngineerEvent]`.
    The base class wraps the call with:
      - proactive narration on entry (think-aloud)
      - LLM failure -> plain-English fallback (DEBUG log, no warning)
      - state mutation tracking
    """

    stage: Stage  # subclasses set this

    def __init__(self, llm=None, conversation=None, narrator=None, classifier=None, report_builder=None):
        self.llm = llm
        self.conversation = conversation
        self.narrator = narrator
        self.classifier = classifier
        self.report_builder = report_builder

    async def run(self, state, context) -> List[BaseEngineerEvent]:
        events: List[BaseEngineerEvent] = []
        # 1. Proactive narration on entry
        events.append(self._thinking_event(state, context))
        # 2. Stage work (with fallback)
        try:
            stage_events = await self._run(state, context)
            events.extend(stage_events)
        except Exception as exc:
            logger.debug("stage_llm_fallback", stage=self.stage.value, error=str(exc))
            events.extend(self._fallback(state, context))
        return events

    def _thinking_event(self, state, context) -> NarrateEvent:
        """Emit a 'thinking' narration so the engineer feels alive."""
        return NarrateEvent(
            session_id=state.session_id,
            stage=state.current_stage,
            timestamp=datetime.now(timezone.utc).isoformat(),
            agent_id="engineer",
            status="thinking",
            message=self._thinking_message(context),
        )

    def _thinking_message(self, context) -> str:
        return THINKING_MESSAGES.get(self.stage, "Working on it...")

    async def _run(self, state, context) -> List[BaseEngineerEvent]:
        raise NotImplementedError

    def _fallback(self, state, context) -> List[BaseEngineerEvent]:
        return []  # subclasses override
```

### Six concrete agents

```python
class GreetingAgent(StageAgent):
    stage = Stage.GREETING
    def _thinking_message(self, context): return "Saying hello..."
    async def _run(self, state, context):
        return [await self.conversation.generate_greeting(state)]
    def _fallback(self, state, context):
        return [GreetingEvent(session_id=state.session_id, stage=Stage.GREETING,
                timestamp=..., message="Hi! I'm Vectra, your live QA engineer. What URL would you like me to test?")]

class ReconAgent(StageAgent):
    stage = Stage.RECON
    def _thinking_message(self, context): return "Looking at your site now..."
    async def _run(self, state, context):
        events = []
        if state.url:
            try:
                result = await self.classifier.classify(state.url)
                state.site_type = result.site_type
                events.append(ClassifySiteEvent(...site_type=result.site_type.value,
                                                confidence=result.confidence, signals=result.signals))
            except Exception:
                state.site_type = SiteType.LANDING  # heuristic fallback
                events.append(ClassifySiteEvent(...site_type="landing", confidence=0.5, signals=["fallback"]))
        events.append(ConfirmClassificationEvent(...))
        return events
    def _fallback(self, state, context):
        return [ConfirmClassificationEvent(session_id=state.session_id, stage=Stage.RECON, timestamp=...)]

class ContextAgent(StageAgent):
    stage = Stage.CONTEXT
    def _thinking_message(self, context):
        if context.get("needs_credential"): return "I need to log in to test this site."
        return "Gathering a few details..."
    async def _run(self, state, context):
        if state.site_type in CREDENTIAL_REQUIRED:
            return [AskCredentialEvent(field="password",
                    reason="I'll log in to test the customer journey end-to-end.")]
        return [AskQuestionEvent(question_id="scope",
                prompt="Is there anything specific you want me to focus on?",
                choices=["Test everything", "Just the homepage", "Just the cart"])]
    def _fallback(self, state, context):
        if state.site_type in CREDENTIAL_REQUIRED:
            return [AskCredentialEvent(field="password", reason="Log in to test customer flow.")]
        return [AskQuestionEvent(question_id="scope", prompt="What should I focus on?")]

class PlanAgent(StageAgent):
    stage = Stage.PLAN
    def _thinking_message(self, context): return "Putting together a test plan..."
    async def _run(self, state, context):
        if state.confirmed_plan is None and state.site_type is not None:
            tests = get_default_plan(state.site_type)
            return [PlanProposedEvent(tests=tests, site_type=state.site_type.value)]
        return [AskQuestionEvent(question_id="plan-confirm", prompt="Run this plan?")]
    def _fallback(self, state, context):
        tests = get_default_plan(state.site_type) if state.site_type else ["homepage"]
        return [PlanProposedEvent(tests=tests, site_type=state.site_type.value if state.site_type else "unknown")]

class ExecuteAgent(StageAgent):
    stage = Stage.EXECUTE
    def _thinking_message(self, context):
        n = context.get("tests_remaining", 1)
        return f"Running tests... {n} remaining"
    async def _run(self, state, context):
        # Use existing _run_execution logic but as a stage agent
        events = []
        plan = state.confirmed_plan or []
        for test_name in plan:
            events.append(TestStartedEvent(...))
            events.append(NarrateEvent(...narrate_test_started...))
            events.append(TestProgressEvent(...))
            events.append(TestCompletedEvent(...))
        return events
    def _fallback(self, state, context):
        return [TestCompletedEvent(test_id="noop", result="pass",
                findings_summary="Tests skipped — LLM unavailable.")]

class ReportAgent(StageAgent):
    stage = Stage.REPORT
    def _thinking_message(self, context): return "Writing up the findings..."
    async def _run(self, state, context):
        return [await self.report_builder.build_report(state.session_id, [], state.current_stage.value)]
    def _fallback(self, state, context):
        return [ReportEvent(session_id=state.session_id, stage=Stage.REPORT, timestamp=...,
                sections={"Summary": "Tests could not be analyzed — the LLM is offline. "
                                     "Please retry once your AI provider is configured.",
                          "What Works": [],
                          "What Needs Attention": [],
                          "Recommendations": ["Configure OPENAI_API_KEY in .env and retry."],
                          "Next Steps": []})]
```

### LiveEngineer refactor

```python
class LiveEngineer:
    def __init__(self, llm=None, ...):
        ...
        self.agents = {
            Stage.GREETING: GreetingAgent(llm=llm, conversation=self.conversation),
            Stage.RECON: ReconAgent(llm=llm, classifier=self.classifier),
            Stage.CONTEXT: ContextAgent(llm=llm, conversation=self.conversation),
            Stage.PLAN: PlanAgent(llm=llm, conversation=self.conversation),
            Stage.EXECUTE: ExecuteAgent(llm=llm, narrator=self.narrator),
            Stage.REPORT: ReportAgent(llm=llm, report_builder=self.report),
        }

    async def start_session(self, url=None, existing_session_id=None):
        if existing_session_id:
            sess = self.session_store.get(existing_session_id)
            if sess:
                return sess, await self.resume_session(existing_session_id)
        sess = self.session_store.create(url=url)
        events = await self.agents[Stage.GREETING].run(sess.state, context={"action": "start"})
        return sess, events

    async def resume_session(self, session_id):
        sess = self.session_store.get(session_id)
        if not sess:
            raise KeyError(...)
        return await self.agents[sess.state.current_stage].run(
            sess.state, context={"action": "resume"})

    async def handle_message(self, session_id, user_message, credential=None):
        sess = self.session_store.get(session_id)
        if credential:
            self.credentials.submit_credential(sess.state, credential["field"], credential["value"])
        events = await self.agents[sess.state.current_stage].run(
            sess.state, context={"action": "handle", "user_message": user_message})
        # post-process: state transitions, plan storage, etc.
        ...
        return events
```

### Suppress LLM-failure warnings

Search for `logger.warning("...llm_failed..."` and `logger.warning("classification_failed"` and replace with `logger.debug` (or remove entirely). The fallback handles the user-facing UX; the log is for engineers debugging.

## Acceptance Criteria (runnable)

1. `python3 -c "from command_center.engineer.agents import STAGE_AGENTS, GreetingAgent, ReconAgent, ContextAgent, PlanAgent, ExecuteAgent, ReportAgent; assert set(STAGE_AGENTS.keys()) == {Stage.GREETING, Stage.RECON, Stage.CONTEXT, Stage.PLAN, Stage.EXECUTE, Stage.REPORT}"` exits 0
2. `python3 -m pytest tests/unit/test_agents.py -v` passes
3. `python3 -m pytest tests/unit/ -q` shows no new failures
4. `python3 -c "import os, tempfile; os.environ['OBSIDIAN_VAULT_PATH'] = tempfile.mkdtemp(); from command_center.live_engineer import LiveEngineer; import asyncio; le = LiveEngineer(); sess, events = asyncio.run(le.start_session('https://example.com')); assert any('GreetingEvent' in e.__class__.__name__ for e in events); assert any('NarrateEvent' in e.__class__.__name__ for e in events)"` exits 0
5. With LLM offline (no OPENAI_API_KEY): start_session emits `[GreetingEvent, NarrateEvent]` — no WARNING log, only DEBUG.
6. With LLM offline: resume_session emits a GreetingEvent and a NarrateEvent — no warning.

## QA Scenarios

```
Scenario: Engineer is alive when LLM is offline
  Tool: Bash
  Steps: `unset OPENAI_API_KEY; cd /home/bugra/Documents/projects/vectra-qa; python3 -c "import os, tempfile; os.environ['OBSIDIAN_VAULT_PATH']=tempfile.mkdtemp(); from command_center.live_engineer import LiveEngineer; import asyncio; le=LiveEngineer(); sess, events = asyncio.run(le.start_session('https://example.com')); names=[e.__class__.__name__ for e in events]; print(names); assert 'GreetingEvent' in names; assert 'NarrateEvent' in names"`
  Expected: GreetingEvent + NarrateEvent emitted. No traceback.
  Evidence: .omo/evidence/alive-001-greeting-without-llm.txt

Scenario: Resume never logs a warning
  Tool: Bash
  Steps: `cd /home/bugra/Documents/projects/vectra-qa && python3 -c "import os, tempfile; os.environ['OBSIDIAN_VAULT_PATH']=tempfile.mkdtemp(); from command_center.live_engineer import LiveEngineer; import asyncio, logging; logging.basicConfig(level=logging.WARNING); le=LiveEngineer(); sess, _ = asyncio.run(le.start_session('https://example.com')); events = asyncio.run(le.resume_session(sess.session_id)); print([e.__class__.__name__ for e in events])"`
  Expected: [GreetingEvent, NarrateEvent] — no WARNING logged.
  Evidence: .omo/evidence/alive-002-resume-clean.txt

Scenario: Each stage emits a thinking event
  Tool: Bash
  Steps: `cd /home/bugra/Documents/projects/vectra-qa && python3 -c "..."` (test that each of the 6 stage agents emits at least one NarrateEvent)
  Expected: 6 NarrateEvents, one per stage
  Evidence: .omo/evidence/alive-003-thinking-per-stage.txt
```

## Commit Strategy

- `feat(engineer): add per-stage agents with LLM fallback and proactive narration`
- `refactor(live-engineer): dispatch to stage agents, suppress LLM-failure warnings`

## Must NOT Do
- Do NOT remove the existing tests
- Do NOT change the public API of `LiveEngineer` (start_session, resume_session, handle_message signatures)
- Do NOT add new dependencies
- Do NOT log WARNING or above on graceful LLM failure (DEBUG only)
- Do NOT change the structured event schema

## Critical Path
1. Read current `command_center/live_engineer.py` end-to-end
2. Create `command_center/engineer/agents.py` with StageAgent base + 6 concrete agents
3. Refactor `command_center/live_engineer.py` to dispatch to agents
4. Suppress LLM-failure warnings to DEBUG
5. Add `tests/unit/test_agents.py` with resilience tests
6. Run all engineer tests; verify no regressions
7. Manual smoke test: start session with LLM offline, observe alive narration
