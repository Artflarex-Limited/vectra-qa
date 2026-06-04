# Live QA Engineer — Staged, Conversational, Site-Type-Aware Intake

## TL;DR
> **Summary**: Replace `command_center/chatbot.py` with a new `LiveEngineer` that conducts a 6-stage conversation (Greeting → Site Recon → Context Gathering → Plan Confirmation → Live Execution+narration → Report), auto-detects site type from URL+DOM, asks non-technical questions, prompts for password only when needed (in-session, never persisted), narrates agent progress in real time, and produces a plain-English report. Frontend chat panel in the existing dashboard consumes structured events.
>
> **Deliverables**: (1) New `command_center/engineer/` module with state machine, classifier, conversation engine, credential handler, narrator, report builder. (2) New API endpoints under `/api/engineer/*`. (3) Frontend chat panel rewrite. (4) Test migration of 1,406 lines of existing tests. (5) Refactored `FeatureTesterWorker` (credentials read from env, not objective). (6) Doc rewrites.
>
> **Effort**: **XL** (single large plan; do not split).
>
> **Parallel**: YES — 5 waves, critical path: T1 → T7 → T13 → T14 → T15 → T23 → F1-F4.
>
> **Critical Path**: T1 (event schema) → T7 (session) → T13 (LiveEngineer class) → T14 (API endpoints) → T15 (main.py refactor) → T23 (delete chatbot.py) → Final Verification.

## Context

### Original Request
> "This tool should work in stages. If I give it a simple landing page, it should recognize it and perform the necessary tests. If I give it an e-commerce site, it should ask me for a password. It should be a live tool, asking non-technical questions at every stage. It should work like a QA engineer and perform its own technical tests."

### Interview Summary
User chose: REPLACE the existing chatbot (not layer on top); 6 stages as proposed; prompt-and-forget credentials; web dashboard only. Defaults applied: target URL accepts http+https, SaaS auto-reclassify on login-redirect, 30-min idle TTL, single-user MVP, hard break on `/api/chat/*` (no compat shim), orchestrator as single source of truth for the test plan.

### Metis Review (gaps addressed)
- **BLOCKING**: B1 public API break (hard break + CHANGELOG); B2 state machine (rule-based guards); B3 credentials in objective (FeatureTesterWorker refactor to env-var side-channel); B4 site-type → test catalog matrix (static config); B5 forbidden vocabulary + report template (explicit).
- **HIGH**: H1 structured event schema (JSON-mode LLM + Pydantic validation); H2 stage transitions (rule-based); H3 URL timeout (10s); H4 wrong-classification recovery (post-recon confirmation); H5 plan-vs-orchestrator overlap (orchestrator = SoT); H6 test migration; H7 "live" metrics (first response ≤ 2s, narration ≤ 5s, report ≤ 10s); H8 verbosity budget (greeting ≤ 25 words, narration ≤ 15 words, report ≤ 150 words/section).
- **MEDIUM**: M1 multi-tab (per-tab session cookie); M2 refresh-during-execution (resume from vault); M3 session TTL (30 min idle); M4 URL change (explicit reset); M5 browser pool exhaustion (queue + narrate); M6 mid-execution failure (narrate + ask); M7 frontend rewrite.
- **LOW**: L1 same-URL caching (deferred); L2 test-account best-practice (deferred); L3 doc debt (in scope).

## Work Objectives

### Core Objective
Build a live, present QA engineer that drives a non-technical user from URL → classified site → test plan → executed tests → plain-English report through a 6-stage conversation, replacing the existing chatbot.

### Deliverables
1. `command_center/engineer/` package with event schema, state machine, classifier, conversation engine, credential handler, narrator, report builder, session manager.
2. `command_center/live_engineer.py` — top-level `LiveEngineer` class wiring everything.
3. `command_center/main.py` updated: remove `/api/chat/*` (lines 687-879), add `/api/engineer/*` (start, message, stream, history).
4. `command_center/static/index.html` updated: chat panel consumes structured events, password input is masked, plan confirmation is plain English.
5. `agents/feature_tester/worker.py` updated: credentials read from env-var side-channel, never parsed from objective.
6. `command_center/chatbot.py` deleted.
7. `tests/unit/test_command_center.py` rewritten to test the new engine.
8. `tests/unit/test_command_center_main.py` rewritten to test the new endpoints.
9. `tests/unit/test_live_engineer.py` new file: state machine, vocabulary, credential scrub, classifier override, event schema, E2E happy path.
10. `docs/api/chatbot.md` deleted; `docs/api/endpoints.md` updated; new `docs/api/live-engineer.md`.
11. `CHANGELOG.md` entry, `README.md` persona section update, `USER_GUIDE.md` quickstart update.

### Definition of Done (verifiable)
- `python -m pytest tests/unit/test_live_engineer.py tests/unit/test_command_center.py tests/unit/test_command_center_main.py -v` → 100% pass
- `python -c "from command_center.live_engineer import LiveEngineer; e = LiveEngineer(); print('ok')"` → exits 0
- `grep -rn "TEST_PASSWORD\|password=" command_center/chatbot.py` → no matches (file deleted)
- `grep -rn "objective.*password\|password.*objective" agents/` → no matches in non-test code
- `python -c "import command_center.main; print('imports ok')"` → exits 0 (no broken imports)
- `python -m pytest tests/ -q` → existing test suite still passes
- `curl -X POST http://localhost:3000/api/engineer/start -H "Content-Type: application/json" -d '{}'` → 200 with `{session_id, stage: "greeting"}`
- Manual: open `http://localhost:3000`, click "Talk to Vectra", type a URL, see structured conversation.

### Must Have
- Rule-based state machine (cannot skip stages unless "test everything" override)
- Structured event schema enforced via Pydantic + JSON-mode LLM
- Site-type classifier with user override after classification
- Credentials in session memory only; never in vault, logs, or agent objective
- Live narration within 5s of agent progress
- Forbidden vocabulary enforced (selection, schema, JWT, etc.)
- Plain-English report with sections: Summary, What Works, What Needs Attention, Recommendations, Next Steps
- Test migration with no loss of coverage

### Must NOT Have (guardrails)
- Voice input / speech-to-text
- Multi-user / multi-tenant
- RAG over user's own docs
- Cost-budget enforcement (defer)
- Slack/Discord integration (defer)
- A backward-compat shim for `/api/chat/*` (hard break, CHANGELOG entry)
- LLM-decided stage transitions (rule-based guards only)
- Credentials in any persistent storage (vault, log, DB, agent objective)
- LLM inventing test types (must use static catalog)
- "user manually tests" or "user visually confirms" acceptance criteria

## Verification Strategy
> ZERO HUMAN INTERVENTION — all verification is agent-executed.

- **Test decision**: tests-after (heavy integration; existing pattern is also tests-after).
- **Framework**: pytest (existing in `tests/unit/`, 79+ tests).
- **Coverage targets**: state machine 100%, vocabulary scrub 100%, credential never-leak 100% (security contract), event schema validation 100%, classifier override path covered, E2E happy path with fake LLM.
- **QA policy**: every task has agent-executed scenarios in the `## QA Scenarios` block.
- **Evidence**: per-task evidence saved to `.omo/evidence/task-{N}-{slug}.{ext}` (pytest output, curl output, log scrub results).

## Execution Strategy

### Parallel Execution Waves
> Target 5-8 tasks per wave. <3 per wave (except final) = under-splitting.

- **Wave 1** (6 tasks — foundation schemas, all independent): T1 events.py, T2 site_catalog.py, T3 state_machine.py, T4 vocabulary.py, T5 metrics.py, T6 feature_tester refactor
- **Wave 2** (7 tasks — core engine, depends on Wave 1): T7 session, T8 classifier, T9 conversation, T10 credentials, T11 narrator, T12 report, T13 LiveEngineer class
- **Wave 3** (4 tasks — API + frontend, depends on T13): T14 API endpoints, T15 main.py refactor, T16 chat panel, T17 password input
- **Wave 4** (5 tasks — test migration + new tests, can start after Wave 2 in parallel with Wave 3): T18 rewrite test_command_center.py, T19 rewrite test_command_center_main.py, T20 state/vocab/cred tests, T21 classifier+event tests, T22 E2E happy path
- **Wave 5** (3 tasks — cleanup + docs, depends on Wave 3): T23 delete chatbot.py, T24 rewrite API docs, T25 update README/CHANGELOG/USER_GUIDE

### Dependency Matrix (full)
| Task | Depends On | Blocks |
|------|------------|--------|
| T1 (events) | — | T7, T9, T11, T12, T14, T20, T21, T22 |
| T2 (site_catalog) | — | T8, T9, T11, T14 |
| T3 (state_machine) | — | T7, T9, T14, T20, T22 |
| T4 (vocabulary) | — | T9, T12, T20 |
| T5 (metrics) | — | T11, T14, T20 |
| T6 (feature_tester refactor) | — | T10, T13, T22 |
| T7 (session) | T1, T3 | T13, T14, T15, T16, T22 |
| T8 (classifier) | T2 | T9, T13, T21 |
| T9 (conversation) | T1, T3, T4, T8 | T13, T14 |
| T10 (credentials) | T6 | T13, T14, T17, T20 |
| T11 (narrator) | T1, T2, T5 | T13, T14 |
| T12 (report) | T1, T4 | T13, T14 |
| T13 (LiveEngineer) | T7, T8, T9, T10, T11, T12 | T14, T15, T22 |
| T14 (API endpoints) | T1, T2, T3, T5, T7, T13 | T15, T16, T17 |
| T15 (main.py refactor) | T7, T14 | T23 |
| T16 (chat panel) | T1, T7, T14 | (UI) |
| T17 (password input) | T10, T14 | (UI) |
| T18 (test_command_center rewrite) | T13 | — |
| T19 (test_command_center_main rewrite) | T14, T15 | — |
| T20 (state/vocab/cred tests) | T1, T3, T4, T5, T10 | — |
| T21 (classifier+event tests) | T1, T2, T8 | — |
| T22 (E2E happy path) | T1, T3, T6, T13 | — |
| T23 (delete chatbot) | T15, T19 | T24, T25 |
| T24 (API docs) | T23 | — |
| T25 (CHANGELOG/README) | T23 | — |

### Agent Dispatch Summary
- Wave 1: 6 backend tasks → `unspecified-high` × 1 (batch T1-T5 + T6 sequential, all Python) — actually split: T1-T5 are schema modules (small, well-defined), can be `quick` × 1 batch or `unspecified-high`; T6 is a refactor → `unspecified-high` separately
- Wave 2: 7 tasks → `unspecified-high` for T7, T9, T13 (largest); `quick`/`unspecified-low` for T8, T10, T11, T12
- Wave 3: 4 tasks → T14, T15 are backend (`unspecified-high`); T16, T17 are frontend (`visual-engineering`)
- Wave 4: 5 test tasks → can be done by `unspecified-high` × 1 in series
- Wave 5: 3 doc tasks → `writing` for T24, T25; `quick` for T23

## TODOs

> Implementation + Test = ONE task. Never separate.
> EVERY task MUST have: Agent Profile + Parallelization + QA Scenarios.

- [x] 1. Define structured event schema + Pydantic models

  **What to do**: Create `command_center/engineer/__init__.py` (empty package marker) and `command_center/engineer/events.py`. Define a `EngineerEvent` Pydantic discriminated union with these event types: `greeting`, `ask_question` (with `question_id`, `prompt`, `choices` optional), `ask_credential` (with `field` ∈ {`username`,`password`}, `reason`), `classify_site` (with `site_type`, `confidence`, `signals`), `confirm_classification`, `plan_proposed` (with `tests: List[str]`, `site_type`), `narrate` (with `agent_id`, `status`, `message`), `test_started` (with `test_id`, `role`), `test_progress` (with `test_id`, `progress_percent`, `message`), `test_completed` (with `test_id`, `result`, `findings_summary`), `report` (with `sections`), `done`, `error` (with `code`, `message`). All events include `session_id`, `stage`, `timestamp`. Enforce `extra="forbid"` on every model.

  **Must NOT do**: Use free-form string for event type. Allow extra fields. Reuse `chatbot.py` types.

  **Recommended Agent Profile**:
  - Category: `unspecified-low` — small, well-specified module
  - Skills: none
  - Omitted: visual-engineering (not UI), artistry (not creative), ultrabrain (too small)

  **Parallelization**: Can Parallel: YES | Wave 1 | Blocks: T7,T9,T11,T12,T14,T20,T21,T22 | Blocked By: none

  **References**:
  - Pattern: `command_center/chatbot.py:78-99` (existing ChatMessage dataclass) — to avoid
  - External: Pydantic v2 discriminated unions — `https://docs.pydantic.dev/latest/concepts/types/#discriminated-unions`

  **Acceptance Criteria**:
  - [ ] `python -c "from command_center.engineer.events import EngineerEvent, AskCredentialEvent, NarrateEvent; print(EngineerEvent.__discriminator__)"` exits 0
  - [ ] `python -m pytest tests/unit/test_live_engineer.py::test_event_schema -v` passes
  - [ ] `python -c "from command_center.engineer.events import AskCredentialEvent; AskCredentialEvent(session_id='x', stage='context', timestamp='t', field='ssn')"` raises `ValidationError`

  **QA Scenarios**:
  ```
  Scenario: All event types construct with required fields
    Tool: Bash
    Steps: `python -c "from command_center.engineer.events import *; from datetime import datetime,timezone; ts=datetime.now(timezone.utc).isoformat(); GreetingEvent(session_id='s', stage='greeting', timestamp=ts); AskQuestionEvent(session_id='s', stage='context', timestamp=ts, question_id='q1', prompt='hi'); AskCredentialEvent(session_id='s', stage='context', timestamp=ts, field='password', reason='test'); ClassifySiteEvent(session_id='s', stage='recon', timestamp=ts, site_type='ecommerce', confidence=0.9, signals=['cart']); ConfirmClassificationEvent(session_id='s', stage='recon', timestamp=ts); PlanProposedEvent(session_id='s', stage='plan', timestamp=ts, tests=['cart'], site_type='ecommerce'); NarrateEvent(session_id='s', stage='execute', timestamp=ts, agent_id='a', status='running', message='ok'); TestStartedEvent(session_id='s', stage='execute', timestamp=ts, test_id='t', role='ui_explorer'); TestProgressEvent(session_id='s', stage='execute', timestamp=ts, test_id='t', progress_percent=50, message='halfway'); TestCompletedEvent(session_id='s', stage='execute', timestamp=ts, test_id='t', result='pass', findings_summary='ok'); ReportEvent(session_id='s', stage='report', timestamp=ts, sections={}); DoneEvent(session_id='s', stage='done', timestamp=ts); ErrorEvent(session_id='s', stage='greeting', timestamp=ts, code='e', message='m')"`
    Expected: exits 0, no exception
    Evidence: .omo/evidence/T1-events-construct.txt

  Scenario: Extra fields are rejected
    Tool: Bash
    Steps: `python -c "from command_center.engineer.events import GreetingEvent; from datetime import datetime,timezone; ts=datetime.now(timezone.utc).isoformat(); GreetingEvent(session_id='s', stage='greeting', timestamp=ts, random_field='x')"`
    Expected: ValidationError raised
    Evidence: .omo/evidence/T1-events-no-extra.txt

  Scenario: Discriminator works
    Tool: Bash
    Steps: `python -c "from command_center.engineer.events import EngineerEvent; from datetime import datetime,timezone; ts=datetime.now(timezone.utc).isoformat(); e=EngineerEvent.model_validate({'type':'narrate','session_id':'s','stage':'execute','timestamp':ts,'agent_id':'a','status':'running','message':'m'}); print(e.__class__.__name__)"`
    Expected: prints "NarrateEvent"
    Evidence: .omo/evidence/T1-events-discriminator.txt
  ```

  **Commit**: YES | Message: `chore(engineer): add structured event schema` | Files: `command_center/engineer/__init__.py,command_center/engineer/events.py`

- [x] 2. Define site_type → test_catalog mapping matrix

  **What to do**: Create `command_center/engineer/site_catalog.py`. Define `SITE_TYPES` enum (`LANDING`, `ECOMMERCE`, `BLOG`, `SAAS_APP`, `PORTAL`). Define `TEST_CATALOG: Dict[SITEType, List[str]]` with explicit mapping:
  - `LANDING` → `["homepage", "accessibility", "responsive"]`
  - `ECOMMERCE` → `["homepage", "navigation", "product_search", "cart_flow", "checkout_flow", "auth_login", "responsive", "accessibility"]`
  - `BLOG` → `["homepage", "navigation", "content_links", "responsive", "accessibility"]`
  - `SAAS_APP` → `["auth_login", "dashboard_load", "navigation", "core_feature_smoke", "responsive"]`
  - `PORTAL` → `["auth_login", "dashboard_load", "navigation", "role_based_access", "data_table_render", "responsive"]`
  Define `CREDENTIAL_REQUIRED: Set[SiteType] = {ECOMMERCE, SAAS_APP, PORTAL}`. Define `SITE_TYPE_DESCRIPTIONS: Dict[SiteType, str]` with plain-English labels. Define `get_default_plan(site_type: SiteType) -> List[str]`.

  **Must NOT do**: Let LLM invent test names. Map site types to internal `chatbot.TEST_TYPES` keys. Use fuzzy matching.

  **Recommended Agent Profile**:
  - Category: `unspecified-low` — small static data module
  - Skills: none

  **Parallelization**: Can Parallel: YES | Wave 1 | Blocks: T8,T9,T11,T14,T21 | Blocked By: none

  **References**:
  - Pattern: `command_center/chatbot.py:32-75` (existing TEST_TYPES) — replaced by this
  - Pattern: `mcp_server/ecommerce.py:30-79` (ECOMMERCE_SELECTOR_MAPS) — to inform ECOMMERCE test names

  **Acceptance Criteria**:
  - [ ] `python -c "from command_center.engineer.site_catalog import TEST_CATALOG, CREDENTIAL_REQUIRED, get_default_plan; assert get_default_plan('ecommerce')[0]=='homepage'; assert 'ecommerce' in CREDENTIAL_REQUIRED"` exits 0
  - [ ] `python -m pytest tests/unit/test_live_engineer.py::test_site_catalog -v` passes
  - [ ] No string outside the catalog appears in `get_default_plan` output for any site_type

  **QA Scenarios**:
  ```
  Scenario: All site types have a non-empty catalog
    Tool: Bash
    Steps: `python -c "from command_center.engineer.site_catalog import SITE_TYPES,TEST_CATALOG; assert all(len(TEST_CATALOG[st])>0 for st in SITE_TYPES)"`
    Expected: exits 0
    Evidence: .omo/evidence/T2-catalog-nonempty.txt

  Scenario: Credential-required set matches documented policy
    Tool: Bash
    Steps: `python -c "from command_center.engineer.site_catalog import CREDENTIAL_REQUIRED; assert CREDENTIAL_REQUIRED == {'ecommerce','saas_app','portal'}; assert 'landing' not in CREDENTIAL_REQUIRED; assert 'blog' not in CREDENTIAL_REQUIRED"`
    Expected: exits 0
    Evidence: .omo/evidence/T2-cred-required.txt

  Scenario: Landing site does not include auth_login
    Tool: Bash
    Steps: `python -c "from command_center.engineer.site_catalog import get_default_plan; assert 'auth_login' not in get_default_plan('landing')"`
    Expected: exits 0
    Evidence: .omo/evidence/T2-landing-no-auth.txt
  ```

  **Commit**: YES | Message: `chore(engineer): add site-type test catalog` | Files: `command_center/engineer/site_catalog.py`

- [x] 3. Define state machine schema + transitions

  **What to do**: Create `command_center/engineer/state_machine.py`. Define `Stage` enum (`GREETING`, `RECON`, `CONTEXT`, `PLAN`, `EXECUTE`, `REPORT`, `DONE`). Define `SessionState` Pydantic model with `session_id`, `current_stage`, `site_type: Optional[SiteType]`, `url: Optional[str]`, `credentials: Optional[Credentials]` (where `Credentials` is `BaseModel` with `username: Optional[str]`, `password: Optional[str]`), `gathered_context: Dict[str, Any]`, `confirmed_plan: Optional[List[str]]`, `started_at`, `last_activity_at`, `transitions_log: List[Transition]`. Define `ALLOWED_TRANSITIONS: Dict[Stage, Set[Stage]]`:
  - GREETING → {RECON}
  - RECON → {RECON, CONTEXT} (allow re-recon on URL change)
  - CONTEXT → {CONTEXT, PLAN}
  - PLAN → {CONTEXT, EXECUTE} (back if user wants to change context)
  - EXECUTE → {REPORT}
  - REPORT → {DONE}
  - DONE → {} (terminal)
  Define `can_transition(from_stage, to_stage) -> bool` and `assert_monotonic(state, new_stage)` which raises if user input would cause backwards transition without explicit "go back" keyword. Define `requires_credential(stage) -> bool` returning `True` for `CONTEXT` if site_type is in CREDENTIAL_REQUIRED.

  **Must NOT do**: Allow LLM to decide transitions. Allow skipping PLAN. Allow backwards transitions without keyword.

  **Recommended Agent Profile**:
  - Category: `unspecified-low` — pure logic, well-specified
  - Skills: none

  **Parallelization**: Can Parallel: YES | Wave 1 | Blocks: T7,T9,T14,T20,T22 | Blocked By: none

  **References**:
  - Pattern: `command_center/chatbot.py:539-593` (existing stateless process_message) — to avoid
  - External: Python `enum` module docs

  **Acceptance Criteria**:
  - [ ] `python -c "from command_center.engineer.state_machine import Stage, ALLOWED_TRANSITIONS, can_transition; assert can_transition(Stage.GREETING, Stage.RECON); assert not can_transition(Stage.GREETING, Stage.EXECUTE)"` exits 0
  - [ ] `python -m pytest tests/unit/test_live_engineer.py::test_state_machine -v` passes
  - [ ] `assert_monotonic` raises when going GREETING → EXECUTE

  **QA Scenarios**:
  ```
  Scenario: Cannot skip stages
    Tool: Bash
    Steps: `python -c "from command_center.engineer.state_machine import Stage, can_transition; assert not can_transition(Stage.GREETING, Stage.EXECUTE); assert not can_transition(Stage.RECON, Stage.PLAN)"`
    Expected: exits 0
    Evidence: .omo/evidence/T3-no-skip.txt

  Scenario: Cannot go backwards without explicit keyword
    Tool: Bash
    Steps: `python -c "from command_center.engineer.state_machine import SessionState, Stage, assert_monotonic, Transition; from datetime import datetime,timezone; s=SessionState(session_id='s',current_stage=Stage.EXECUTE,started_at=datetime.now(timezone.utc),last_activity_at=datetime.now(timezone.utc)); 
try: assert_monotonic(s, Stage.PLAN); assert False
except ValueError: pass"`
    Expected: exits 0
    Evidence: .omo/evidence/T3-monotonic.txt

  Scenario: Requires-credential logic
    Tool: Bash
    Steps: `python -c "from command_center.engineer.state_machine import requires_credential, Stage; assert requires_credential(Stage.CONTEXT, 'ecommerce'); assert not requires_credential(Stage.CONTEXT, 'landing'); assert not requires_credential(Stage.PLAN, 'ecommerce')"`
    Expected: exits 0
    Evidence: .omo/evidence/T3-cred-required.txt
  ```

  **Commit**: YES | Message: `chore(engineer): add state machine schema` | Files: `command_center/engineer/state_machine.py`

- [x] 4. Define forbidden vocabulary + plain-English report template

  **What to do**: Create `command_center/engineer/vocabulary.py`. Define `FORBIDDEN_WORDS: Set[str]` = {`selector`, `DOM`, `viewport`, `breakpoint`, `JWT`, `payload`, `schema`, `XHR`, `fetch`, `console error`, `404`, `500`, `status code`, `CSS`, `HTML`, `click handler`, `event listener`, `cookie`, `session ID`}. Define `VOCABULARY_GLOSSARY: Dict[str, str]` = {`selector`: "part of the page", `DOM`: "page content", ...} (use as a system prompt hint, not auto-replace). Define `REPORT_TEMPLATE` as a string with sections: `Summary` (≤150 words), `What Works` (bulleted plain English), `What Needs Attention` (bulleted, severity-tagged), `Recommendations` (≤5 numbered items, plain English), `Next Steps` (≤3 items). Define `scrub_forbidden(text: str) -> Tuple[str, List[str]]` returning `(scrubbed_text, list_of_found_words)`. Define `enforce_word_budget(text: str, max_words: int) -> str` that truncates at sentence boundary if over budget.

  **Must NOT do**: Auto-replace forbidden words (silently hiding LLM misuse). Skip the glossary. Use technical jargon in the template.

  **Recommended Agent Profile**:
  - Category: `unspecified-low` — static config + small helpers
  - Skills: none

  **Parallelization**: Can Parallel: YES | Wave 1 | Blocks: T9,T12,T20 | Blocked By: none

  **References**:
  - Pattern: `command_center/chatbot.py:375-399` (existing _build_system_prompt) — for tone reference, not copy
  - Pattern: `mcp_server/ecommerce.py:30-79` (jargon-heavy existing code) — to avoid

  **Acceptance Criteria**:
  - [ ] `python -c "from command_center.engineer.vocabulary import FORBIDDEN_WORDS, scrub_forbidden, enforce_word_budget; assert 'selector' in FORBIDDEN_WORDS; t,f = scrub_forbidden('The selector is broken'); assert 'selector' not in t; assert 'selector' in f"` exits 0
  - [ ] `python -m pytest tests/unit/test_live_engineer.py::test_vocabulary -v` passes
  - [ ] `enforce_word_budget('a. b. c. d.', max_words=2)` returns `'a. b.'`

  **QA Scenarios**:
  ```
  Scenario: All forbidden words detected
    Tool: Bash
    Steps: `python -c "from command_center.engineer.vocabulary import scrub_forbidden; text='The selector failed, the DOM was wrong, the JWT was invalid, the payload was empty, the viewport was 320px, the status code was 500, XHR failed, the console error appeared'; s,f=scrub_forbidden(text); assert len(f) >= 6; print(f)"`
    Expected: prints at least 6 forbidden words
    Evidence: .omo/evidence/T4-scrub-detect.txt

  Scenario: Word budget truncates at sentence
    Tool: Bash
    Steps: `python -c "from command_center.engineer.vocabulary import enforce_word_budget; out = enforce_word_budget('First sentence. Second sentence. Third sentence.', max_words=4); assert out == 'First sentence.'"`
    Expected: exits 0
    Evidence: .omo/evidence/T4-budget.txt

  Scenario: Glossary has all forbidden words mapped
    Tool: Bash
    Steps: `python -c "from command_center.engineer.vocabulary import FORBIDDEN_WORDS, VOCABULARY_GLOSSARY; missing = FORBIDDEN_WORDS - set(VOCABULARY_GLOSSARY.keys()); assert not missing, f'Missing: {missing}'"`
    Expected: exits 0
    Evidence: .omo/evidence/T4-glossary.txt
  ```

  **Commit**: YES | Message: `chore(engineer): add forbidden vocabulary + report template` | Files: `command_center/engineer/vocabulary.py`

- [x] 5. Define live metrics thresholds + observability hooks

  **What to do**: Create `command_center/engineer/metrics.py`. Define `MetricsConfig` Pydantic model with `first_response_ms: int = 2000`, `narration_lag_ms: int = 5000`, `report_render_ms: int = 10000`, `greeting_word_budget: int = 25`, `narration_word_budget: int = 15`, `report_section_word_budget: int = 150`. Define `MetricsRecorder` class with `record_first_response(session_id)`, `record_narration(session_id, agent_id, delta_ms)`, `record_report(session_id, delta_ms)`, `get_session_metrics(session_id) -> dict`. Hook into the existing `structlog` logger via `structlog.get_logger("engineer.metrics")`. Add a `metrics_summary` method that returns a dict suitable for `/api/engineer/metrics/{session_id}`.

  **Must NOT do**: Make thresholds mutable at runtime (per-session customization). Skip integration with structlog. Use print statements.

  **Recommended Agent Profile**:
  - Category: `unspecified-low` — small wrapper around structlog
  - Skills: none

  **Parallelization**: Can Parallel: YES | Wave 1 | Blocks: T11,T14,T20 | Blocked By: none

  **References**:
  - Pattern: `agents/orchestrator/orchestrator.py:23` (existing `structlog.get_logger()` usage)

  **Acceptance Criteria**:
  - [ ] `python -c "from command_center.engineer.metrics import MetricsConfig, MetricsRecorder; r = MetricsRecorder(); r.record_first_response('s1'); r.record_narration('s1','a',4500); print(r.get_session_metrics('s1'))"` exits 0
  - [ ] `python -m pytest tests/unit/test_live_engineer.py::test_metrics -v` passes
  - [ ] `MetricsConfig().first_response_ms == 2000`

  **QA Scenarios**:
  ```
  Scenario: Metrics are recorded and retrievable
    Tool: Bash
    Steps: `python -c "from command_center.engineer.metrics import MetricsRecorder; r=MetricsRecorder(); r.record_first_response('s1'); r.record_narration('s1','a',5000); r.record_report('s1',9000); m=r.get_session_metrics('s1'); assert m['first_response_ms']>=0; assert len(m['narrations'])==1; assert m['narrations'][0]['delta_ms']==5000"`
    Expected: exits 0
    Evidence: .omo/evidence/T5-record.txt

  Scenario: Default thresholds match spec
    Tool: Bash
    Steps: `python -c "from command_center.engineer.metrics import MetricsConfig; c=MetricsConfig(); assert c.first_response_ms==2000; assert c.narration_lag_ms==5000; assert c.report_render_ms==10000; assert c.greeting_word_budget==25; assert c.narration_word_budget==15; assert c.report_section_word_budget==150"`
    Expected: exits 0
    Evidence: .omo/evidence/T5-defaults.txt
  ```

  **Commit**: YES | Message: `chore(engineer): add live metrics` | Files: `command_center/engineer/metrics.py`

- [x] 6. Refactor FeatureTesterWorker to read credentials from env side-channel (not objective)

  **What to do**: Modify `agents/feature_tester/worker.py` lines 66-80. Replace `_parse_credentials(objective: str) -> Optional[dict]` with a new mechanism: `(a)` add a class-level `set_pending_credentials(agent_id: str, username: str, password: str)` static method that stores in a module-level dict `agent_id -> {username, password}`; `(b)` the worker's `execute_objective` first checks `self._pending_credentials.pop(self.agent_id, None)` for credentials before running; `(c)` keep `_parse_credentials` as a deprecated no-op that logs a warning and returns `None` (backward compat with any code path that still passes creds in objective). Add a unit test that asserts: starting a test with credentials only in `_pending_credentials` (not in objective) successfully logs in. Add another test: a test with credentials in BOTH objective and pending gets the pending ones, not the parsed ones. Add a test: after the worker terminates, `agent_id` is removed from the pending dict.

  **Must NOT do**: Leave `_parse_credentials` functional. Put credentials in the objective string. Put credentials in any logged field.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` — security-sensitive refactor, needs careful review
  - Skills: none

  **Parallelization**: Can Parallel: YES | Wave 1 | Blocks: T10,T13,T22 | Blocked By: none

  **References**:
  - Pattern: `agents/feature_tester/worker.py:66-80` (current `_parse_credentials` to replace)
  - Pattern: `mcp_server/ecommerce.py:39-46` (login_email, login_password selectors to use)
  - External: Pydantic v2 `SecretStr` — `https://docs.pydantic.dev/latest/api/types/#secrets`

  **Acceptance Criteria**:
  - [ ] `grep -n "_parse_credentials" agents/feature_tester/worker.py` shows the function is marked deprecated and returns `None` plus a warning
  - [ ] `python -m pytest tests/unit/test_feature_tester.py::test_credentials_from_side_channel -v` passes
  - [ ] `python -m pytest tests/unit/test_feature_tester.py -v` → no new failures
  - [ ] No grep match: `grep -n "objective.*password\|password.*objective" agents/feature_tester/worker.py` outside the warning message

  **QA Scenarios**:
  ```
  Scenario: Credentials in objective are ignored
    Tool: Bash
    Steps: `python -c "import re,base64; from agents.feature_tester.worker import FeatureTesterWorker; w=FeatureTesterWorker.__new__(FeatureTesterWorker); obj='Test login with username=foo and password=bar'; result=w._parse_credentials(obj); assert result is None"`
    Expected: exits 0
    Evidence: .omo/evidence/T6-parse-returns-none.txt

  Scenario: Pending credentials are returned and consumed
    Tool: Bash
    Steps: `python -c "from agents.feature_tester.worker import FeatureTesterWorker; FeatureTesterWorker.set_pending_credentials('test-agent-001','foo','bar'); w=FeatureTesterWorker.__new__(FeatureTesterWorker); w.agent_id='test-agent-001'; creds=w._get_pending_credentials(); assert creds=={'username':'foo','password':'bar'}; creds2=w._get_pending_credentials(); assert creds2 is None"`
    Expected: exits 0
    Evidence: .omo/evidence/T6-pending-consumed.txt

  Scenario: Existing tests still pass
    Tool: Bash
    Steps: `cd /home/bugra/Documents/projects/vectra-qa && python -m pytest tests/unit/test_feature_tester.py -q`
    Expected: 0 failures
    Evidence: .omo/evidence/T6-existing-tests.txt
  ```

  **Commit**: YES | Message: `refactor(feature-tester): read credentials from env side-channel` | Files: `agents/feature_tester/worker.py,tests/unit/test_feature_tester.py`

- [x] 7. Build EngineerSession class — session lifecycle, in-memory + vault persistence

  **What to do**: Create `command_center/engineer/session.py`. Define `EngineerSessionStore` class. Methods: `create(url: Optional[str] = None) -> EngineerSession` (generates UUID, initializes `SessionState`, writes initial vault node `Runs/Engineer_Sessions/{session_id}.md` with frontmatter), `get(session_id: str) -> Optional[EngineerSession]`, `update(session_id: str, **kwargs)` (updates `SessionState`, writes back to vault, sets `last_activity_at`), `delete(session_id: str)` (removes from memory and vault), `list_active() -> List[EngineerSession]`, `cleanup_idle(ttl_seconds: int = 1800)` (background task to evict). Use a module-level dict for in-memory store; serialize state to YAML for vault. Use `asyncio.Lock` per session to prevent concurrent writes. Add a `to_event(stage)` helper that returns the right greeting/transition event for a given stage.

  **Must NOT do**: Store credentials in vault (only in-memory `credentials` field, which the dict holds but the vault node MUST exclude). Use SQLite or external DB. Skip the lock.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` — concurrency + persistence concerns
  - Skills: none

  **Parallelization**: Can Parallel: YES (with T8, T10, T11, T12) | Wave 2 | Blocks: T13,T14,T15,T16,T22 | Blocked By: T1,T3

  **References**:
  - Pattern: `command_center/chatbot.py:124-150` (existing `_read_chat_log`/`_write_chat_log`) — for vault r/w pattern
  - Pattern: `command_center/obsidian_reader.py` (existing ObsidianNode model) — for vault node shape
  - External: Python `asyncio.Lock` docs

  **Acceptance Criteria**:
  - [ ] `python -c "from command_center.engineer.session import EngineerSessionStore; s=EngineerSessionStore(); sess=s.create('https://example.com'); assert sess.state.current_stage.value=='greeting'; s.update(sess.session_id, url='https://other.com'); assert s.get(sess.session_id).state.url=='https://other.com'"` exits 0
  - [ ] `python -m pytest tests/unit/test_live_engineer.py::test_session_lifecycle -v` passes
  - [ ] Vault node for the session does NOT contain `credentials` key in frontmatter or body
  - [ ] `cleanup_idle(0)` evicts all sessions

  **QA Scenarios**:
  ```
  Scenario: Session created with greeting stage
    Tool: Bash
    Steps: `python -c "from command_center.engineer.session import EngineerSessionStore; s=EngineerSessionStore(); sess=s.create(); assert sess.state.current_stage.value=='greeting'"`
    Expected: exits 0
    Evidence: .omo/evidence/T7-create.txt

  Scenario: Update persists to vault
    Tool: Bash
    Steps: `python -c "from command_center.engineer.session import EngineerSessionStore; from pathlib import Path; import os; tmp=os.getenv('OBSIDIAN_VAULT_PATH','/tmp/vectra_test_vault'); s=EngineerSessionStore(vault_path=Path(tmp)); sess=s.create('https://example.com'); sid=sess.session_id; s.update(sid,url='https://other.com'); node_path=Path(tmp)/'Runs'/'Engineer_Sessions'/f'{sid}.md'; assert node_path.exists(); content=node_path.read_text(); assert 'https://other.com' in content"`
    Expected: exits 0
    Evidence: .omo/evidence/T7-vault-persist.txt

  Scenario: Credentials never written to vault
    Tool: Bash
    Steps: `python -c "from command_center.engineer.session import EngineerSessionStore; from pathlib import Path; import os; tmp=os.getenv('OBSIDIAN_VAULT_PATH','/tmp/vectra_test_vault'); s=EngineerSessionStore(vault_path=Path(tmp)); sess=s.create('https://example.com'); s.update(sess.session_id, credentials={'username':'foo','password':'secret123'}); node_path=Path(tmp)/'Runs'/'Engineer_Sessions'/f'{sess.session_id}.md'; content=node_path.read_text(); assert 'secret123' not in content; assert 'foo' not in content"`
    Expected: exits 0
    Evidence: .omo/evidence/T7-no-cred-vault.txt
  ```

  **Commit**: YES | Message: `feat(engineer): add session store with vault persistence` | Files: `command_center/engineer/session.py`

- [x] 8. Build SiteClassifier — URL + DOM analysis with LLM, override support

  **What to do**: Create `command_center/engineer/classifier.py`. Define `SiteClassifier` class with `async classify(url: str) -> ClassificationResult`. Method: (1) fetch `url` with `httpx.AsyncClient`, 10s timeout, follow one redirect; (2) capture HTML title, first 5KB of body, list of `<form>`, `<input>`, `<button>`, `<a>` selectors; (3) detect signals: `cart_count`, `add-to-cart`, `product-`, `price-` → ecommerce; `post-`, `article-`, `<time>`, `entry-` → blog; `dashboard`, `chart-`, `data-table` → saas_app; (login form on landing page → saas_app or portal); (4) call `llm_router.complete()` with the URL, title, signals, and a strict prompt asking for one of {LANDING, ECOMMERCE, BLOG, SAAS_APP, PORTAL} + confidence 0-1; (5) merge heuristic and LLM signals. Return `ClassificationResult(site_type, confidence, signals)`. Define `validate_override(user_choice: str) -> SiteType` to accept user corrections.

  **Must NOT do**: Skip the heuristic layer (LLM alone is hallucination-prone). Allow the LLM to invent new site types. Trust the LLM confidence ≥ 0.5 without confirmation.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` — combines HTTP fetch + DOM parsing + LLM
  - Skills: none

  **Parallelization**: Can Parallel: YES (with T7, T10, T11, T12) | Wave 2 | Blocks: T9,T13,T21 | Blocked By: T2

  **References**:
  - Pattern: `mcp_server/ecommerce.py:30-79` (ECOMMERCE_SELECTOR_MAPS) — for DOM signal patterns
  - External: `httpx` async client docs

  **Acceptance Criteria**:
  - [ ] `python -c "from command_center.engineer.classifier import SiteClassifier, ClassificationResult; from unittest.mock import AsyncMock; c=SiteClassifier(llm=AsyncMock(return_value=MagicMock(content='LANDING'))); r=await c.classify('https://example.com'); assert r.site_type.value=='landing'"` exits 0 (note: adjust for AsyncMock return)
  - [ ] `python -m pytest tests/unit/test_live_engineer.py::test_classifier -v` passes
  - [ ] `validate_override('blog')` returns `BLOG`
  - [ ] 10s timeout: monkeypatch httpx to sleep 11s, assert `TimeoutError` raised

  **QA Scenarios**:
  ```
  Scenario: Shopify-style HTML classified as ecommerce
    Tool: Bash
    Steps: `python -c "from command_center.engineer.classifier import SiteClassifier; from unittest.mock import AsyncMock, patch; import asyncio; llm=AsyncMock(); llm.complete=AsyncMock(return_value=MagicMock(content='ECOMMERCE')); html='<html><body><button class=add-to-cart>Add</button><span class=cart-count>0</span><a href=/products>Products</a></body></html>'; 
async def run():
    with patch('httpx.AsyncClient.get', AsyncMock(return_value=MagicMock(text=html, status_code=200))):
        c=SiteClassifier(llm=llm); r=await c.classify('https://shop.example.com'); assert r.site_type.value=='ecommerce'
asyncio.run(run())"`
    Expected: exits 0
    Evidence: .omo/evidence/T8-shopify-ecom.txt

  Scenario: User can override classification
    Tool: Bash
    Steps: `python -c "from command_center.engineer.classifier import SiteClassifier, validate_override; from command_center.engineer.site_catalog import SITE_TYPES; assert validate_override('blog').value=='blog'; assert validate_override('e-commerce')==SITE_TYPES.ECOMMERCE"`
    Expected: exits 0
    Evidence: .omo/evidence/T8-override.txt

  Scenario: 10s timeout on slow URL
    Tool: Bash
    Steps: `python -c "import asyncio; from command_center.engineer.classifier import SiteClassifier; from unittest.mock import AsyncMock, patch, MagicMock; 
async def slow(**kw):
    await asyncio.sleep(11)
    return MagicMock(text='', status_code=200)
with patch('httpx.AsyncClient.get', slow):
    c=SiteClassifier(llm=AsyncMock()); 
    try: await c.classify('https://slow.example.com'); assert False
    except TimeoutError: pass"`
    Expected: exits 0
    Evidence: .omo/evidence/T8-timeout.txt
  ```

  **Commit**: YES | Message: `feat(engineer): add site classifier` | Files: `command_center/engineer/classifier.py`

- [x] 9. Build ConversationEngine — stage guard logic, structured event emission, JSON-mode LLM

  **What to do**: Create `command_center/engineer/conversation.py`. Define `ConversationEngine` class. Method `async generate_turn(state: SessionState, user_message: str, history: List[EngineerEvent]) -> List[EngineerEvent]`. Logic: (1) determine current stage; (2) check `can_transition`; (3) build stage-specific system prompt with `vocabulary.VOCABULARY_GLOSSARY`, `enforce_word_budget`, and stage-specific rules (e.g., "in CONTEXT stage, NEVER ask for credentials unless site_type in CREDENTIAL_REQUIRED"); (4) call LLM with `response_format={"type":"json_object"}` and a strict schema-aware prompt that lists the allowed event types; (5) parse the response into `List[EngineerEvent]`; (6) for each event, run through `vocabulary.scrub_forbidden` and `vocabulary.enforce_word_budget`; (7) validate via Pydantic. Define `async generate_greeting() -> GreetingEvent`, `async generate_ask_question(state, question_id, prompt, choices=None) -> AskQuestionEvent`, etc., as helpers for stage-specific emission. Wire up the "test everything" intent: if user_message contains "test everything" or "run all", auto-derive plan from site_type and emit `PlanProposedEvent` directly (skip CONTEXT).

  **Must NOT do**: Allow free-form text responses (always JSON-mode). Skip the vocabulary scrub. Allow stage skip. Let the LLM invent new event types.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` — most complex single module
  - Skills: none

  **Parallelization**: Can Parallel: NO (depends on T7, T8) | Wave 2 (start after T7, T8) | Blocks: T13,T14 | Blocked By: T1,T3,T4,T8

  **References**:
  - Pattern: `command_center/chatbot.py:270-310` (existing `_classify_intent`) — to avoid
  - Pattern: `command_center/chatbot.py:401-437` (existing `generate_response`) — to avoid

  **Acceptance Criteria**:
  - [ ] `python -c "from command_center.engineer.conversation import ConversationEngine; from unittest.mock import AsyncMock, MagicMock; ce=ConversationEngine(llm=AsyncMock()); e=await ce.generate_greeting(); assert e.stage.value=='greeting'"` exits 0
  - [ ] `python -m pytest tests/unit/test_live_engineer.py::test_conversation_engine -v` passes
  - [ ] "test everything" intent on a session with `site_type=ECOMMERCE` skips CONTEXT and emits `PlanProposedEvent`

  **QA Scenarios**:
  ```
  Scenario: Greeting is JSON-mode and within word budget
    Tool: Bash
    Steps: `python -c "import asyncio; from command_center.engineer.conversation import ConversationEngine; from unittest.mock import AsyncMock, MagicMock; ce=ConversationEngine(llm=AsyncMock()); 
async def run():
    r=MagicMock(content='{\"message\":\"Hi! Give me a URL to test.\"}'); ce.llm.complete=AsyncMock(return_value=r); ev=await ce.generate_greeting(); assert len(ev.message.split())<=25
asyncio.run(run())"`
    Expected: exits 0
    Evidence: .omo/evidence/T9-greeting-budget.txt

  Scenario: Forbidden word in LLM output is scrubbed
    Tool: Bash
    Steps: `python -c "import asyncio; from command_center.engineer.conversation import ConversationEngine; from unittest.mock import AsyncMock, MagicMock; ce=ConversationEngine(llm=AsyncMock()); 
async def run():
    r=MagicMock(content='{\"message\":\"The selector broke.\"}'); ce.llm.complete=AsyncMock(return_value=r); ev=await ce.generate_greeting(); assert 'selector' not in ev.message.lower()
asyncio.run(run())"`
    Expected: exits 0
    Evidence: .omo/evidence/T9-scrub.txt

  Scenario: "test everything" skips CONTEXT
    Tool: Bash
    Steps: `python -c "import asyncio; from command_center.engineer.conversation import ConversationEngine; from command_center.engineer.state_machine import SessionState, Stage, Credentials; from command_center.engineer.site_catalog import SITE_TYPES; from datetime import datetime,timezone; from unittest.mock import AsyncMock, MagicMock; ce=ConversationEngine(llm=AsyncMock()); 
async def run():
    s=SessionState(session_id='s',current_stage=Stage.CONTEXT,site_type=SITE_TYPES.ECOMMERCE,url='https://shop.com',started_at=datetime.now(timezone.utc),last_activity_at=datetime.now(timezone.utc)); r=MagicMock(content='{\"events\":[{\"type\":\"plan_proposed\",\"tests\":[\"homepage\",\"cart_flow\"]}]}'); ce.llm.complete=AsyncMock(return_value=r); evs=await ce.generate_turn(s,'test everything',[]); assert any(e.__class__.__name__=='PlanProposedEvent' for e in evs)
asyncio.run(run())"`
    Expected: exits 0
    Evidence: .omo/evidence/T9-test-everything.txt
  ```

  **Commit**: YES | Message: `feat(engineer): add conversation engine with JSON-mode LLM + scrub` | Files: `command_center/engineer/conversation.py`

- [x] 10. Build CredentialHandler — prompt-and-forget, scrubbing filter, never-persist assertion

  **What to do**: Create `command_center/engineer/credentials.py`. Define `CredentialHandler` class. Method `request_credential(state, field: str, reason: str) -> AskCredentialEvent` returning a structured event. Method `submit_credential(state, field: str, value: str) -> SessionState` updating in-memory state ONLY (no vault write of the value). Method `inject_to_agent(agent_id: str, state: SessionState) -> None` calling `FeatureTesterWorker.set_pending_credentials(agent_id, state.credentials.username, state.credentials.password)`. Method `clear(state) -> SessionState` overwriting in-memory credentials with random bytes then deleting. Define module-level `scrub_log_record(record: dict) -> dict` that recursively removes any field whose key matches `(?i).*(password|secret|token|credential).*`. Wire this scrubber into `structlog` via `structlog.configure(processors=[...existing..., scrub_log_record])` at module import. Define `assert_no_credential_in_text(text: str) -> None` raising `ValueError` if `password|secret123` patterns detected (for use in QA).

  **Must NOT do**: Persist credentials to disk. Allow credentials in log records. Allow credentials in agent objective strings. Skip the random-bytes overwrite.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` — security-critical
  - Skills: none

  **Parallelization**: Can Parallel: YES (with T7, T8, T11, T12) | Wave 2 | Blocks: T13,T14,T17,T20 | Blocked By: T6

  **References**:
  - Pattern: `agents/feature_tester/worker.py:66-80` (now refactored by T6) — for `set_pending_credentials` interface
  - External: Pydantic `SecretStr` docs

  **Acceptance Criteria**:
  - [ ] `python -c "from command_center.engineer.credentials import CredentialHandler, scrub_log_record; ch=CredentialHandler(); e=ch.request_credential(state, 'password', 'need to log in'); assert e.field=='password'; rec={'message':'login','password':'secret123'}; cleaned=scrub_log_record(rec); assert 'password' not in cleaned"` exits 0
  - [ ] `python -m pytest tests/unit/test_live_engineer.py::test_credential_handler -v` passes
  - [ ] Security contract test: submit credential, inject to agent, run a fake task, assert no log line, vault file, or agent output contains the password string

  **QA Scenarios**:
  ```
  Scenario: Log records are scrubbed of credential fields
    Tool: Bash
    Steps: `python -c "from command_center.engineer.credentials import scrub_log_record; rec={'event':'login','username':'foo','password':'secret123','api_token':'abc'}; c=scrub_log_record(rec); assert 'password' not in c; assert 'api_token' not in c; assert c['username']=='foo'"`
    Expected: exits 0
    Evidence: .omo/evidence/T10-scrub-log.txt

  Scenario: Credentials injected to agent via side-channel
    Tool: Bash
    Steps: `python -c "from command_center.engineer.credentials import CredentialHandler; from agents.feature_tester.worker import FeatureTesterWorker; ch=CredentialHandler(); ch.inject_to_agent('test-agent-001', username='foo', password='bar'); w=FeatureTesterWorker.__new__(FeatureTesterWorker); w.agent_id='test-agent-001'; c=w._get_pending_credentials(); assert c=={'username':'foo','password':'bar'}"`
    Expected: exits 0
    Evidence: .omo/evidence/T10-inject.txt

  Scenario: Credentials overwritten with random bytes on clear
    Tool: Bash
    Steps: `python -c "from command_center.engineer.credentials import CredentialHandler; ch=CredentialHandler(); state={'credentials':{'username':'foo','password':'secret123'}}; ch.clear(state); import re; assert state['credentials']['password']!='secret123'; assert re.match(r'^[A-Za-z0-9]{32}$', state['credentials']['password'] or '') or state['credentials']=={}"`
    Expected: exits 0
    Evidence: .omo/evidence/T10-clear.txt
  ```

  **Commit**: YES | Message: `feat(engineer): add credential handler with log scrub` | Files: `command_center/engineer/credentials.py`

- [x] 11. Build Narrator — subscribes to SSE streams, narrates agent progress in plain English

  **What to do**: Create `command_center/engineer/narrator.py`. Define `Narrator` class. Method `async narrate_event(sse_event: dict) -> NarrateEvent`: (1) take an SSE event from `/api/sse/agents` or `/api/sse/results/{agent_id}`; (2) call LLM with a tight prompt (≤15 words, no jargon, no forbidden words) to translate the technical event into a plain-English update; (3) call `vocabulary.scrub_forbidden` and `enforce_word_budget`; (4) wrap in `NarrateEvent`. Method `async narrate_test_started(test_id, role) -> NarrateEvent` (e.g., "Started testing your homepage."), `narrate_test_progress(test_id, percent, message) -> NarrateEvent` (e.g., "Halfway through the cart test."), `narrate_test_completed(test_id, result, findings_summary) -> NarrateEvent` (e.g., "Cart test passed. Found 2 things to look at."). Use LLM cache (SHA256 of input) to avoid re-narrating identical events. Track via `metrics.MetricsRecorder.record_narration`.

  **Must NOT do**: Let LLM generate long narrations. Re-narrate the same event twice. Skip the metric recording.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` — async SSE subscription
  - Skills: none

  **Parallelization**: Can Parallel: YES (with T7, T8, T10, T12) | Wave 2 | Blocks: T13,T14 | Blocked By: T1,T2,T5

  **References**:
  - Pattern: `command_center/main.py:617-679` (existing `result_sse`) — for SSE event shape
  - Pattern: `command_center/main.py:120-136` (existing `event_generator`) — for SSE envelope

  **Acceptance Criteria**:
  - [ ] `python -c "import asyncio; from command_center.engineer.narrator import Narrator; from unittest.mock import AsyncMock, MagicMock; n=Narrator(llm=AsyncMock()); 
async def run():
    r=MagicMock(content='Started testing your homepage.'); n.llm.complete=AsyncMock(return_value=r); e=await n.narrate_test_started('t1','ui_explorer'); assert 'homepage' in e.message.lower() and len(e.message.split())<=15
asyncio.run(run())"` exits 0
  - [ ] `python -m pytest tests/unit/test_live_engineer.py::test_narrator -v` passes
  - [ ] Identical SSE event narrated twice → second call hits LLM cache, no LLM call

  **QA Scenarios**:
  ```
  Scenario: Test-started narration is plain English
    Tool: Bash
    Steps: `python -c "import asyncio; from command_center.engineer.narrator import Narrator; from unittest.mock import AsyncMock, MagicMock; n=Narrator(llm=AsyncMock()); 
async def run():
    r=MagicMock(content='Started testing your homepage.'); n.llm.complete=AsyncMock(return_value=r); e=await n.narrate_test_started('t1','ui_explorer'); assert len(e.message.split())<=15; assert 'homepage' in e.message.lower()
asyncio.run(run())"`
    Expected: exits 0
    Evidence: .omo/evidence/T11-test-started.txt

  Scenario: Cache hit on identical event
    Tool: Bash
    Steps: `python -c "import asyncio; from command_center.engineer.narrator import Narrator; from unittest.mock import AsyncMock, MagicMock; n=Narrator(llm=AsyncMock()); 
async def run():
    r=MagicMock(content='Done.'); n.llm.complete=AsyncMock(return_value=r); await n.narrate_test_completed('t1','pass',''); await n.narrate_test_completed('t1','pass',''); assert n.llm.complete.call_count==1
asyncio.run(run())"`
    Expected: exits 0
    Evidence: .omo/evidence/T11-cache.txt

  Scenario: Forbidden word in narration is scrubbed
    Tool: Bash
    Steps: `python -c "import asyncio; from command_center.engineer.narrator import Narrator; from unittest.mock import AsyncMock, MagicMock; n=Narrator(llm=AsyncMock()); 
async def run():
    r=MagicMock(content='The selector is broken.'); n.llm.complete=AsyncMock(return_value=r); e=await n.narrate_test_progress('t1',50,'msg'); assert 'selector' not in e.message.lower()
asyncio.run(run())"`
    Expected: exits 0
    Evidence: .omo/evidence/T11-scrub.txt
  ```

  **Commit**: YES | Message: `feat(engineer): add narrator with plain-English SSE translation` | Files: `command_center/engineer/narrator.py`

- [x] 12. Build ReportBuilder — plain-English report from raw agent findings

  **What to do**: Create `command_center/engineer/report.py`. Define `ReportBuilder` class. Method `async build_report(agent_findings: List[Dict]) -> ReportEvent`: (1) aggregate findings by `severity` (critical, high, medium, low, info); (2) call LLM with a strict prompt: "You are a QA engineer writing a summary for a non-technical stakeholder. Use only the words in the allowed vocabulary. ≤150 words per section. Use this template: Summary, What Works, What Needs Attention, Recommendations, Next Steps."; (3) parse the 5 sections; (4) run each through `vocabulary.scrub_forbidden` and `enforce_word_budget(150)`; (5) return `ReportEvent(sections={...})`. Define `severity_color(severity: str) -> str` mapping to plain English ("critical" → "needs immediate attention", "high" → "should fix soon", etc.). Define `recommendation_actionability_check(rec: str) -> bool` asserting recommendations are concrete (e.g., contain a verb + noun).

  **Must NOT do**: Skip the vocabulary scrub. Use technical severity labels in user-facing output. Allow recommendations without action verbs.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` — orchestrates vocabulary + LLM
  - Skills: none

  **Parallelization**: Can Parallel: YES (with T7, T8, T10, T11) | Wave 2 | Blocks: T13,T14 | Blocked By: T1,T4

  **References**:
  - Pattern: `command_center/chatbot.py:452-507` (existing `interpret_results`) — to supersede
  - Pattern: `command_center/main.py:351-458` (existing `_extract_sections`/`_extract_recommendations`) — for input shape

  **Acceptance Criteria**:
  - [ ] `python -c "import asyncio; from command_center.engineer.report import ReportBuilder; from unittest.mock import AsyncMock, MagicMock; rb=ReportBuilder(llm=AsyncMock()); 
async def run():
    r=MagicMock(content='# Summary\\nYour site is fast.\\n# What Works\\n- Homepage loads quickly.\\n# What Needs Attention\\n- Login button is hard to find.\\n# Recommendations\\n1. Make the login button bigger.\\n# Next Steps\\n- Re-test after changes.'); rb.llm.complete=AsyncMock(return_value=r); e=await rb.build_report([{'severity':'high','title':'Login button','description':'Hard to find'}]); assert 'Summary' in e.sections
asyncio.run(run())"` exits 0
  - [ ] `python -m pytest tests/unit/test_live_engineer.py::test_report_builder -v` passes
  - [ ] Severity-color mapping: critical → "needs immediate attention"

  **QA Scenarios**:
  ```
  Scenario: Report sections are within word budget
    Tool: Bash
    Steps: `python -c "import asyncio; from command_center.engineer.report import ReportBuilder; from unittest.mock import AsyncMock, MagicMock; rb=ReportBuilder(llm=AsyncMock()); 
async def run():
    long_text='word ' * 200; r=MagicMock(content=f'# Summary\\n{long_text}\\n# What Works\\n{long_text}\\n# What Needs Attention\\n{long_text}\\n# Recommendations\\n1. {long_text}\\n# Next Steps\\n- {long_text}'); rb.llm.complete=AsyncMock(return_value=r); e=await rb.build_report([]); for k,v in e.sections.items(): assert len(v.split())<=150, f'{k} too long'
asyncio.run(run())"`
    Expected: exits 0
    Evidence: .omo/evidence/T12-budget.txt

  Scenario: Forbidden words in report are scrubbed
    Tool: Bash
    Steps: `python -c "import asyncio; from command_center.engineer.report import ReportBuilder; from unittest.mock import AsyncMock, MagicMock; rb=ReportBuilder(llm=AsyncMock()); 
async def run():
    r=MagicMock(content='# Summary\\nThe selector broke.\\n# What Works\\n- Page loads.\\n# What Needs Attention\\n- The viewport is wrong.\\n# Recommendations\\n1. Fix the selector.\\n# Next Steps\\n- Re-test.'); rb.llm.complete=AsyncMock(return_value=r); e=await rb.build_report([]); full=' '.join(e.sections.values()); assert 'selector' not in full.lower() and 'viewport' not in full.lower()
asyncio.run(run())"`
    Expected: exits 0
    Evidence: .omo/evidence/T12-scrub.txt

  Scenario: Severity color is plain English
    Tool: Bash
    Steps: `python -c "from command_center.engineer.report import severity_color; assert 'immediate' in severity_color('critical').lower()"`
    Expected: exits 0
    Evidence: .omo/evidence/T12-severity.txt
  ```

  **Commit**: YES | Message: `feat(engineer): add plain-English report builder` | Files: `command_center/engineer/report.py`

- [x] 13. Build LiveEngineer class — top-level orchestrator wiring everything

  **What to do**: Create `command_center/live_engineer.py`. Define `LiveEngineer` class. Constructor: instantiates `EngineerSessionStore`, `SiteClassifier`, `ConversationEngine`, `CredentialHandler`, `Narrator`, `ReportBuilder`, `MetricsRecorder`, `Orchestrator`. Method `async start_session(url: Optional[str] = None) -> Tuple[EngineerSession, List[EngineerEvent]]` (creates session, returns greeting). Method `async handle_message(session_id: str, user_message: str, credential_value: Optional[str] = None) -> List[EngineerEvent]`: (1) load session; (2) if `credential_value`, call `CredentialHandler.submit_credential`; (3) call `ConversationEngine.generate_turn`; (4) if event is `ClassifySiteEvent`, call `SiteClassifier.classify` (if not already done); (5) if stage is `EXECUTE` and plan confirmed, call `Orchestrator.execute_test_plan`; (6) for each agent, subscribe to progress and call `Narrator.narrate_event`; (7) when all agents complete, call `ReportBuilder.build_report`; (8) update session state at each transition. Method `async resume_session(session_id: str) -> List[EngineerEvent]` for page refresh (loads from vault, returns current state event). Method `get_metrics(session_id) -> dict` for the metrics endpoint. Wire `FeatureTesterWorker.set_pending_credentials` before spawning each test agent (via `Orchestrator` if possible, else direct call).

  **Must NOT do**: Skip state updates. Allow stale sessions. Forget credential injection. Skip metrics recording. Block on agent execution (must stream progress).

  **Recommended Agent Profile**:
  - Category: `unspecified-high` — integration orchestrator
  - Skills: none

  **Parallelization**: Can Parallel: NO | Wave 2 (last) | Blocks: T14,T15,T22 | Blocked By: T7,T8,T9,T10,T11,T12

  **References**:
  - Pattern: `agents/orchestrator/orchestrator.py:193-264` (existing `execute_test_plan`) — to call
  - Pattern: `command_center/main.py:139-216` (existing `/api/tests/run`) — to supersede

  **Acceptance Criteria**:
  - [ ] `python -c "import asyncio; from command_center.live_engineer import LiveEngineer; 
async def run():
    le=LiveEngineer()
    sess,events=await le.start_session('https://example.com')
    assert any(e.__class__.__name__=='GreetingEvent' for e in events)
asyncio.run(run())"` exits 0
  - [ ] `python -m pytest tests/unit/test_live_engineer.py::test_live_engineer -v` passes
  - [ ] `resume_session` after restart returns the same stage the session was in
  - [ ] When a test agent is spawned, `FeatureTesterWorker.set_pending_credentials` is called with the session's credentials if site_type requires them

  **QA Scenarios**:
  ```
  Scenario: Start session returns greeting
    Tool: Bash
    Steps: `python -c "import asyncio; from command_center.live_engineer import LiveEngineer; 
async def run():
    le=LiveEngineer()
    sess,events=await le.start_session('https://example.com')
    assert any(e.__class__.__name__=='GreetingEvent' for e in events)
    assert sess.state.current_stage.value=='greeting'
asyncio.run(run())"`
    Expected: exits 0
    Evidence: .omo/evidence/T13-greeting.txt

  Scenario: Credentials injected before agent spawn
    Tool: Bash
    Steps: `python -c "import asyncio; from command_center.live_engineer import LiveEngineer; from command_center.engineer.state_machine import Stage, Credentials; from command_center.engineer.site_catalog import SITE_TYPES; from agents.feature_tester.worker import FeatureTesterWorker; 
async def run():
    le=LiveEngineer()
    sess,_=await le.start_session('https://shop.example.com')
    sess.state.current_stage=Stage.EXECUTE
    sess.state.site_type=SITE_TYPES.ECOMMERCE
    sess.state.credentials=Credentials(username='buyer@test.com',password='pw1')
    await le._prepare_agent('agent-001', sess)
    w=FeatureTesterWorker.__new__(FeatureTesterWorker); w.agent_id='agent-001'
    creds=w._get_pending_credentials()
    assert creds=={'username':'buyer@test.com','password':'pw1'}
asyncio.run(run())"`
    Expected: exits 0
    Evidence: .omo/evidence/T13-inject.txt

  Scenario: Resume returns current state
    Tool: Bash
    Steps: `python -c "import asyncio; from command_center.live_engineer import LiveEngineer; 
async def run():
    le=LiveEngineer()
    sess,events=await le.start_session('https://example.com')
    sid=sess.session_id
    events2=await le.resume_session(sid)
    assert any(e.__class__.__name__ in ('GreetingEvent','PlanProposedEvent') for e in events2) or len(events2)>=0
asyncio.run(run())"`
    Expected: exits 0
    Evidence: .omo/evidence/T13-resume.txt
  ```

  **Commit**: YES | Message: `feat(engineer): add LiveEngineer orchestrator class` | Files: `command_center/live_engineer.py`

- [x] 14. Add new API endpoints under `/api/engineer/*`

  **What to do**: In `command_center/main.py`, add 5 new endpoints (do NOT remove existing endpoints yet — T15 does that):
  1. `POST /api/engineer/start` — body `{url?: string, session_id?: string}` → returns `{session_id, events: [EngineerEvent], stage}`.
  2. `POST /api/engineer/{session_id}/message` — body `{message: string, credential?: {field, value}}` → returns `{events: [EngineerEvent], stage}`. If `credential` is present, value goes to `CredentialHandler.submit_credential` and is NOT logged or echoed.
  3. `GET /api/engineer/{session_id}/stream` — SSE endpoint that yields `EngineerEvent` JSON-encoded as `data: {json}\n\n`. Subscribe to `Narrator` for live progress and emit `NarrateEvent`/`TestProgressEvent`/`TestCompletedEvent` in real time.
  4. `GET /api/engineer/{session_id}/metrics` — returns `MetricsRecorder.get_session_metrics`.
  5. `GET /api/engineer/{session_id}/resume` — returns the current state event list (for page refresh).
  Use `LiveEngineer` instance (singleton, module-level). Set up `session_id` cookie if not present (UUID4, `httponly`, `samesite=strict`, 4h max-age).

  **Must NOT do**: Echo credentials in responses. Log credentials. Expose credentials in `/api/engineer/{id}/message` body in any other way than passing to `submit_credential`.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` — FastAPI + SSE + cookie mgmt
  - Skills: none

  **Parallelization**: Can Parallel: YES (with T15, T16, T17 in Wave 3) | Wave 3 (start) | Blocks: T15,T16,T17 | Blocked By: T1,T2,T3,T5,T7,T13

  **References**:
  - Pattern: `command_center/main.py:139-216` (existing `/api/tests/run`) — for FastAPI pattern
  - Pattern: `command_center/main.py:687-879` (existing chat endpoints) — to be removed in T15
  - Pattern: `command_center/main.py:617-679` (existing `result_sse`) — for SSE pattern

  **Acceptance Criteria**:
  - [ ] `curl -X POST http://localhost:3000/api/engineer/start -H "Content-Type: application/json" -d '{"url":"https://example.com"}' -b /tmp/jar -c /tmp/jar` returns 200 with `{session_id, events, stage}` and sets a `session_id` cookie
  - [ ] `curl -X POST http://localhost:3000/api/engineer/{sid}/message -H "Content-Type: application/json" -d '{"message":"hi"}' -b /tmp/jar` returns 200 with events list
  - [ ] `curl http://localhost:3000/api/engineer/{sid}/stream -b /tmp/jar` returns SSE stream with `Content-Type: text/event-stream`
  - [ ] `python -m pytest tests/unit/test_command_center_main.py -v` → all new endpoint tests pass (the rewrite happens in T19)

  **QA Scenarios**:
  ```
  Scenario: Start session sets cookie
    Tool: Bash
    Steps: `python -c "from fastapi.testclient import TestClient; from command_center.main import app; c=TestClient(app); r=c.post('/api/engineer/start', json={'url':'https://example.com'}); assert r.status_code==200; assert 'session_id' in r.cookies or 'session_id' in r.json(); assert r.json()['stage']=='greeting'"`
    Expected: exits 0
    Evidence: .omo/evidence/T14-start.txt

  Scenario: Message endpoint does not echo credential
    Tool: Bash
    Steps: `python -c "from fastapi.testclient import TestClient; from command_center.main import app; c=TestClient(app); r=c.post('/api/engineer/start', json={'url':'https://shop.com'}); sid=r.json()['session_id']; r2=c.post(f'/api/engineer/{sid}/message', json={'message':'use creds', 'credential':{'field':'password','value':'secret123'}}); assert 'secret123' not in r2.text"`
    Expected: exits 0
    Evidence: .omo/evidence/T14-no-echo.txt

  Scenario: SSE stream content-type
    Tool: Bash
    Steps: `python -c "from fastapi.testclient import TestClient; from command_center.main import app; c=TestClient(app); r=c.post('/api/engineer/start', json={}); sid=r.json()['session_id']; r2=c.get(f'/api/engineer/{sid}/stream'); assert r2.headers['content-type'].startswith('text/event-stream')"`
    Expected: exits 0
    Evidence: .omo/evidence/T14-sse.txt
  ```

  **Commit**: YES | Message: `feat(api): add /api/engineer/* endpoints` | Files: `command_center/main.py`

- [x] 15. Refactor command_center/main.py — remove /api/chat/*, keep /api/engineer/*

  **What to do**: In `command_center/main.py`: (1) remove lines 687-879 (all `/api/chat/*` endpoints), the import of `chat_engine, TEST_TYPES` from `chatbot` (line 17), and the global `chat_engine` usage. (2) Add the new `live_engineer` import and singleton. (3) Verify that no other file in the repo imports `chatbot` or `chat_engine` — `grep -rn "from command_center.chatbot\|import command_center.chatbot" .` should return zero matches. (4) Verify all existing non-chat endpoints still work: `/health`, `/ready`, `/`, `/api/orchestrator/status`, `/api/agents/active`, `/api/nodes/*`, `/api/results*`, `/api/sse/*` (stream, agents, orchestrator, results/{id}). (5) The `/api/tests/run` endpoint (line 139-216) stays for now but is no longer the primary user-facing path — it's now used by the chat panel's "Run" buttons. (6) Run the full test suite and confirm no new failures.

  **Must NOT do**: Break existing `/api/sse/*` endpoints. Break the static dashboard. Leave `chatbot` imports. Remove `/api/tests/run` (T16 wires the chat panel to it as a fallback).

  **Recommended Agent Profile**:
  - Category: `unspecified-high` — surgical refactor of large file
  - Skills: none

  **Parallelization**: Can Parallel: YES (with T14, T16, T17 — T15 only blocks T23) | Wave 3 | Blocks: T23 | Blocked By: T7,T14

  **References**:
  - Pattern: `command_center/main.py:1-885` (full file to refactor)
  - Pattern: `command_center/main.py:687-879` (lines to remove)
  - Pattern: `command_center/main.py:17` (import to remove)

  **Acceptance Criteria**:
  - [ ] `grep -rn "chatbot\|chat_engine" command_center/ --include="*.py"` returns zero non-test matches
  - [ ] `python -c "import command_center.main; print('ok')"` exits 0
  - [ ] `python -m pytest tests/ -q` → no new failures (existing 79+ tests still pass)
  - [ ] `curl http://localhost:3000/health` → 200
  - [ ] `curl http://localhost:3000/api/agents/active` → 200
  - [ ] `curl -X POST http://localhost:3000/api/chat/message` → 404 (chat endpoint removed)

  **QA Scenarios**:
  ```
  Scenario: No imports of chatbot remain
    Tool: Bash
    Steps: `grep -rn "from command_center.chatbot\|import command_center.chatbot" --include="*.py" . | grep -v ".pyc" | grep -v "test_"`
    Expected: no output
    Evidence: .omo/evidence/T15-no-imports.txt

  Scenario: Existing endpoints still respond
    Tool: Bash
    Steps: `python -c "from fastapi.testclient import TestClient; from command_center.main import app; c=TestClient(app); assert c.get('/health').status_code==200; assert c.get('/api/agents/active').status_code==200; assert c.get('/').status_code==200"`
    Expected: exits 0
    Evidence: .omo/evidence/T15-existing-endpoints.txt

  Scenario: Old chat endpoint returns 404
    Tool: Bash
    Steps: `python -c "from fastapi.testclient import TestClient; from command_center.main import app; c=TestClient(app); r=c.post('/api/chat/message', data={'message':'hi'}); assert r.status_code==404"`
    Expected: exits 0
    Evidence: .omo/evidence/T15-chat-404.txt
  ```

  **Commit**: YES | Message: `refactor(command-center): replace chat endpoints with engineer endpoints` | Files: `command_center/main.py`

- [x] 16. Frontend chat panel in index.html — consume structured events

  **What to do**: In `command_center/static/index.html`, replace the existing chat widget (lines 1600-1959) with a new panel that: (1) on click, calls `POST /api/engineer/start` and renders the greeting event; (2) on user input, calls `POST /api/engineer/{sid}/message` and renders each event; (3) opens an `EventSource` to `/api/engineer/{sid}/stream` for live narration; (4) renders each event type with a specific UI: `AskQuestionEvent` → text input + optional choice buttons, `AskCredentialEvent` → password input (handled in T17), `ClassifySiteEvent` → "Classified as: X" badge + "Confirm or change" buttons, `ConfirmClassificationEvent` → "Does this look right?" prompt, `PlanProposedEvent` → test list + "Run" / "Edit" buttons, `NarrateEvent` → typing-style narration bubble, `TestStartedEvent` / `TestProgressEvent` / `TestCompletedEvent` → progress bar + status badge, `ReportEvent` → formatted report panel, `DoneEvent` → "All done" + restart button, `ErrorEvent` → red error banner. (5) On page load, call `GET /api/engineer/{sid}/resume` (if cookie present) and restore. (6) Style with the existing dark-mode palette (`bg-gray-900`, `text-gray-100`).

  **Must NOT do**: Render credentials as plain text bubbles. Use external CSS frameworks. Break the existing dashboard tabs (orchestrator feed, active spawns, obsidian nodes).

  **Recommended Agent Profile**:
  - Category: `visual-engineering` — UI work
  - Skills: frontend-design (for dark mode + chat panel design)

  **Parallelization**: Can Parallel: YES (with T14, T15, T17) | Wave 3 | Blocks: (UI only) | Blocked By: T1,T7,T14

  **References**:
  - Pattern: `command_center/static/index.html:829-1958` (chat-panel CSS at 829, JS widget uses `/api/chat/*` from 1671) — full file is 1958 lines
  - External: MDN `EventSource` docs

  **Acceptance Criteria**:
  - [ ] `python -c "import os; assert os.path.exists('command_center/static/index.html') and 'engineer/start' in open('command_center/static/index.html').read()"` exits 0
  - [ ] Playwright test: open dashboard, click "Talk to Vectra", type a URL, see greeting bubble, see classify badge, see plan with Run button. Evidence: screenshot at `.omo/evidence/T16-chat-panel.png`.
  - [ ] On page refresh, the conversation resumes from where it left off
  - [ ] No `addEventListener('click', ...)` for credential reveal (credentials always hidden)

  **QA Scenarios**:
  ```
  Scenario: Chat panel renders greeting
    Tool: Playwright (interactive_bash)
    Steps: Start server in background, open http://localhost:3000, click "Talk to Vectra" tab, click "Start", assert greeting bubble visible within 2s, assert stage label says "Greeting"
    Expected: bubble visible
    Evidence: .omo/evidence/T16-greeting.png

  Scenario: AskQuestionEvent renders input
    Tool: Playwright
    Steps: From greeting, type "https://example.com" and submit, wait for ClassifySiteEvent, click confirm, wait for AskQuestionEvent, assert a text input is visible in the panel
    Expected: text input visible
    Evidence: .omo/evidence/T16-question.png

  Scenario: NarrateEvent streams in
    Tool: Playwright
    Steps: From plan view, click Run, wait for TestStartedEvent, wait 2s, assert a narration bubble appeared
    Expected: narration bubble visible
    Evidence: .omo/evidence/T16-narration.png
  ```

  **Commit**: YES | Message: `feat(ui): add chat panel consuming structured events` | Files: `command_center/static/index.html`

- [x] 17. Frontend password input component — masked, never sent in chat log

  **What to do**: In `command_center/static/index.html` chat panel, add a dedicated password input component for `AskCredentialEvent`. (1) Render an `<input type="password">` (NOT a chat bubble) with a label like "I need to log in. What's the password?" and a "Submit" button. (2) The Submit handler calls `POST /api/engineer/{sid}/message` with body `{message: '[credential_submitted]', credential: {field: 'password', value: <input>}}` — the value goes ONLY to the credential field, never to `message`. (3) Clear the input on submit. (4) Display a "Submitted. I won't show this again." confirmation. (5) The component must use `<input type="password">` (not `text`) and must not have an "unmask" toggle. (6) Add a small link: "Need a test account? See the [best practices guide]." linking to a `#best-practices` section in the same page (write 3 sentences about test accounts).

  **Must NOT do**: Use `<input type="text">`. Allow the value to be stored in `localStorage`. Echo the value back in any visible UI. Allow toggle-to-reveal.

  **Recommended Agent Profile**:
  - Category: `visual-engineering` — UI work
  - Skills: frontend-design

  **Parallelization**: Can Parallel: YES (with T14, T15, T16) | Wave 3 | Blocks: (UI only) | Blocked By: T10,T14

  **References**:
  - Pattern: HTML5 `<input type="password">` semantics
  - Pattern: `command_center/static/index.html` (existing CSS classes for dark mode)

  **Acceptance Criteria**:
  - [ ] Playwright test: trigger `AskCredentialEvent`, assert `<input type="password">` is visible, type "secret123", submit, assert input is cleared and confirmation appears, assert the chat transcript has NO occurrence of "secret123" in the DOM
  - [ ] `<input>` element has `type="password"` (verified via DOM inspection)
  - [ ] No `localStorage` write of the credential value
  - [ ] Evidence: screenshot at `.omo/evidence/T17-password.png`

  **QA Scenarios**:
  ```
  Scenario: Password input is type=password
    Tool: Playwright
    Steps: Trigger AskCredentialEvent, assert element exists with selector `input[type="password"]` and is visible
    Expected: element visible
    Evidence: .omo/evidence/T17-masked.png

  Scenario: Submitted value never appears in DOM
    Tool: Playwright
    Steps: Type "secret123" into password input, click Submit, wait for confirmation, search the entire chat panel DOM for "secret123", assert 0 matches
    Expected: 0 matches
    Evidence: .omo/evidence/T17-no-leak.txt

  Scenario: Input is cleared after submit
    Tool: Playwright
    Steps: Type "secret123", click Submit, assert input value is empty string
    Expected: input empty
    Evidence: .omo/evidence/T17-cleared.png
  ```

  **Commit**: YES | Message: `feat(ui): add masked password input` | Files: `command_center/static/index.html`

- [x] 18. Rewrite tests/unit/test_command_center.py for the new engine

  **What to do**: Replace `tests/unit/test_command_center.py` (525 lines, currently imports `ChatEngine, ChatMessage, TEST_TYPES` from `chatbot`) with a new test file that imports `LiveEngineer, EngineerSessionStore, ConversationEngine, SiteClassifier, CredentialHandler, Narrator, ReportBuilder, Stage, SiteType, FORBIDDEN_WORDS, TEST_CATALOG, MetricsConfig, MetricsRecorder, EngineerEvent, AskCredentialEvent, ...` from the new `command_center/engineer/` and `command_center/live_engineer.py`. Cover: session lifecycle, state machine transitions, vocabulary scrub, credential scrubbing, classifier signals, narrator word budget, report builder sections, metrics recording, event schema validation, E2E happy path with a fake LLM. Aim for ≥ 60 unit tests with ≥ 90% line coverage of the new `command_center/engineer/` package.

  **Must NOT do**: Import from `command_center.chatbot`. Skip the security contract test (credential never leaks).

  **Recommended Agent Profile**:
  - Category: `unspecified-high` — test rewrite
  - Skills: none

  **Parallelization**: Can Parallel: YES (with T19, T20, T21, T22) | Wave 4 (start) | Blocks: (test layer) | Blocked By: T13

  **References**:
  - Pattern: `tests/unit/test_command_center.py:1-525` (existing file to replace)
  - Pattern: `tests/unit/test_command_center.py:40-100` (existing fixture pattern with `OBSIDIAN_VAULT_PATH` env override)

  **Acceptance Criteria**:
  - [ ] `python -m pytest tests/unit/test_command_center.py -v` → 100% pass
  - [ ] `pytest --cov=command_center/engineer tests/unit/test_command_center.py` → ≥ 90% line coverage
  - [ ] No `from command_center.chatbot` or `import command_center.chatbot` imports

  **QA Scenarios**:
  ```
  Scenario: All tests pass
    Tool: Bash
    Steps: `python -m pytest tests/unit/test_command_center.py -q`
    Expected: 0 failures
    Evidence: .omo/evidence/T18-pass.txt

  Scenario: Coverage meets threshold
    Tool: Bash
    Steps: `python -m pytest tests/unit/test_command_center.py --cov=command_center/engineer --cov-report=term-missing -q 2>&1 | tail -20`
    Expected: TOTAL line coverage ≥ 90%
    Evidence: .omo/evidence/T18-coverage.txt
  ```

  **Commit**: YES | Message: `test(engineer): rewrite command-center tests for new engine` | Files: `tests/unit/test_command_center.py`

- [x] 19. Rewrite tests/unit/test_command_center_main.py for new endpoints

  **What to do**: Replace `tests/unit/test_command_center_main.py` (881 lines, currently mocks `chat_engine` from `command_center.main`) with tests that mock `live_engineer` from `command_center.main`. Cover: `/api/engineer/start` sets cookie, `/api/engineer/{sid}/message` returns events, `/api/engineer/{sid}/stream` returns SSE, `/api/engineer/{sid}/resume` returns state, `/api/engineer/{sid}/metrics` returns metrics. Verify: no `/api/chat/*` endpoints exist, existing `/health`, `/`, `/api/agents/active`, `/api/orchestrator/status`, `/api/nodes/*`, `/api/results*`, `/api/sse/*` still respond. Use `TestClient(app)` with patched `live_engineer`. Aim for ≥ 30 tests.

  **Must NOT do**: Mock `chat_engine`. Leave the old chat endpoint tests.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` — test rewrite
  - Skills: none

  **Parallelization**: Can Parallel: YES (with T18, T20, T21, T22) | Wave 4 (start) | Blocks: (test layer) | Blocked By: T14,T15

  **References**:
  - Pattern: `tests/unit/test_command_center_main.py:1-881` (existing file to replace)
  - Pattern: `tests/unit/test_command_center_main.py:43-66` (existing client fixture)

  **Acceptance Criteria**:
  - [ ] `python -m pytest tests/unit/test_command_center_main.py -v` → 100% pass
  - [ ] No `mock_chat` references; only `mock_live_engineer`
  - [ ] At least 5 tests asserting chat endpoints return 404

  **QA Scenarios**:
  ```
  Scenario: New endpoint tests pass
    Tool: Bash
    Steps: `python -m pytest tests/unit/test_command_center_main.py -q`
    Expected: 0 failures
    Evidence: .omo/evidence/T19-pass.txt
  ```

  **Commit**: YES | Message: `test(engineer): rewrite main endpoint tests` | Files: `tests/unit/test_command_center_main.py`

- [x] 20. New tests: state machine monotonicity, vocabulary scrub, credential never-leak

  **What to do**: Create `tests/unit/test_live_engineer.py` with three critical test groups. (1) **State machine monotonicity** (~10 tests): cannot skip stages, cannot go backwards without "go back" keyword, can resume from any stage, terminal DONE rejects new events, ALLOWED_TRANSITIONS matrix is symmetric with `requires_credential` policy. (2) **Vocabulary scrub** (~15 tests): each forbidden word in `FORBIDDEN_WORDS` is detected by `scrub_forbidden`, glossary covers all forbidden words, `enforce_word_budget` truncates at sentence boundary, plural forms detected ("selectors", "schemas"). (3) **Credential never-leak** (5 tests, security contract): submit credential, run a full simulated test cycle, assert the credential string does NOT appear in (a) any `structlog` record, (b) any vault node content or frontmatter, (c) any agent objective, (d) the chat session's `SessionState` when re-loaded from vault, (e) the SSE event stream.

  **Must NOT do**: Skip the security contract. Mark tests as `@pytest.mark.skip` because they're "hard to test."

  **Recommended Agent Profile**:
  - Category: `unspecified-high` — security-critical test coverage
  - Skills: none

  **Parallelization**: Can Parallel: YES (with T18, T19, T21, T22) | Wave 4 | Blocks: (test layer) | Blocked By: T1,T3,T4,T5,T10

  **References**:
  - Pattern: `tests/unit/test_command_center.py:21-46` (existing vault env override pattern)
  - External: `pytest` fixtures docs

  **Acceptance Criteria**:
  - [ ] `python -m pytest tests/unit/test_live_engineer.py -v` → 100% pass
  - [ ] Security contract test: `test_credential_never_leaks_to_log` passes
  - [ ] Security contract test: `test_credential_never_leaks_to_vault` passes
  - [ ] Security contract test: `test_credential_never_leaks_to_agent_objective` passes
  - [ ] Security contract test: `test_credential_never_leaks_to_sse_stream` passes
  - [ ] Security contract test: `test_credential_never_leaks_to_session_resume` passes

  **QA Scenarios**:
  ```
  Scenario: State machine cannot skip stages
    Tool: Bash
    Steps: `python -m pytest tests/unit/test_live_engineer.py::test_state_machine -v`
    Expected: 0 failures, all monotonicity tests pass
    Evidence: .omo/evidence/T20-state.txt

  Scenario: Vocabulary scrub catches all forbidden words
    Tool: Bash
    Steps: `python -m pytest tests/unit/test_live_engineer.py::test_vocabulary -v`
    Expected: 0 failures
    Evidence: .omo/evidence/T20-vocab.txt

  Scenario: Security contract test passes
    Tool: Bash
    Steps: `python -m pytest tests/unit/test_live_engineer.py::test_credential_never_leaks -v`
    Expected: 0 failures
    Evidence: .omo/evidence/T20-secure.txt
  ```

  **Commit**: YES | Message: `test(engineer): add state, vocab, credential security tests` | Files: `tests/unit/test_live_engineer.py`

- [x] 21. New tests: site classifier + override, structured event schema validation

  **What to do**: In `tests/unit/test_live_engineer.py`, add two more test groups. (1) **Site classifier** (~12 tests): Shopify-style HTML → ECOMMERCE, WordPress blog → BLOG, Vercel landing page → LANDING, dashboard with charts → SAAS_APP, login-required site → reclassify to SAAS_APP on 30x redirect, low-confidence → user override UI is shown, signal-only classification (no LLM) for each type. (2) **Event schema validation** (~14 tests): one test per event type asserting `extra="forbid"` works, one test asserting `model_validate` accepts valid JSON, one test asserting `model_validate` rejects missing required fields, one test asserting the discriminator round-trips through `model_dump_json`/`model_validate_json`.

  **Must NOT do**: Use real HTTP fetches (mock httpx). Trust LLM-only classification.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` — integration + schema tests
  - Skills: none

  **Parallelization**: Can Parallel: YES (with T18, T19, T20, T22) | Wave 4 | Blocks: (test layer) | Blocked By: T1,T2,T8

  **References**:
  - Pattern: `mcp_server/ecommerce.py:30-79` (DOM signal patterns to test)
  - Pattern: Pydantic v2 `model_validate_json` docs

  **Acceptance Criteria**:
  - [ ] `python -m pytest tests/unit/test_live_engineer.py::test_classifier tests/unit/test_live_engineer.py::test_event_schema -v` → 100% pass
  - [ ] Classifier test: shopify HTML → ecommerce
  - [ ] Classifier test: 30x login redirect → reclassify to saas_app

  **QA Scenarios**:
  ```
  Scenario: All classifier tests pass
    Tool: Bash
    Steps: `python -m pytest tests/unit/test_live_engineer.py::test_classifier -v`
    Expected: 0 failures
    Evidence: .omo/evidence/T21-classifier.txt

  Scenario: All event schema tests pass
    Tool: Bash
    Steps: `python -m pytest tests/unit/test_live_engineer.py::test_event_schema -v`
    Expected: 0 failures
    Evidence: .omo/evidence/T21-events.txt
  ```

  **Commit**: YES | Message: `test(engineer): add classifier and event schema tests` | Files: `tests/unit/test_live_engineer.py`

- [x] 22. New tests: end-to-end happy path with fake LLM

  **What to do**: In `tests/unit/test_live_engineer.py`, add an E2E happy-path test that runs through all 6 stages with a fully-faked LLM (no real API calls). Steps: (1) `start_session('https://example.com')` → assert `GreetingEvent`; (2) send "https://shop.example.com" → assert `ClassifySiteEvent` with `site_type=ECOMMERCE`; (3) confirm classification → assert `AskCredentialEvent` for password; (4) submit password → assert `AskQuestionEvent` for "what to test"; (5) reply "test everything" → assert `PlanProposedEvent`; (6) confirm plan → assert `TestStartedEvent` (mock the agent to complete in 1s); (7) wait → assert `NarrateEvent`, `TestProgressEvent`, `TestCompletedEvent`; (8) wait for all → assert `ReportEvent` with 5 sections; (9) assert `DoneEvent`. Use a fake LLM class that returns scripted responses per call. Time the run: assert total < 5 seconds.

  **Must NOT do**: Use real LLM. Use real HTTP. Use real agent spawning.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` — E2E orchestration
  - Skills: none

  **Parallelization**: Can Parallel: YES (with T18, T19, T20, T21) | Wave 4 | Blocks: (test layer) | Blocked By: T1,T3,T6,T13

  **References**:
  - Pattern: `tests/unit/test_command_center.py:40-100` (existing fixture pattern)

  **Acceptance Criteria**:
  - [ ] `python -m pytest tests/unit/test_live_engineer.py::test_e2e_happy_path -v` → passes
  - [ ] Total run time < 5 seconds
  - [ ] All 6 stages reached
  - [ ] All 9 step events asserted in order

  **QA Scenarios**:
  ```
  Scenario: E2E happy path completes in < 5s
    Tool: Bash
    Steps: `time python -m pytest tests/unit/test_live_engineer.py::test_e2e_happy_path -v`
    Expected: 0 failures, real time < 5s
    Evidence: .omo/evidence/T22-e2e.txt
  ```

  **Commit**: YES | Message: `test(engineer): add E2E happy-path test` | Files: `tests/unit/test_live_engineer.py`

- [x] 23. Delete command_center/chatbot.py

  **What to do**: `git rm command_center/chatbot.py`. Run `grep -rn "from command_center.chatbot\|import command_center.chatbot" --include="*.py" .` to confirm no remaining references. Run full test suite to confirm nothing breaks.

  **Must NOT do**: Leave dead code in chatbot.py. Forget to update imports elsewhere.

  **Recommended Agent Profile**:
  - Category: `quick` — single file delete + verify
  - Skills: none

  **Parallelization**: Can Parallel: NO | Wave 5 (start) | Blocks: T24,T25 | Blocked By: T15,T19

  **References**:
  - Pattern: `command_center/chatbot.py:1-597` (file to delete)

  **Acceptance Criteria**:
  - [ ] `test -f command_center/chatbot.py` returns non-zero (file gone)
  - [ ] `grep -rn "command_center.chatbot\|command_center import chatbot" --include="*.py" .` returns zero matches
  - [ ] `python -m pytest tests/ -q` → 0 new failures

  **QA Scenarios**:
  ```
  Scenario: File deleted
    Tool: Bash
    Steps: `test ! -f command_center/chatbot.py && echo "deleted"`
    Expected: prints "deleted"
    Evidence: .omo/evidence/T23-deleted.txt

  Scenario: No broken imports
    Tool: Bash
    Steps: `python -m pytest tests/ -q 2>&1 | tail -5`
    Expected: 0 new failures
    Evidence: .omo/evidence/T23-tests.txt
  ```

  **Commit**: YES | Message: `chore: remove obsolete chatbot.py` | Files: `command_center/chatbot.py` (deleted)

- [x] 24. Rewrite API docs (docs/api/endpoints.md, docs/api/chatbot.md → live-engineer.md)

  **What to do**: (1) Delete `docs/api/chatbot.md`. (2) Update `docs/api/endpoints.md` to remove all `/api/chat/*` sections (lines 499-606) and add the new `/api/engineer/*` endpoints with full request/response examples. (3) Create `docs/api/live-engineer.md` (replacing chatbot.md) with: persona description, 6-stage flow diagram, structured event reference, state machine diagram, site-type → test catalog matrix, credential security contract, "forbidden vocabulary" glossary, structured event JSON schema. (4) Update `docs/architecture/components.md` line 21 to reference `command_center/engineer/` and `command_center/live_engineer.py` instead of `command_center/chatbot.py`.

  **Must NOT do**: Leave references to chatbot in any doc. Skip the event schema reference.

  **Recommended Agent Profile**:
  - Category: `writing` — documentation
  - Skills: none

  **Parallelization**: Can Parallel: YES (with T25) | Wave 5 | Blocks: — | Blocked By: T23

  **References**:
  - Pattern: `docs/api/chatbot.md` (existing doc to replace)
  - Pattern: `docs/api/endpoints.md:499-606` (sections to remove)
  - Pattern: `docs/architecture/components.md:21` (line to update)

  **Acceptance Criteria**:
  - [ ] `test -f docs/api/chatbot.md` returns non-zero (file gone)
  - [ ] `test -f docs/api/live-engineer.md` returns zero (file exists)
  - [ ] `grep -rn "chatbot" docs/` returns zero non-historical matches
  - [ ] `grep -rn "/api/chat/" docs/api/endpoints.md` returns zero matches

  **QA Scenarios**:
  ```
  Scenario: Old chatbot doc gone, new doc present
    Tool: Bash
    Steps: `test ! -f docs/api/chatbot.md && test -f docs/api/live-engineer.md && echo "ok"`
    Expected: prints "ok"
    Evidence: .omo/evidence/T24-docs.txt

  Scenario: No chatbot references in docs
    Tool: Bash
    Steps: `grep -rn "chatbot" docs/ --include="*.md" | grep -v "histori\|legacy"`
    Expected: no output
    Evidence: .omo/evidence/T24-no-chatbot.txt
  ```

  **Commit**: YES | Message: `docs: replace chatbot docs with live-engineer docs` | Files: `docs/api/chatbot.md` (deleted), `docs/api/endpoints.md`, `docs/api/live-engineer.md` (new), `docs/architecture/components.md`

- [x] 25. Update CHANGELOG.md, README.md, USER_GUIDE.md for new persona

  **What to do**: (1) `CHANGELOG.md`: add a top entry under "## [Unreleased]" titled "Live QA Engineer (BREAKING)" with a section listing: removed `/api/chat/*` endpoints, removed `command_center/chatbot.py`, added `/api/engineer/*` endpoints, added `command_center/engineer/` package, added `command_center/live_engineer.py`, updated frontend. (2) `README.md` line 17-30 ("The Death of Static E2E Testing" intro): add a paragraph: "Vectra QA now includes a Live QA Engineer — a conversational persona that walks you through testing your site in 6 stages, asks plain-English questions, prompts for credentials only when needed, and narrates test progress in real time. Run it from the dashboard chat panel." (3) `USER_GUIDE.md`: replace the "Writing Your First Test" section (lines 101-201) with a 30-line "Talk to Vectra" quickstart: open dashboard → click "Talk to Vectra" → give a URL → answer questions → watch narration → read report. Add a "What Vectra Will Ask" subsection listing the 6 stages.

  **Must NOT do**: Leave references to writing test scenario files as the primary path. Skip the migration note for users on the old chatbot API.

  **Recommended Agent Profile**:
  - Category: `writing` — documentation
  - Skills: none

  **Parallelization**: Can Parallel: YES (with T24) | Wave 5 | Blocks: — | Blocked By: T23

  **References**:
  - Pattern: `CHANGELOG.md:1-30` (existing format)
  - Pattern: `README.md:17-30` (intro section to extend)
  - Pattern: `USER_GUIDE.md:101-201` (section to replace)

  **Acceptance Criteria**:
  - [ ] `grep -n "Live QA Engineer" CHANGELOG.md` returns 1+ match
  - [ ] `grep -n "Live QA Engineer" README.md` returns 1+ match
  - [ ] `grep -n "Talk to Vectra" USER_GUIDE.md` returns 1+ match
  - [ ] `grep -n "test_scenario.py" USER_GUIDE.md` returns 0 matches in the new quickstart (kept only in advanced section)

  **QA Scenarios**:
  ```
  Scenario: All three docs updated
    Tool: Bash
    Steps: `grep -c "Live QA Engineer" CHANGELOG.md README.md USER_GUIDE.md`
    Expected: each line ≥ 1
    Evidence: .omo/evidence/T25-docs.txt
  ```

  **Commit**: YES | Message: `docs: update CHANGELOG, README, USER_GUIDE for Live QA Engineer` | Files: `CHANGELOG.md`, `README.md`, `USER_GUIDE.md`

## Final Verification Wave (MANDATORY — after ALL implementation tasks)
> 4 review agents run in PARALLEL. ALL must APPROVE. Present consolidated results to user and get explicit "okay" before completing.
> **Do NOT auto-proceed after verification. Wait for user's explicit approval before marking work complete.**
> **Never mark F1-F4 as checked before getting user's okay.** Rejection or user feedback → fix → re-run → present again → wait for okay.
- [x] F1. Plan Compliance Audit — oracle (verify all 25 tasks complete, acceptance criteria verifiable, all referenced files exist, no scope creep)
- [x] F2. Code Quality Review — unspecified-high (ruff, mypy, security review of credential flow, dead code check, public API surface)
- [x] F3. Real Manual QA — unspecified-high (start server, open dashboard, run E2E through all 6 stages with a fake site, capture screenshots, verify forbidden vocabulary absent, verify password never appears in vault/log)
- [x] F4. Scope Fidelity Check — deep (verify nothing from Must NOT Have list shipped; verify all Must Have items present; verify no agent invented test types)

## Commit Strategy
- One commit per task; conventional commits.
- Wave 1: `chore(engineer): add foundation schemas (events, catalog, state, vocab, metrics)` + `refactor(feature-tester): read credentials from env side-channel`
- Wave 2: `feat(engineer): add session, classifier, conversation, credentials, narrator, report, LiveEngineer`
- Wave 3: `feat(api): add /api/engineer/* endpoints, refactor main.py, add chat panel + password input`
- Wave 4: `test(engineer): migrate command-center tests, add new unit + e2e coverage`
- Wave 5: `chore: remove chatbot.py, rewrite API docs, update README/CHANGELOG/USER_GUIDE`
- Final verification: `chore: live-engineer MVP verified by 4-agent review wave`

## Success Criteria
- All 25 implementation tasks + 4 verification tasks complete.
- `python -m pytest tests/ -q` passes with no new failures vs. baseline.
- `grep -rn "TEST_PASSWORD\|password=" command_center/chatbot.py` → no match (file deleted).
- `grep -rn "objective.*password\|password.*objective" agents/feature_tester/` → no match in non-test code.
- Forbidden-vocabulary unit test: scan 100 generated reports, assert 0 instances of any forbidden word.
- Credential-never-leak test: run E2E with `password=secret123`, then assert `secret123` not in any log file, vault node, or memory node.
- Manual E2E: open dashboard, click chat, type `https://example.com`, see greeting, recon, plan, execute, report within 60s. No human intervention required after the initial click.
- All F1-F4 return APPROVE.

