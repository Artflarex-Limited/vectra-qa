"""Unit tests for command_center.engineer modules (T4 vocabulary, T8 classifier).

Covers FORBIDDEN_WORDS shape, scrub_forbidden detection + cleaning,
enforce_word_budget sentence-boundary truncation, glossary completeness,
the 5-section report template, and the SiteClassifier heuristic + LLM flow.
"""
from __future__ import annotations

import asyncio

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
from command_center.engineer.events import AskCredentialEvent, GreetingEvent
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
