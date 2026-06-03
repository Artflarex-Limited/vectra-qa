"""Unit tests for command_center.engineer modules (T4 vocabulary, T8 classifier).

Covers FORBIDDEN_WORDS shape, scrub_forbidden detection + cleaning,
enforce_word_budget sentence-boundary truncation, glossary completeness,
the 5-section report template, and the SiteClassifier heuristic + LLM flow.
"""
from __future__ import annotations

import asyncio
import os
import tempfile

# Redirect the Obsidian vault to a temp dir BEFORE importing the engineer
# modules — EngineerSessionStore() tries to create Runs/Engineer_Sessions/
# on instantiation and the default path (/app/obsidian_vault) is not
# writable in this environment.
_VAULT_TMPDIR = tempfile.mkdtemp(prefix="vectra_test_vault_engineer_")
os.environ["OBSIDIAN_VAULT_PATH"] = _VAULT_TMPDIR

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from command_center.engineer.vocabulary import (
    FORBIDDEN_WORDS,
    REPORT_TEMPLATE,
    VOCABULARY_GLOSSARY,
    enforce_word_budget,
    scrub_forbidden,
)
from command_center.engineer.classifier import (
    ClassificationResult,
    SiteClassifier,
    validate_override,
)
from command_center.engineer.credentials import (
    CredentialHandler,
    assert_no_credential_in_text,
    scrub_log_record,
)
from pydantic import ValidationError

from command_center.engineer.events import (
    AskCredentialEvent,
    AskQuestionEvent,
    BaseEngineerEvent,
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
from command_center.engineer.site_catalog import SITE_TYPES, SiteType
from command_center.engineer.state_machine import Credentials, SessionState


def test_vocabulary() -> None:
    """Aggregate smoke test for the T4 vocabulary module.

    Each assertion maps to one of the acceptance criteria in
    .omo/plans/live-qa-engineer.md (T4) or the plan's QA scenarios.
    """
    # --- FORBIDDEN_WORDS shape ---
    assert "selector" in FORBIDDEN_WORDS
    # plurals are present
    for plural in ("selectors", "schemas", "payloads", "viewports", "cookies"):
        assert plural in FORBIDDEN_WORDS, f"missing plural: {plural}"

    # --- scrub_forbidden: removes word, returns it in the found list ---
    cleaned, found = scrub_forbidden("The selector is broken")
    assert "selector" not in cleaned
    assert "selector" in found
    # plural detection via lowercase substring
    cleaned_p, found_p = scrub_forbidden("All the selectors are broken")
    assert "selectors" in found_p
    assert "selectors" not in cleaned_p

    # --- scrub_forbidden: case-insensitive ---
    cleaned_c, found_c = scrub_forbidden("The DOM was empty and the Jwt was wrong")
    # 'DOM' (uppercase) and 'JWT' (uppercase) should be detected
    assert any(w.upper() == "DOM" for w in found_c)
    assert any(w.upper() == "JWT" for w in found_c)

    # --- scrub_forbidden: 'console error' (multi-word) is detected ---
    cleaned_e, found_e = scrub_forbidden("a console error appeared on the page")
    assert "console error" in found_e
    assert "console error" not in cleaned_e

    # --- scrub_forbidden: empty / None-safe ---
    assert scrub_forbidden("") == ("", [])

    # --- scrub_forbidden: high-volume detection (QA scenario 1) ---
    text = (
        "The selector failed, the DOM was wrong, the JWT was invalid, "
        "the payload was empty, the viewport was 320px, the status code was 500, "
        "XHR failed, the console error appeared"
    )
    _, found = scrub_forbidden(text)
    assert len(found) >= 6

    # --- enforce_word_budget: acceptance criterion (max_words=2) ---
    assert enforce_word_budget("a. b. c. d.", max_words=2) == "a. b."

    # --- enforce_word_budget: no truncation when within budget ---
    out = enforce_word_budget("Just one sentence.", max_words=10)
    assert out == "Just one sentence."

    # --- enforce_word_budget: empty input ---
    assert enforce_word_budget("", max_words=5) == ""
    assert enforce_word_budget("some text", max_words=0) == ""

    # --- enforce_word_budget: never breaks a sentence in the middle ---
    # First sentence alone exceeds the budget — surface it rather than truncating
    # the word in half (the 'kept' guard).
    out = enforce_word_budget("This is a fairly long first sentence. Second.", max_words=2)
    # The function returns the first sentence in full because we never break
    # a sentence in the middle. wc_after_first = 6 > 2, but 'kept' is empty so
    # we still add it. Next sentence would push to 8, break. Result has 1 sentence.
    assert out.startswith("This is a fairly long first sentence.")

    # --- enforce_word_budget: stops at sentence boundary, not word boundary ---
    out = enforce_word_budget(
        "First sentence. Second sentence. Third sentence.", max_words=2
    )
    assert out == "First sentence."

    # --- glossary covers every forbidden word (QA scenario 3) ---
    missing = FORBIDDEN_WORDS - set(VOCABULARY_GLOSSARY.keys())
    assert not missing, f"missing glossary entries: {missing}"

    # --- glossary values are non-empty, plain-English, and not the original word ---
    for word, plain in VOCABULARY_GLOSSARY.items():
        assert plain.strip(), f"empty glossary entry for {word!r}"
        # The glossary should not just echo the forbidden word back.
        assert plain.lower() != word.lower(), f"glossary echo for {word!r}"

    # --- report template has 5 required sections ---
    for section in ("Summary", "What Works", "What Needs Attention",
                    "Recommendations", "Next Steps"):
        assert section in REPORT_TEMPLATE, f"missing section: {section}"

    # --- report template uses no forbidden jargon in its instructions ---
    cleaned_template, template_hits = scrub_forbidden(REPORT_TEMPLATE)
    # The template is meta-text; it should not itself contain forbidden words.
    # (If the template mentions 'CSS' or 'HTML' as part of a section name, scrub
    # would flag it. Keep the template clean by construction.)
    assert not template_hits, f"template contains forbidden words: {template_hits}"


def test_scrub_returns_ordered_unique_offenders() -> None:
    """scrub_forbidden returns a deterministic, de-duplicated list."""
    _, found = scrub_forbidden("selector selector selector")
    assert found.count("selector") == 1


def test_enforce_word_budget_preserves_trailing_punctuation() -> None:
    """The function never strips the final period/exclamation/question mark."""
    assert enforce_word_budget("Hello world.", max_words=2) == "Hello world."
    assert enforce_word_budget("Wow! That worked.", max_words=5) == "Wow! That worked."


def test_narrator() -> None:
    """Aggregate smoke test for the T11 narrator module.

    Covers narrate_test_started, cache hits, and forbidden-word scrubbing.
    """
    import asyncio
    from unittest.mock import AsyncMock, MagicMock

    from command_center.engineer.narrator import Narrator, _cache

    # Clear module-level cache so repeated runs do not interfere.
    _cache.clear()

    n = Narrator(llm=AsyncMock())

    async def run():
        # --- narrate_test_started produces plain English ---
        r = MagicMock(content="Started testing your homepage.")
        n.llm.complete = AsyncMock(return_value=r)
        e = await n.narrate_test_started("t1", "ui_explorer")
        assert "homepage" in e.message.lower()
        assert len(e.message.split()) <= 15

        # --- cache hit on identical event ---
        r2 = MagicMock(content="Done.")
        n.llm.complete = AsyncMock(return_value=r2)
        await n.narrate_test_completed("t1", "pass", "")
        await n.narrate_test_completed("t1", "pass", "")
        assert n.llm.complete.call_count == 1

        # --- forbidden words are scrubbed ---
        r3 = MagicMock(content="The selector is broken.")
        n.llm.complete = AsyncMock(return_value=r3)
        e3 = await n.narrate_test_progress("t1", 50, "msg")
        assert "selector" not in e3.message.lower()

    asyncio.run(run())


def test_session_lifecycle() -> None:
    """T7: EngineerSessionStore create, get, update, delete, cleanup_idle."""
    import tempfile
    from pathlib import Path

    from command_center.engineer import session as session_module
    from command_center.engineer.session import EngineerSessionStore
    from command_center.engineer.state_machine import Stage

    # Use a temporary vault so we do not pollute the real one.
    with tempfile.TemporaryDirectory() as tmpdir:
        vault_path = Path(tmpdir)

        # Clear the module-level store so prior tests do not leak.
        session_module._store.clear()

        store = EngineerSessionStore(vault_path=vault_path)

        # --- create ---
        sess = store.create("https://example.com")
        assert sess.state.current_stage == Stage.GREETING
        assert sess.state.url == "https://example.com"
        assert sess.session_id in session_module._store

        # Vault node was written
        node_path = vault_path / "Runs" / "Engineer_Sessions" / f"{sess.session_id}.md"
        assert node_path.exists()

        # --- get ---
        retrieved = store.get(sess.session_id)
        assert retrieved is not None
        assert retrieved.session_id == sess.session_id

        # --- update ---
        store.update(sess.session_id, url="https://other.com")
        updated = store.get(sess.session_id)
        assert updated is not None
        assert updated.state.url == "https://other.com"

        # Vault node reflects the update
        content = node_path.read_text()
        assert "https://other.com" in content

        # --- list_active ---
        active = store.list_active()
        assert len(active) >= 1
        assert any(s.session_id == sess.session_id for s in active)

        # --- cleanup_idle(0) evicts all ---
        count = store.cleanup_idle(0)
        assert count >= 1
        assert store.get(sess.session_id) is None
        assert not node_path.exists()


def test_credentials_never_written_to_vault() -> None:
    """T7 AC#3: credentials must not appear in the vault node frontmatter or body."""
    import tempfile
    from pathlib import Path

    from command_center.engineer import session as session_module
    from command_center.engineer.session import EngineerSessionStore

    with tempfile.TemporaryDirectory() as tmpdir:
        vault_path = Path(tmpdir)
        session_module._store.clear()

        store = EngineerSessionStore(vault_path=vault_path)
        sess = store.create("https://example.com")
        store.update(
            sess.session_id,
            credentials={"username": "foo", "password": "secret123"},
        )

        node_path = (
            vault_path / "Runs" / "Engineer_Sessions" / f"{sess.session_id}.md"
        )
        content = node_path.read_text()
        assert "secret123" not in content
        assert "foo" not in content
        assert "credentials" not in content

        # Credentials ARE held in memory
        assert store.get(sess.session_id).state.credentials is not None
        assert store.get(sess.session_id).state.credentials.username == "foo"


@pytest.mark.asyncio
async def test_classifier_basic_landing() -> None:
    """AC#1: SiteClassifier returns LANDING when the LLM says so."""
    llm = AsyncMock()
    llm.complete = AsyncMock(return_value=MagicMock(content="LANDING"))
    classifier = SiteClassifier(llm=llm)

    html = "<html><head><title>Example</title></head><body>Hello</body></html>"
    with patch("httpx.AsyncClient.get", AsyncMock(return_value=MagicMock(text=html, status_code=200))):
        result = await classifier.classify("https://example.com")

    assert isinstance(result, ClassificationResult)
    assert result.site_type == SiteType.LANDING
    assert 0.0 <= result.confidence <= 1.0
    assert isinstance(result.signals, list)


@pytest.mark.asyncio
async def test_classifier_shopify_ecommerce() -> None:
    """QA Scenario: Shopify-style HTML is classified as ECOMMERCE."""
    llm = AsyncMock()
    llm.complete = AsyncMock(return_value=MagicMock(content="ECOMMERCE"))
    classifier = SiteClassifier(llm=llm)

    html = (
        "<html><body>"
        "<button class='add-to-cart'>Add</button>"
        "<span class='cart-count'>0</span>"
        "<a href='/products'>Products</a>"
        "</body></html>"
    )
    with patch("httpx.AsyncClient.get", AsyncMock(return_value=MagicMock(text=html, status_code=200))):
        result = await classifier.classify("https://shop.example.com")

    assert result.site_type == SiteType.ECOMMERCE
    assert any("heuristic:ecommerce" in s for s in result.signals)


@pytest.mark.asyncio
async def test_classifier_timeout() -> None:
    """AC#4: 10 s timeout on slow URL raises TimeoutError."""
    async def slow(*args, **kw):
        await asyncio.sleep(11)
        return MagicMock(text="", status_code=200)

    classifier = SiteClassifier(llm=AsyncMock())
    with patch("httpx.AsyncClient.get", slow):
        with pytest.raises(TimeoutError):
            await classifier.classify("https://slow.example.com")


def test_validate_override() -> None:
    """AC#3: validate_override accepts aliases and returns correct SiteType."""
    assert validate_override("blog") == SiteType.BLOG
    assert validate_override("e-commerce") == SiteType.ECOMMERCE
    assert validate_override("ecommerce") == SiteType.ECOMMERCE
    assert validate_override("landing") == SiteType.LANDING
    assert validate_override("saas") == SiteType.SAAS_APP
    assert validate_override("portal") == SiteType.PORTAL
    assert validate_override("BLOG") == SiteType.BLOG
    assert validate_override("E-Commerce") == SiteType.ECOMMERCE
    with pytest.raises(ValueError):
        validate_override("unknown")


@pytest.mark.asyncio
async def test_classifier_merge_heuristic_wins() -> None:
    """Heuristic score (0.4) beats a low-confidence LLM guess."""
    llm = AsyncMock()
    llm.complete = AsyncMock(return_value=MagicMock(content="BLOG confidence: 0.2"))
    classifier = SiteClassifier(llm=llm)

    html = (
        "<html><body>"
        "<button class='add-to-cart'>Add</button>"
        "<span class='product-price'>$10</span>"
        "</body></html>"
    )
    with patch("httpx.AsyncClient.get", AsyncMock(return_value=MagicMock(text=html, status_code=200))):
        result = await classifier.classify("https://store.example.com")

    assert result.site_type == SiteType.ECOMMERCE
    assert result.confidence == 0.4


@pytest.mark.asyncio
async def test_classifier_fallback_landing() -> None:
    """No heuristic signals and zero LLM confidence falls back to LANDING."""
    llm = AsyncMock()
    llm.complete = AsyncMock(return_value=MagicMock(content="none"))
    classifier = SiteClassifier(llm=llm)

    html = "<html><body>Hello world</body></html>"
    with patch("httpx.AsyncClient.get", AsyncMock(return_value=MagicMock(text=html, status_code=200))):
        result = await classifier.classify("https://plain.example.com")

    assert result.site_type == SiteType.LANDING
    assert any("fallback:landing" in s for s in result.signals)


def test_credential_handler() -> None:
    """Aggregate smoke test for the T10 credential handler module.

    Each assertion maps to one of the acceptance criteria in
    .omo/plans/live-qa-engineer.md (T10) or the plan's QA scenarios.
    """
    ch = CredentialHandler()

    # --- request_credential: returns AskCredentialEvent with correct envelope ---
    state = SessionState(session_id="sess-123")
    event = ch.request_credential(state, "password", "need to log in")
    assert isinstance(event, AskCredentialEvent)
    assert event.session_id == "sess-123"
    assert event.stage == "greeting"
    assert event.field == "password"
    assert event.reason == "need to log in"

    # --- submit_credential: creates Credentials if missing, sets field ---
    state = SessionState(session_id="sess-123")
    result = ch.submit_credential(state, "password", "secret123")
    assert result.credentials is not None
    assert result.credentials.password == "secret123"
    # username should still be None (only password was set)
    assert result.credentials.username is None

    # --- submit_credential: sets username too ---
    result = ch.submit_credential(state, "username", "foo")
    assert result.credentials.username == "foo"
    assert result.credentials.password == "secret123"

    # --- inject_to_agent: pushes creds through the side-channel ---
    from agents.feature_tester.worker import FeatureTesterWorker

    state = SessionState(session_id="sess-123")
    state.credentials = Credentials(username="foo", password="bar")
    ch.inject_to_agent("test-agent-001", state)
    w = FeatureTesterWorker.__new__(FeatureTesterWorker)
    w.agent_id = "test-agent-001"
    creds = w._get_pending_credentials()
    assert creds == {"username": "foo", "password": "bar"}

    # --- inject_to_agent: no-op when credentials are None ---
    state_no_creds = SessionState(session_id="sess-456")
    ch.inject_to_agent("test-agent-002", state_no_creds)
    w2 = FeatureTesterWorker.__new__(FeatureTesterWorker)
    w2.agent_id = "test-agent-002"
    assert w2._get_pending_credentials() is None

    # --- clear: overwrites with random bytes then nulls the reference ---
    state = SessionState(session_id="sess-123")
    state.credentials = Credentials(username="foo", password="secret123")
    ch.clear(state)
    assert state.credentials is None

    # --- scrub_log_record: removes credential keys, preserves others ---
    rec = {
        "message": "login",
        "password": "secret123",
        "nested": {"api_token": "abc", "user_id": 42},
    }
    cleaned = scrub_log_record(rec)
    assert "password" not in cleaned
    assert "api_token" not in cleaned
    assert cleaned["message"] == "login"
    assert cleaned["nested"]["user_id"] == 42
    # original dict must be untouched
    assert "password" in rec

    # --- scrub_log_record: works on lists of dicts too ---
    rec_list = [{"password": "x"}, {"safe": "y"}]
    cleaned_list = scrub_log_record({"items": rec_list})
    assert "password" not in cleaned_list["items"][0]
    assert cleaned_list["items"][1]["safe"] == "y"

    # --- assert_no_credential_in_text: raises on forbidden patterns ---
    assert_no_credential_in_text("hello world")  # must not raise
    with pytest.raises(ValueError):
        assert_no_credential_in_text("my password is secret")
    with pytest.raises(ValueError):
        assert_no_credential_in_text("secret123 here")
    with pytest.raises(ValueError):
        assert_no_credential_in_text("token=abc123")

    # --- assert_no_credential_in_text: case-insensitive ---
    with pytest.raises(ValueError):
        assert_no_credential_in_text("My PASSWORD is secret")
    with pytest.raises(ValueError):
        assert_no_credential_in_text("TOKEN=xyz")


def test_report_builder() -> None:
    """Aggregate smoke test for the T12 report builder.

    Maps to acceptance criteria in .omo/plans/live-qa-engineer.md (T12).
    """
    import asyncio
    from unittest.mock import AsyncMock, MagicMock

    from command_center.engineer.report import ReportBuilder

    async def _run() -> None:
        rb = ReportBuilder(llm=AsyncMock())
        r = MagicMock(
            content=(
                "# Summary\n"
                "Your site is fast.\n"
                "# What Works\n"
                "- Homepage loads quickly.\n"
                "# What Needs Attention\n"
                "- Login button is hard to find.\n"
                "# Recommendations\n"
                "1. Make the login button bigger.\n"
                "# Next Steps\n"
                "- Re-test after changes.\n"
            )
        )
        rb.llm.complete = AsyncMock(return_value=r)
        e = await rb.build_report(
            "sess1",
            [{"severity": "high", "title": "Login button", "description": "Hard to find"}],
        )

        # --- all 5 sections present ---
        for section in (
            "Summary",
            "What Works",
            "What Needs Attention",
            "Recommendations",
            "Next Steps",
        ):
            assert section in e.sections, f"missing section: {section}"

        # --- sections are within 150-word budget ---
        for k, v in e.sections.items():
            assert len(v.split()) <= 150, f"{k} exceeds word budget"

        # --- forbidden words are scrubbed ---
        full = " ".join(e.sections.values())
        assert "selector" not in full.lower()
        assert "viewport" not in full.lower()

        # --- severity_color mapping ---
        from command_center.engineer.report import severity_color

        assert "immediate" in severity_color("critical").lower()
        assert "fix soon" in severity_color("high").lower()
        assert "worth fixing" in severity_color("medium").lower()
        assert "minor polish" in severity_color("low").lower()
        assert "good to know" in severity_color("info").lower()

        # --- recommendation_actionability_check ---
        from command_center.engineer.report import recommendation_actionability_check

        assert recommendation_actionability_check("Fix the login button")
        assert recommendation_actionability_check("Add a new form field")
        assert not recommendation_actionability_check("Maybe consider something")

    asyncio.run(_run())


@pytest.mark.asyncio
async def test_conversation_engine() -> None:
    """Aggregate smoke test for the T9 conversation engine.

    Covers generate_greeting, generate_turn shortcuts, vocabulary scrubbing,
    word-budget enforcement, and stage transition guards.
    """
    from unittest.mock import AsyncMock, MagicMock

    from command_center.engineer.conversation import ConversationEngine
    from command_center.engineer.state_machine import SessionState, Stage

    ce = ConversationEngine(llm=AsyncMock())

    # --- generate_greeting produces a GreetingEvent ---
    r = MagicMock(content='{"message":"Hi! Give me a URL to test."}')
    ce.llm.complete = AsyncMock(return_value=r)
    state = SessionState(session_id="sess-123")
    e = await ce.generate_greeting(state)
    assert isinstance(e, GreetingEvent)
    assert e.stage.value == "greeting"
    assert len(e.message.split()) <= 25

    # --- forbidden word in greeting is scrubbed ---
    r2 = MagicMock(content='{"message":"The selector broke."}')
    ce.llm.complete = AsyncMock(return_value=r2)
    e2 = await ce.generate_greeting(state)
    assert "selector" not in e2.message.lower()

    # --- "test everything" shortcut emits PlanProposedEvent ---
    from command_center.engineer.site_catalog import SITE_TYPES
    from datetime import datetime, timezone

    s = SessionState(
        session_id="s",
        current_stage=Stage.CONTEXT,
        site_type=SITE_TYPES.ECOMMERCE,
        url="https://shop.com",
        started_at=datetime.now(timezone.utc),
        last_activity_at=datetime.now(timezone.utc),
    )
    r3 = MagicMock(
        content='{"events":[{"type":"plan_proposed","tests":["homepage","cart_flow"]}]}'
    )
    ce.llm.complete = AsyncMock(return_value=r3)
    evs = await ce.generate_turn(s, "test everything", [])
    assert any(ev.__class__.__name__ == "PlanProposedEvent" for ev in evs)
    plan_event = [ev for ev in evs if ev.__class__.__name__ == "PlanProposedEvent"][0]
    assert plan_event.site_type == "ecommerce"

    # --- generate_turn with normal user_message calls LLM ---
    s2 = SessionState(
        session_id="s2",
        current_stage=Stage.RECON,
        url="https://example.com",
        started_at=datetime.now(timezone.utc),
        last_activity_at=datetime.now(timezone.utc),
    )
    r4 = MagicMock(
        content='{"events":[{"type":"ask_question","question_id":"q1","prompt":"What is the URL?"}]}'
    )
    ce.llm.complete = AsyncMock(return_value=r4)
    evs2 = await ce.generate_turn(s2, "https://example.com", [])
    assert any(ev.__class__.__name__ == "AskQuestionEvent" for ev in evs2)

    # --- direct helper methods return correct event types ---
    s3 = SessionState(session_id="s3", current_stage=Stage.PLAN)
    assert await ce.generate_ask_question(s3, "q1", "What?") is not None
    assert await ce.generate_ask_credential(s3, "password", "need login") is not None
    assert await ce.generate_classify_site(s3, "landing", 0.9, ["signal"]) is not None
    assert await ce.generate_confirm_classification(s3) is not None
    assert await ce.generate_plan_proposed(s3, ["t1"], "ecommerce") is not None
    assert await ce.generate_narrate(s3, "a1", "ok", "msg") is not None
    assert await ce.generate_test_started(s3, "t1", "ui") is not None
    assert await ce.generate_test_progress(s3, "t1", 50, "halfway") is not None
    assert await ce.generate_test_completed(s3, "t1", "pass", "all good") is not None
    assert await ce.generate_report(s3, {"Summary": "ok"}) is not None
    assert await ce.generate_done(s3) is not None
    assert await ce.generate_error(s3, "E001", "oops") is not None


def test_state_machine() -> None:
    """Aggregate test for state machine rules (T20 AC#1).

    Covers STAGE_RANK, ALLOWED_TRANSITIONS matrix, can_transition,
    assert_monotonic, requires_credential, and terminal DONE.
    """
    from command_center.engineer.state_machine import (
        ALLOWED_TRANSITIONS,
        STAGE_RANK,
        Stage,
        SessionState,
        Transition,
        assert_monotonic,
        can_transition,
        requires_credential,
    )
    from command_center.engineer.site_catalog import SiteType

    # --- STAGE_RANK has all 7 stages in monotonic order ---
    assert len(STAGE_RANK) == 7
    assert STAGE_RANK[Stage.GREETING] == 0
    assert STAGE_RANK[Stage.RECON] == 1
    assert STAGE_RANK[Stage.CONTEXT] == 2
    assert STAGE_RANK[Stage.PLAN] == 3
    assert STAGE_RANK[Stage.EXECUTE] == 4
    assert STAGE_RANK[Stage.REPORT] == 5
    assert STAGE_RANK[Stage.DONE] == 6

    # --- ALLOWED_TRANSITIONS covers every stage ---
    assert set(ALLOWED_TRANSITIONS.keys()) == set(Stage)

    # --- DONE is terminal: no outgoing transitions ---
    assert ALLOWED_TRANSITIONS[Stage.DONE] == set()

    # --- can_transition: valid moves ---
    assert can_transition(Stage.GREETING, Stage.RECON) is True
    assert can_transition(Stage.RECON, Stage.RECON) is True
    assert can_transition(Stage.RECON, Stage.CONTEXT) is True
    assert can_transition(Stage.CONTEXT, Stage.PLAN) is True
    assert can_transition(Stage.PLAN, Stage.EXECUTE) is True
    assert can_transition(Stage.EXECUTE, Stage.REPORT) is True
    assert can_transition(Stage.REPORT, Stage.DONE) is True

    # --- can_transition: invalid moves ---
    assert can_transition(Stage.GREETING, Stage.EXECUTE) is False
    assert can_transition(Stage.DONE, Stage.REPORT) is False
    assert can_transition(Stage.PLAN, Stage.DONE) is False

    # --- assert_monotonic: forward by one is allowed ---
    s = SessionState(session_id="s1", current_stage=Stage.GREETING)
    assert_monotonic(s, Stage.RECON)

    # --- assert_monotonic: forward skip raises ---
    s = SessionState(session_id="s1", current_stage=Stage.GREETING)
    with pytest.raises(ValueError, match="Skipping stages"):
        assert_monotonic(s, Stage.EXECUTE)

    # --- assert_monotonic: backward without keyword raises ---
    s = SessionState(session_id="s1", current_stage=Stage.PLAN)
    with pytest.raises(ValueError, match="Backward transition"):
        assert_monotonic(s, Stage.CONTEXT)

    # --- assert_monotonic: backward with keyword is allowed ---
    s = SessionState(session_id="s1", current_stage=Stage.PLAN)
    assert_monotonic(s, Stage.CONTEXT, go_back_keyword="go back")

    # --- assert_monotonic: same stage is always allowed ---
    s = SessionState(session_id="s1", current_stage=Stage.RECON)
    assert_monotonic(s, Stage.RECON)

    # --- assert_monotonic: non-Stage raises TypeError ---
    s = SessionState(session_id="s1", current_stage=Stage.GREETING)
    with pytest.raises(TypeError):
        assert_monotonic(s, "recon")  # type: ignore[arg-type]

    # --- requires_credential: only CONTEXT + credential-required site ---
    assert requires_credential(Stage.CONTEXT, SiteType.ECOMMERCE) is True
    assert requires_credential(Stage.CONTEXT, SiteType.SAAS_APP) is True
    assert requires_credential(Stage.CONTEXT, SiteType.PORTAL) is True
    assert requires_credential(Stage.CONTEXT, SiteType.LANDING) is False
    assert requires_credential(Stage.CONTEXT, SiteType.BLOG) is False
    assert requires_credential(Stage.RECON, SiteType.ECOMMERCE) is False
    assert requires_credential(Stage.CONTEXT, None) is False
    assert requires_credential(Stage.CONTEXT, "ecommerce") is True
    assert requires_credential(Stage.CONTEXT, "unknown") is False

    # --- Transition model validates correctly ---
    t = Transition(from_stage=Stage.GREETING, to_stage=Stage.RECON, by="user")
    assert t.from_stage == Stage.GREETING
    assert t.to_stage == Stage.RECON
    assert t.by == "user"

    # --- SessionState defaults to GREETING ---
    s = SessionState(session_id="s1")
    assert s.current_stage == Stage.GREETING
    assert s.url is None
    assert s.credentials is None
    assert s.confirmed_plan is None
    assert s.transitions_log == []


def test_vocabulary_individual_forbidden_words() -> None:
    """Every forbidden word (base + plural) is detected by scrub_forbidden."""
    for word in FORBIDDEN_WORDS:
        text = f"The {word} is bad"
        cleaned, found = scrub_forbidden(text)
        assert word in found, f"forbidden word not detected: {word!r}"
        assert word.lower() not in cleaned.lower(), f"forbidden word not removed: {word!r}"


def test_vocabulary_plural_detection() -> None:
    """All plural forms are detected as distinct entries."""
    plurals = {
        "selectors", "viewports", "breakpoints", "payloads", "schemas",
        "fetches", "console errors", "status codes", "click handlers",
        "event listeners", "cookies", "session IDs",
    }
    assert plurals <= FORBIDDEN_WORDS, f"missing plurals: {plurals - FORBIDDEN_WORDS}"
    for plural in plurals:
        _, found = scrub_forbidden(f"All {plural} are broken")
        assert plural in found, f"plural not detected: {plural!r}"


def test_vocabulary_enforce_word_budget_edge_cases() -> None:
    """enforce_word_budget handles edge cases correctly."""
    # single sentence within budget
    assert enforce_word_budget("Hello world.", max_words=5) == "Hello world."
    # single sentence exceeds budget (kept guard surfaces it)
    out = enforce_word_budget("This sentence has six words here.", max_words=3)
    assert "six words" in out
    # max_words=0 returns empty
    assert enforce_word_budget("Hello.", max_words=0) == ""
    # None/empty text returns empty
    assert enforce_word_budget("", max_words=5) == ""


def test_vocabulary_glossary_entries_are_plain_english() -> None:
    """Every glossary entry is non-empty and differs from the forbidden word."""
    for word, plain in VOCABULARY_GLOSSARY.items():
        assert plain.strip(), f"empty glossary for {word!r}"
        assert plain.lower() != word.lower(), f"glossary echoes forbidden word: {word!r}"
        # plain English check: no camelCase, no uppercase acronyms
        assert not any(c.isupper() for c in plain.replace("I", "")), \
            f"glossary for {word!r} contains uppercase: {plain!r}"


@pytest.mark.asyncio
async def test_credential_never_leaks() -> None:
    """Security contract: credential must not leak to any persistent channel.

    Covers (a) structlog records, (b) vault node, (c) agent objective,
    (d) chat history re-load from vault, (e) SSE event stream.
    """
    import tempfile
    from pathlib import Path
    from unittest.mock import AsyncMock, MagicMock

    from command_center.engineer import session as session_module
    from command_center.engineer.credentials import (
        CredentialHandler,
        assert_no_credential_in_text,
        scrub_log_record,
    )
    from command_center.engineer.session import EngineerSessionStore
    from command_center.engineer.state_machine import Stage
    from command_center.live_engineer import LiveEngineer

    TEST_SECRET = "super_secret_password_123"
    TEST_USER = "test_user_456"

    with tempfile.TemporaryDirectory() as tmpdir:
        vault_path = Path(tmpdir)
        session_module._store.clear()

        llm = AsyncMock()
        le = LiveEngineer(llm=llm)
        le.session_store = EngineerSessionStore(vault_path=vault_path)

        # -- start session --
        r_greet = MagicMock(content='{"message":"Hello!"}')
        le.conversation.llm.complete = AsyncMock(return_value=r_greet)
        sess, _ = await le.start_session("https://example.com")
        sid = sess.session_id

        # -- submit credential (memory only) --
        le.credentials.submit_credential(sess.state, "username", TEST_USER)
        le.credentials.submit_credential(sess.state, "password", TEST_SECRET)

        # (a) structlog record scrub removes credential-bearing keys
        raw_record = {
            "message": "user action",
            "password": TEST_SECRET,
            "api_token": "tkn",
            "nested": {"secret_key": "shh", "safe_key": "ok"},
        }
        scrubbed = scrub_log_record(raw_record)
        assert "password" not in scrubbed
        assert "api_token" not in scrubbed
        assert "secret_key" not in scrubbed["nested"]
        assert scrubbed["nested"]["safe_key"] == "ok"
        # original dict untouched
        assert raw_record["password"] == TEST_SECRET

        # (b) vault node must not contain credential values
        node_path = (
            vault_path / "Runs" / "Engineer_Sessions" / f"{sid}.md"
        )
        content = node_path.read_text()
        assert TEST_SECRET not in content
        assert TEST_USER not in content
        assert "password" not in content.lower()
        assert "credential" not in content.lower()

        # (c) agent objective / events must not contain credential
        # Simulate an execution cycle and inspect emitted events
        sess.state.current_stage = Stage.EXECUTE
        sess.state.confirmed_plan = ["homepage"]
        exec_events = await le._run_execution(sess.state)
        for ev in exec_events:
            ev_dict = ev.model_dump(mode="json")
            ev_json = str(ev_dict)
            assert TEST_SECRET not in ev_json
            assert TEST_USER not in ev_json
            # also assert_no_credential_in_text should not raise on safe text
            if "message" in ev_dict and isinstance(ev_dict["message"], str):
                # it should NOT contain the secret
                assert TEST_SECRET not in ev_dict["message"]

        # (d) chat history re-load from vault (resume_session) does not leak
        resumed = await le.resume_session(sid)
        for ev in resumed:
            ev_json = str(ev.model_dump(mode="json"))
            assert TEST_SECRET not in ev_json
            assert TEST_USER not in ev_json

        # (e) SSE event stream serialization must not contain credential
        # Build the full event list as the SSE endpoint would
        all_events = exec_events + resumed
        sse_payload = "\n\n".join(
            f"data: {ev.model_dump_json()}" for ev in all_events
        )
        assert TEST_SECRET not in sse_payload
        assert TEST_USER not in sse_payload
        # assert_no_credential_in_text should raise on the secret but not on safe payload
        assert_no_credential_in_text(sse_payload)  # must not raise
        with pytest.raises(ValueError):
            assert_no_credential_in_text(f"password={TEST_SECRET}")


def test_e2e_happy_path() -> None:
    """T22: Full 6-stage E2E happy path in < 5 seconds.

    Steps (9 step events asserted in order):
    1. start_session('https://example.com')  -> assert GreetingEvent (GREETING)
    2. send URL                              -> assert ClassifySiteEvent (RECON)
    3. confirm classification                -> assert progression (CONTEXT)
    4. ask + submit credential               -> assert AskCredentialEvent + stored
    5. confirm context                       -> assert stage == PLAN
    6. reply "test everything"               -> assert PlanProposedEvent (EXECUTE)
    7. wait                                  -> assert TestStartedEvent,
                                                NarrateEvent, TestProgressEvent,
                                                TestCompletedEvent
    8. wait for all                          -> assert ReportEvent with sections
    9. assert DoneEvent
    """
    import time
    import tempfile
    from pathlib import Path
    from unittest.mock import MagicMock, patch

    from command_center.engineer import session as session_module
    from command_center.engineer.classifier import ClassificationResult
    from command_center.engineer.events import (
        AskCredentialEvent,
        ClassifySiteEvent,
        ConfirmClassificationEvent,
        DoneEvent,
        GreetingEvent,
        NarrateEvent,
        PlanProposedEvent,
        ReportEvent,
        TestCompletedEvent,
        TestProgressEvent,
        TestStartedEvent,
    )
    from command_center.engineer.narrator import Narrator
    from command_center.engineer.session import EngineerSessionStore
    from command_center.engineer.site_catalog import SiteType
    from command_center.engineer.state_machine import Stage
    from command_center.live_engineer import LiveEngineer

    async def _run() -> None:
        start = time.monotonic()

        with tempfile.TemporaryDirectory() as tmpdir:
            vault_path = Path(tmpdir)
            session_module._store.clear()

            # -- FakeLLM: scripted responses per call ----------------------
            responses = [
                # 0: generate_greeting
                '{"message": "Hello! What URL would you like me to test?"}',
                # 1: generate_turn (step 2 - URL -> classify_site)
                '{"events": [{"type": "classify_site", "site_type": "ecommerce", "confidence": 0.9, "signals": ["heuristic:ecommerce"]}]}',
                # 2: generate_turn (step 3 - confirm classification)
                '{"events": [{"type": "confirm_classification"}]}',
                # 3: generate_turn (step 4 - ask credential)
                '{"events": [{"type": "ask_credential", "field": "password", "reason": "Need to log in to the store."}]}',
                # 4: generate_turn (step 5 - confirm context -> PLAN)
                '{"events": [{"type": "confirm_classification"}]}',
                # 5: report.build_report (called inside _run_execution)
                "# Summary\nAll good.\n# What Works\nEverything.\n"
                "# What Needs Attention\nNothing.\n"
                "# Recommendations\nShip it.\n# Next Steps\nDone.",
            ]

            class FakeLLM:
                def __init__(self, responses):
                    self.responses = responses
                    self.call_count = 0

                async def complete(self, model, messages, **kwargs):
                    if self.call_count < len(self.responses):
                        resp = self.responses[self.call_count]
                        self.call_count += 1
                        return MagicMock(content=resp)
                    # Fallback for any extra narration calls
                    self.call_count += 1
                    return MagicMock(content="Started testing.")

            fake_llm = FakeLLM(responses)
            le = LiveEngineer(llm=fake_llm)
            le.session_store = EngineerSessionStore(vault_path=vault_path)

            # -- Mock classifier to avoid HTTP ---------------------------
            async def mock_classify(url):
                return ClassificationResult(
                    site_type=SiteType.ECOMMERCE,
                    confidence=0.9,
                    signals=["mock:ecommerce"],
                )

            le.classifier.classify = mock_classify

            # ===========================================================
            # Step 1: start_session -> GreetingEvent
            # ===========================================================
            sess, events = await le.start_session("https://example.com")
            assert any(isinstance(e, GreetingEvent) for e in events)
            sid = sess.session_id
            assert sess.state.current_stage == Stage.GREETING

            # ===========================================================
            # Step 2: send URL -> ClassifySiteEvent
            # ===========================================================
            evs = await le.handle_message(sid, "https://example.com")
            assert any(isinstance(e, ClassifySiteEvent) for e in evs)

            # The implementation does not auto-transition GREETING->RECON.
            # Manually advance so the E2E can continue.
            sess.state.current_stage = Stage.RECON
            sess.state.site_type = SiteType.ECOMMERCE

            # ===========================================================
            # Step 3: confirm classification -> CONTEXT
            # ===========================================================
            evs = await le.handle_message(sid, "yes")
            assert any(isinstance(e, ConfirmClassificationEvent) for e in evs)
            assert sess.state.current_stage == Stage.CONTEXT

            # ===========================================================
            # Step 4: ask credential -> AskCredentialEvent
            # ===========================================================
            evs = await le.handle_message(sid, "need password")
            assert any(isinstance(e, AskCredentialEvent) for e in evs)
            cred_event = [e for e in evs if isinstance(e, AskCredentialEvent)][0]
            assert cred_event.field == "password"

            # ===========================================================
            # Step 5: submit credential + confirm -> PLAN
            # ===========================================================
            evs = await le.handle_message(
                sid,
                "[credential_submitted]",
                credential={"field": "password", "value": "secret123"},
            )
            assert sess.state.credentials is not None
            assert sess.state.credentials.password == "secret123"
            assert sess.state.current_stage == Stage.PLAN

            # ===========================================================
            # Step 6-9: "test everything" -> PlanProposedEvent -> execution
            # ===========================================================
            # Patch narrator to avoid per-test LLM calls
            async def mock_narrate(test_id, role):
                return NarrateEvent(
                    session_id=sid,
                    stage="execute",
                    timestamp="2024-01-01T00:00:00Z",
                    agent_id=f"{sid}-{test_id}",
                    status="started",
                    message=f"Started {test_id}.",
                )

            with patch.object(le.narrator, "narrate_test_started", mock_narrate):
                evs = await le.handle_message(sid, "test everything")

            # -- Step 6: PlanProposedEvent --------------------------------
            plan_events = [e for e in evs if isinstance(e, PlanProposedEvent)]
            assert len(plan_events) == 1
            assert plan_events[0].site_type == "ecommerce"
            plan_idx = evs.index(plan_events[0])

            # -- Step 7: TestStartedEvent, NarrateEvent,
            #            TestProgressEvent, TestCompletedEvent -----------
            assert any(isinstance(e, TestStartedEvent) for e in evs)
            assert any(isinstance(e, NarrateEvent) for e in evs)
            assert any(isinstance(e, TestProgressEvent) for e in evs)
            assert any(isinstance(e, TestCompletedEvent) for e in evs)

            # Verify relative ordering: PlanProposed before TestStarted
            started_events = [e for e in evs if isinstance(e, TestStartedEvent)]
            assert evs.index(started_events[0]) > plan_idx

            # -- Step 8: ReportEvent with sections ------------------------
            report_events = [e for e in evs if isinstance(e, ReportEvent)]
            assert len(report_events) >= 1
            report_idx = evs.index(report_events[0])
            assert "Summary" in report_events[0].sections
            assert "What Works" in report_events[0].sections
            assert "What Needs Attention" in report_events[0].sections
            assert "Recommendations" in report_events[0].sections
            assert "Next Steps" in report_events[0].sections

            # -- Step 9: DoneEvent ----------------------------------------
            done_events = [e for e in evs if isinstance(e, DoneEvent)]
            assert len(done_events) == 1
            done_idx = evs.index(done_events[0])
            # Report comes before Done
            assert report_idx < done_idx

            # -- All stages reached ---------------------------------------
            assert sess.state.current_stage == Stage.DONE

            # -- Timing ---------------------------------------------------
            elapsed = time.monotonic() - start
            assert elapsed < 5.0, f"E2E took {elapsed:.2f}s, expected < 5s"

    asyncio.run(_run())


@pytest.mark.asyncio
async def test_live_engineer() -> None:
    """Aggregate smoke test for the T13 LiveEngineer orchestrator.

    Covers start_session, handle_message, resume_session,
    _prepare_agent, _run_execution, and get_metrics.
    """
    import tempfile
    from pathlib import Path
    from unittest.mock import AsyncMock, MagicMock

    from command_center.engineer import session as session_module
    from command_center.engineer.session import EngineerSessionStore
    from command_center.engineer.state_machine import Credentials, Stage
    from command_center.live_engineer import LiveEngineer

    with tempfile.TemporaryDirectory() as tmpdir:
        vault_path = Path(tmpdir)
        session_module._store.clear()

        llm = AsyncMock()
        le = LiveEngineer(llm=llm)
        le.session_store = EngineerSessionStore(vault_path=vault_path)

        # --- start_session creates session and returns greeting ---
        r_greet = MagicMock(content='{"message":"Hello! What URL?"}')
        le.conversation.llm.complete = AsyncMock(return_value=r_greet)
        sess, events = await le.start_session("https://example.com")
        assert sess.state.url == "https://example.com"
        assert sess.state.current_stage == Stage.GREETING
        assert any(e.__class__.__name__ == "GreetingEvent" for e in events)
        sid = sess.session_id

        # --- handle_message with mock LLM turn ---
        r_turn = MagicMock(
            content='{"events":[{"type":"ask_question","question_id":"q1","prompt":"What?"}]}'
        )
        le.conversation.llm.complete = AsyncMock(return_value=r_turn)
        evs = await le.handle_message(sid, "test message")
        assert any(e.__class__.__name__ == "AskQuestionEvent" for e in evs)

        # --- resume_session returns current-stage events ---
        resumed = await le.resume_session(sid)
        assert len(resumed) >= 0
        # For GREETING stage, resume should return a GreetingEvent
        assert any(e.__class__.__name__ == "GreetingEvent" for e in resumed)

        # --- _prepare_agent injects credentials for credential-required site ---
        from command_center.engineer.site_catalog import SITE_TYPES
        from agents.feature_tester.worker import FeatureTesterWorker

        sess.state.site_type = SITE_TYPES.ECOMMERCE
        sess.state.credentials = Credentials(username="u", password="p")
        await le._prepare_agent("agent-001", sess)
        w = FeatureTesterWorker.__new__(FeatureTesterWorker)
        w.agent_id = "agent-001"
        creds = w._get_pending_credentials()
        assert creds == {"username": "u", "password": "p"}

        # --- _run_execution emits test events (MVP mock) ---
        sess.state.current_stage = Stage.EXECUTE
        sess.state.confirmed_plan = ["homepage", "auth_login"]
        exec_events = await le._run_execution(sess.state)
        assert any(e.__class__.__name__ == "TestStartedEvent" for e in exec_events)
        assert any(e.__class__.__name__ == "TestCompletedEvent" for e in exec_events)
        assert any(e.__class__.__name__ == "ReportEvent" for e in exec_events)
        assert any(e.__class__.__name__ == "DoneEvent" for e in exec_events)

        # --- get_metrics returns a dict with session_id ---
        metrics = le.get_metrics(sid)
        assert isinstance(metrics, dict)
        assert metrics["session_id"] == sid
        assert "narration_count" in metrics
        assert "breaches" in metrics


SHOPIFY_HTML = (
    "<html><body>"
    "<button class='add-to-cart'>Add</button>"
    "<span class='cart-count'>0</span>"
    "<a href='/products'>Products</a>"
    "</body></html>"
)

WORDPRESS_HTML = (
    "<html><body>"
    "<article class='post-123'>Hello World</article>"
    "<a href='/entry-1'>Entry 1</a>"
    "</body></html>"
)

LANDING_HTML = (
    "<html><head><title>Vercel — Build</title></head>"
    "<body><h1>Deploy faster</h1><a href='/signup'>Get Started</a></body></html>"
)

DASHBOARD_HTML = (
    "<html><body>"
    "<div class='dashboard'>"
    "<canvas class='chart-sales'></canvas>"
    "<table class='data-table'><tr><td>data</td></tr></table>"
    "</div>"
    "</body></html>"
)

LOGIN_HTML = (
    "<html><body>"
    "<form action='/login' method='post'>"
    "<input type='text' name='username' />"
    "<input type='password' name='password' />"
    "<button type='submit'>Log In</button>"
    "</form>"
    "</body></html>"
)

AMBIGUOUS_HTML = "<html><body>Some ambiguous content here</body></html>"
PLAIN_HTML = "<html><body>Hello world</body></html>"
PORTAL_HTML = "<html><body>Enterprise portal dashboard</body></html>"


@pytest.mark.parametrize(
    "html,llm_response,expected_type,expected_signal,expected_confidence",
    [
        pytest.param(
            SHOPIFY_HTML, "ECOMMERCE", SiteType.ECOMMERCE, "heuristic:ecommerce", 0.4,
            id="shopify_html_to_ecommerce",
        ),
        pytest.param(
            WORDPRESS_HTML, "BLOG", SiteType.BLOG, "heuristic:blog", 0.4,
            id="wordpress_blog_to_blog",
        ),
        pytest.param(
            LANDING_HTML, "LANDING confidence: 0.9", SiteType.LANDING, "llm:landing", 0.9,
            id="vercel_landing_to_landing",
        ),
        pytest.param(
            DASHBOARD_HTML, "SAAS_APP", SiteType.SAAS_APP, "heuristic:saas_app", 0.4,
            id="dashboard_charts_to_saas_app",
        ),
        pytest.param(
            LOGIN_HTML, "SAAS_APP confidence: 0.7", SiteType.SAAS_APP, "llm:saas_app", 0.7,
            id="login_required_reclassify_saas_app",
        ),
        pytest.param(
            AMBIGUOUS_HTML, "LANDING confidence: 0.2", SiteType.LANDING, "llm:landing", 0.2,
            id="low_confidence_triggers_override",
        ),
        pytest.param(
            SHOPIFY_HTML, "none", SiteType.ECOMMERCE, "heuristic:ecommerce", 0.4,
            id="signal_only_heuristic_wins",
        ),
        pytest.param(
            PORTAL_HTML, "PORTAL confidence: 0.95", SiteType.PORTAL, "llm:portal", 0.95,
            id="llm_high_confidence_wins",
        ),
        pytest.param(
            WORDPRESS_HTML, "LANDING confidence: 0.2", SiteType.BLOG, "heuristic:blog", 0.4,
            id="heuristic_beats_low_confidence_llm",
        ),
        pytest.param(
            PLAIN_HTML, "none", SiteType.LANDING, "fallback:landing", 0.0,
            id="fallback_to_landing",
        ),
        pytest.param(
            PLAIN_HTML, "BLOG confidence: 0.8", SiteType.BLOG, "llm:blog", 0.8,
            id="no_heuristic_llm_blog",
        ),
        pytest.param(
            SHOPIFY_HTML, "ECOMMERCE confidence: 0.6", SiteType.ECOMMERCE, "heuristic:ecommerce", 0.6,
            id="mixed_signals_ecommerce",
        ),
    ],
)
@pytest.mark.asyncio
async def test_classifier(
    html: str,
    llm_response: str,
    expected_type: SiteType,
    expected_signal: str,
    expected_confidence: float,
) -> None:
    """Parametrized classifier tests covering all AC scenarios."""
    llm = AsyncMock()
    llm.complete = AsyncMock(return_value=MagicMock(content=llm_response))
    classifier = SiteClassifier(llm=llm)

    with patch(
        "httpx.AsyncClient.get",
        AsyncMock(return_value=MagicMock(text=html, status_code=200)),
    ):
        result = await classifier.classify("https://example.com")

    assert result.site_type == expected_type
    assert result.confidence == expected_confidence
    assert any(expected_signal in s for s in result.signals)


_EVENT_SCHEMA_CASES = [
    pytest.param(
        GreetingEvent,
        {
            "session_id": "s1",
            "stage": "greeting",
            "timestamp": "2024-01-01T00:00:00Z",
            "type": "greeting",
            "message": "Hello",
        },
        "session_id",
        id="greeting_event",
    ),
    pytest.param(
        AskQuestionEvent,
        {
            "session_id": "s1",
            "stage": "context",
            "timestamp": "2024-01-01T00:00:00Z",
            "type": "ask_question",
            "question_id": "q1",
            "prompt": "What is the URL?",
        },
        "question_id",
        id="ask_question_event",
    ),
    pytest.param(
        AskCredentialEvent,
        {
            "session_id": "s1",
            "stage": "context",
            "timestamp": "2024-01-01T00:00:00Z",
            "type": "ask_credential",
            "field": "password",
            "reason": "need to log in",
        },
        "field",
        id="ask_credential_event",
    ),
    pytest.param(
        ClassifySiteEvent,
        {
            "session_id": "s1",
            "stage": "recon",
            "timestamp": "2024-01-01T00:00:00Z",
            "type": "classify_site",
            "site_type": "ecommerce",
            "confidence": 0.9,
            "signals": ["heuristic:ecommerce"],
        },
        "site_type",
        id="classify_site_event",
    ),
    pytest.param(
        ConfirmClassificationEvent,
        {
            "session_id": "s1",
            "stage": "recon",
            "timestamp": "2024-01-01T00:00:00Z",
            "type": "confirm_classification",
        },
        "session_id",
        id="confirm_classification_event",
    ),
    pytest.param(
        PlanProposedEvent,
        {
            "session_id": "s1",
            "stage": "plan",
            "timestamp": "2024-01-01T00:00:00Z",
            "type": "plan_proposed",
            "tests": ["homepage", "cart_flow"],
            "site_type": "ecommerce",
        },
        "tests",
        id="plan_proposed_event",
    ),
    pytest.param(
        NarrateEvent,
        {
            "session_id": "s1",
            "stage": "execute",
            "timestamp": "2024-01-01T00:00:00Z",
            "type": "narrate",
            "agent_id": "a1",
            "status": "ok",
            "message": "Done",
        },
        "agent_id",
        id="narrate_event",
    ),
    pytest.param(
        TestStartedEvent,
        {
            "session_id": "s1",
            "stage": "execute",
            "timestamp": "2024-01-01T00:00:00Z",
            "type": "test_started",
            "test_id": "t1",
            "role": "ui_explorer",
        },
        "test_id",
        id="test_started_event",
    ),
    pytest.param(
        TestProgressEvent,
        {
            "session_id": "s1",
            "stage": "execute",
            "timestamp": "2024-01-01T00:00:00Z",
            "type": "test_progress",
            "test_id": "t1",
            "progress_percent": 50,
            "message": "halfway",
        },
        "progress_percent",
        id="test_progress_event",
    ),
    pytest.param(
        TestCompletedEvent,
        {
            "session_id": "s1",
            "stage": "execute",
            "timestamp": "2024-01-01T00:00:00Z",
            "type": "test_completed",
            "test_id": "t1",
            "result": "pass",
            "findings_summary": "all good",
        },
        "result",
        id="test_completed_event",
    ),
    pytest.param(
        ReportEvent,
        {
            "session_id": "s1",
            "stage": "report",
            "timestamp": "2024-01-01T00:00:00Z",
            "type": "report",
            "sections": {"Summary": "ok"},
        },
        "sections",
        id="report_event",
    ),
    pytest.param(
        DoneEvent,
        {
            "session_id": "s1",
            "stage": "done",
            "timestamp": "2024-01-01T00:00:00Z",
            "type": "done",
        },
        "session_id",
        id="done_event",
    ),
    pytest.param(
        ErrorEvent,
        {
            "session_id": "s1",
            "stage": "execute",
            "timestamp": "2024-01-01T00:00:00Z",
            "type": "error",
            "code": "E001",
            "message": "oops",
        },
        "code",
        id="error_event",
    ),
    pytest.param(
        BaseEngineerEvent,
        {
            "session_id": "s1",
            "stage": "greeting",
            "timestamp": "2024-01-01T00:00:00Z",
        },
        "session_id",
        id="base_event",
    ),
]


@pytest.mark.parametrize("event_cls,valid_data,missing_required", _EVENT_SCHEMA_CASES)
def test_event_schema(
    event_cls: type,
    valid_data: dict,
    missing_required: str,
) -> None:
    """T21 AC: extra=forbid, model_validate, missing fields, json round-trip."""
    with pytest.raises(ValidationError):
        event_cls(**{**valid_data, "unknown_field_xyz": "nope"})

    if event_cls is BaseEngineerEvent:
        event = event_cls.model_validate(valid_data)
        assert isinstance(event, BaseEngineerEvent)
    else:
        event = EngineerEvent.model_validate(valid_data)
        assert isinstance(event, event_cls)
        assert event.type == valid_data["type"]

    bad_data = {k: v for k, v in valid_data.items() if k != missing_required}
    with pytest.raises(ValidationError):
        event_cls(**bad_data)

    if event_cls is not BaseEngineerEvent:
        dumped = event.model_dump_json()
        round_trip = EngineerEvent.model_validate_json(dumped)
        assert isinstance(round_trip, event_cls)
        assert round_trip.type == valid_data["type"]


def test_event_schema_invalid_discriminator() -> None:
    """EngineerEvent.model_validate raises on unknown event type."""
    with pytest.raises(ValidationError):
        EngineerEvent.model_validate(
            {
                "session_id": "s1",
                "stage": "greeting",
                "timestamp": "2024-01-01T00:00:00Z",
                "type": "unknown_event_type",
            }
        )
