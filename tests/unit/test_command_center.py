"""Unit tests for the Command Center engineer modules.

Covers: session lifecycle, state machine transitions, vocabulary scrub,
credential scrubbing, classifier signals, narrator word budget,
report builder sections, metrics recording, event schema validation,
and LiveEngineer flow.
"""

import os
import tempfile
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Set OBSIDIAN_VAULT_PATH to a writable temp location before importing
# command_center modules.  EngineerSessionStore creates vault directories
# on instantiation, so we must redirect the vault path first.
# ---------------------------------------------------------------------------
_VAULT_TMPDIR = tempfile.mkdtemp(prefix="vectra_test_vault_engineer_")
os.environ["OBSIDIAN_VAULT_PATH"] = _VAULT_TMPDIR

from command_center.engineer.events import (  # noqa: E402
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
from command_center.engineer.site_catalog import (  # noqa: E402
    CREDENTIAL_REQUIRED,
    SITE_TYPES,
    SITE_TYPE_DESCRIPTIONS,
    TEST_CATALOG,
    SiteType,
    get_default_plan,
)
from command_center.engineer.state_machine import (  # noqa: E402
    Credentials,
    SessionState,
    Stage,
    Transition,
    assert_monotonic,
    can_transition,
    requires_credential,
)
from command_center.engineer.vocabulary import (  # noqa: E402
    FORBIDDEN_WORDS,
    REPORT_TEMPLATE,
    VOCABULARY_GLOSSARY,
    enforce_word_budget,
    scrub_forbidden,
)
from command_center.engineer.metrics import MetricsConfig, MetricsRecorder  # noqa: E402
from command_center.engineer.session import EngineerSessionStore  # noqa: E402
from command_center.engineer.classifier import (  # noqa: E402
    ClassificationResult,
    SiteClassifier,
    validate_override,
)
from command_center.engineer.conversation import ConversationEngine  # noqa: E402
from command_center.engineer.credentials import (  # noqa: E402
    CredentialHandler,
    assert_no_credential_in_text,
    scrub_log_record,
)
from command_center.engineer.narrator import Narrator  # noqa: E402
from command_center.engineer.report import (  # noqa: E402
    ReportBuilder,
    recommendation_actionability_check,
    severity_color,
)
from command_center.live_engineer import LiveEngineer  # noqa: E402


# =========================================================================
# Fixtures
# =========================================================================


@pytest.fixture
def tmp_vault(tmp_path):
    """Return a temporary vault path and clear the module store."""
    from command_center.engineer import session as session_module

    session_module._store.clear()
    return tmp_path


@pytest.fixture
def session_store(tmp_vault):
    """Return an EngineerSessionStore backed by a temp vault."""
    return EngineerSessionStore(vault_path=tmp_vault)


@pytest.fixture
def sample_state():
    """Return a basic SessionState for testing."""
    return SessionState(session_id="test-session-001")


# =========================================================================
# Event schema validation
# =========================================================================


class TestEvents:
    """Tests for EngineerEvent schema validation."""

    @pytest.mark.unit
    def test_greeting_event_serializes(self):
        """GreetingEvent should serialize to dict with correct type."""
        ev = GreetingEvent(
            session_id="s1", stage=Stage.GREETING, timestamp="2024-01-01T00:00:00Z", message="Hello"
        )
        d = ev.model_dump()
        assert d["type"] == "greeting"
        assert d["message"] == "Hello"
        assert d["stage"] == "greeting"

    @pytest.mark.unit
    def test_plan_proposed_event_fields(self):
        """PlanProposedEvent should carry tests and site_type."""
        ev = PlanProposedEvent(
            session_id="s1",
            stage=Stage.PLAN,
            timestamp="2024-01-01T00:00:00Z",
            tests=["homepage", "auth_login"],
            site_type="ecommerce",
        )
        assert ev.tests == ["homepage", "auth_login"]
        assert ev.site_type == "ecommerce"

    @pytest.mark.unit
    def test_engineer_event_discriminated_union(self):
        """EngineerEvent.model_validate should route to correct subclass."""
        raw = {
            "type": "error",
            "session_id": "s1",
            "stage": "greeting",
            "timestamp": "2024-01-01T00:00:00Z",
            "code": "E001",
            "message": "Something went wrong",
        }
        ev = EngineerEvent.model_validate(raw)
        assert isinstance(ev, ErrorEvent)
        assert ev.code == "E001"

    @pytest.mark.unit
    def test_all_event_types_instantiate(self):
        """Every concrete event class should instantiate without error."""
        ts = "2024-01-01T00:00:00Z"
        base = {"session_id": "s1", "stage": Stage.GREETING, "timestamp": ts}
        assert isinstance(GreetingEvent(message="hi", **base), GreetingEvent)
        assert isinstance(AskQuestionEvent(question_id="q1", prompt="What?", **base), AskQuestionEvent)
        assert isinstance(AskCredentialEvent(field="password", reason="login", **base), AskCredentialEvent)
        assert isinstance(ClassifySiteEvent(site_type="landing", confidence=0.9, signals=["s"], **base), ClassifySiteEvent)
        assert isinstance(ConfirmClassificationEvent(**base), ConfirmClassificationEvent)
        assert isinstance(PlanProposedEvent(tests=["t1"], site_type="landing", **base), PlanProposedEvent)
        assert isinstance(NarrateEvent(agent_id="a1", status="ok", message="m", **base), NarrateEvent)
        assert isinstance(TestStartedEvent(test_id="t1", role="ui_explorer", **base), TestStartedEvent)
        assert isinstance(TestProgressEvent(test_id="t1", progress_percent=50, message="m", **base), TestProgressEvent)
        assert isinstance(TestCompletedEvent(test_id="t1", result="pass", findings_summary="ok", **base), TestCompletedEvent)
        assert isinstance(ReportEvent(sections={"Summary": "ok"}, **base), ReportEvent)
        assert isinstance(DoneEvent(**base), DoneEvent)
        assert isinstance(ErrorEvent(code="E", message="m", **base), ErrorEvent)


# =========================================================================
# Site catalog
# =========================================================================


class TestSiteCatalog:
    """Tests for site_catalog module."""

    @pytest.mark.unit
    def test_site_types_enum_values(self):
        """SITE_TYPES members should have expected string values."""
        assert SITE_TYPES.LANDING == "landing"
        assert SITE_TYPES.ECOMMERCE == "ecommerce"
        assert SITE_TYPES.BLOG == "blog"
        assert SITE_TYPES.SAAS_APP == "saas_app"
        assert SITE_TYPES.PORTAL == "portal"

    @pytest.mark.unit
    def test_test_catalog_exhaustive(self):
        """Every SiteType must have a non-empty test plan."""
        for st in SiteType:
            assert st in TEST_CATALOG
            assert len(TEST_CATALOG[st]) > 0
            assert len(set(TEST_CATALOG[st])) == len(TEST_CATALOG[st])

    @pytest.mark.unit
    def test_credential_required_set(self):
        """ECOMMERCE, SAAS_APP, PORTAL require credentials."""
        assert SiteType.ECOMMERCE in CREDENTIAL_REQUIRED
        assert SiteType.SAAS_APP in CREDENTIAL_REQUIRED
        assert SiteType.PORTAL in CREDENTIAL_REQUIRED
        assert SiteType.LANDING not in CREDENTIAL_REQUIRED
        assert SiteType.BLOG not in CREDENTIAL_REQUIRED

    @pytest.mark.unit
    def test_get_default_plan_returns_copy(self):
        """get_default_plan should return a mutable copy."""
        plan = get_default_plan("ecommerce")
        original = TEST_CATALOG[SiteType.ECOMMERCE]
        assert plan == original
        plan.pop()
        assert TEST_CATALOG[SiteType.ECOMMERCE] == original  # unchanged

    @pytest.mark.unit
    def test_site_type_descriptions_present(self):
        """Every SiteType must have a plain-English description."""
        for st in SiteType:
            assert st in SITE_TYPE_DESCRIPTIONS
            assert len(SITE_TYPE_DESCRIPTIONS[st]) > 10


# =========================================================================
# State machine
# =========================================================================


class TestStateMachine:
    """Tests for state_machine transitions and guards."""

    @pytest.mark.unit
    def test_can_transition_allowed(self):
        """can_transition should return True for allowed moves."""
        assert can_transition(Stage.GREETING, Stage.RECON) is True
        assert can_transition(Stage.RECON, Stage.CONTEXT) is True
        assert can_transition(Stage.CONTEXT, Stage.PLAN) is True
        assert can_transition(Stage.PLAN, Stage.EXECUTE) is True
        assert can_transition(Stage.EXECUTE, Stage.REPORT) is True
        assert can_transition(Stage.REPORT, Stage.DONE) is True

    @pytest.mark.unit
    def test_can_transition_disallowed(self):
        """can_transition should return False for illegal moves."""
        assert can_transition(Stage.GREETING, Stage.EXECUTE) is False
        assert can_transition(Stage.DONE, Stage.REPORT) is False
        assert can_transition(Stage.EXECUTE, Stage.GREETING) is False

    @pytest.mark.unit
    def test_assert_monotonic_forward_ok(self, sample_state):
        """Single-step forward transitions should succeed."""
        sample_state.current_stage = Stage.GREETING
        assert_monotonic(sample_state, Stage.RECON)
        sample_state.current_stage = Stage.RECON
        assert_monotonic(sample_state, Stage.CONTEXT)

    @pytest.mark.unit
    def test_assert_monotonic_skip_raises(self, sample_state):
        """Skipping stages should raise ValueError."""
        sample_state.current_stage = Stage.GREETING
        with pytest.raises(ValueError, match="Skipping stages"):
            assert_monotonic(sample_state, Stage.PLAN)

    @pytest.mark.unit
    def test_assert_monotonic_backward_requires_keyword(self, sample_state):
        """Backward transitions require go_back_keyword."""
        sample_state.current_stage = Stage.PLAN
        with pytest.raises(ValueError, match="Backward transition"):
            assert_monotonic(sample_state, Stage.CONTEXT)
        # With keyword, should pass
        assert_monotonic(sample_state, Stage.CONTEXT, go_back_keyword="go back")

    @pytest.mark.unit
    def test_assert_monotonic_self_transition_ok(self, sample_state):
        """Same-stage transitions should always be allowed."""
        sample_state.current_stage = Stage.RECON
        assert_monotonic(sample_state, Stage.RECON)

    @pytest.mark.unit
    def test_requires_credential_only_context(self):
        """Credentials are required only at CONTEXT stage."""
        assert requires_credential(Stage.CONTEXT, SiteType.ECOMMERCE) is True
        assert requires_credential(Stage.CONTEXT, SiteType.LANDING) is False
        assert requires_credential(Stage.PLAN, SiteType.ECOMMERCE) is False
        assert requires_credential(Stage.CONTEXT, None) is False

    @pytest.mark.unit
    def test_credentials_model(self):
        """Credentials should hold username and password."""
        c = Credentials(username="foo", password="bar")
        assert c.username == "foo"
        assert c.password == "bar"

    @pytest.mark.unit
    def test_transition_model(self):
        """Transition should record from_stage, to_stage, by."""
        t = Transition(from_stage=Stage.GREETING, to_stage=Stage.RECON, by="user")
        assert t.from_stage == Stage.GREETING
        assert t.to_stage == Stage.RECON
        assert t.by == "user"


# =========================================================================
# Vocabulary
# =========================================================================


class TestVocabulary:
    """Tests for vocabulary scrubbing and word budgets."""

    @pytest.mark.unit
    def test_forbidden_words_present(self):
        """FORBIDDEN_WORDS should contain expected jargon."""
        assert "selector" in FORBIDDEN_WORDS
        assert "DOM" in FORBIDDEN_WORDS
        assert "JWT" in FORBIDDEN_WORDS
        assert "console error" in FORBIDDEN_WORDS
        assert "selectors" in FORBIDDEN_WORDS  # plural

    @pytest.mark.unit
    def test_scrub_forbidden_detects_and_removes(self):
        """scrub_forbidden should detect and remove forbidden words."""
        cleaned, found = scrub_forbidden("The selector is broken")
        assert "selector" in found
        assert "selector" not in cleaned.lower()

    @pytest.mark.unit
    def test_scrub_forbidden_case_insensitive(self):
        """scrub_forbidden should be case-insensitive."""
        cleaned, found = scrub_forbidden("The DOM was wrong and the JWT failed")
        assert any(f.upper() == "DOM" for f in found)
        assert any(f.upper() == "JWT" for f in found)

    @pytest.mark.unit
    def test_enforce_word_budget_truncates_at_sentence(self):
        """enforce_word_budget should never break a sentence mid-way."""
        text = "First sentence. Second sentence. Third sentence."
        result = enforce_word_budget(text, max_words=2)
        assert result == "First sentence."

    @pytest.mark.unit
    def test_enforce_word_budget_no_truncate_when_within_budget(self):
        """enforce_word_budget should preserve text within budget."""
        text = "Just one sentence."
        result = enforce_word_budget(text, max_words=10)
        assert result == "Just one sentence."

    @pytest.mark.unit
    def test_glossary_covers_all_forbidden_words(self):
        """Every forbidden word must have a glossary entry."""
        missing = FORBIDDEN_WORDS - set(VOCABULARY_GLOSSARY.keys())
        assert not missing, f"missing glossary entries: {missing}"

    @pytest.mark.unit
    def test_report_template_has_five_sections(self):
        """REPORT_TEMPLATE should contain all 5 required sections."""
        for section in ("Summary", "What Works", "What Needs Attention", "Recommendations", "Next Steps"):
            assert section in REPORT_TEMPLATE


# =========================================================================
# Metrics
# =========================================================================


class TestMetrics:
    """Tests for MetricsConfig and MetricsRecorder."""

    @pytest.mark.unit
    def test_metrics_config_defaults(self):
        """MetricsConfig should have sensible defaults."""
        cfg = MetricsConfig()
        assert cfg.first_response_ms == 2000
        assert cfg.narration_lag_ms == 5000
        assert cfg.report_render_ms == 10000
        assert cfg.greeting_word_budget == 25

    @pytest.mark.unit
    def test_metrics_config_is_frozen(self):
        """MetricsConfig should be immutable."""
        cfg = MetricsConfig()
        with pytest.raises(Exception):
            cfg.first_response_ms = 9999

    @pytest.mark.unit
    def test_record_first_response(self):
        """record_first_response should return a non-negative int."""
        rec = MetricsRecorder()
        ms = rec.record_first_response("sess-1")
        assert isinstance(ms, int)
        assert ms >= 0
        # Idempotent
        ms2 = rec.record_first_response("sess-1")
        assert ms2 == ms

    @pytest.mark.unit
    def test_record_narration(self):
        """record_narration should append an entry."""
        rec = MetricsRecorder()
        entry = rec.record_narration("sess-1", "agent-a", 100)
        assert entry["agent_id"] == "agent-a"
        assert entry["delta_ms"] == 100
        metrics = rec.get_session_metrics("sess-1")
        assert len(metrics["narrations"]) == 1

    @pytest.mark.unit
    def test_record_narration_rejects_negative(self):
        """record_narration should raise on negative delta_ms."""
        rec = MetricsRecorder()
        with pytest.raises(ValueError, match="non-negative"):
            rec.record_narration("sess-1", "agent-a", -1)

    @pytest.mark.unit
    def test_metrics_summary_includes_breaches(self):
        """metrics_summary should compute breach flags."""
        rec = MetricsRecorder()
        rec.record_first_response("sess-2")
        rec.record_narration("sess-2", "agent-a", 999999)
        summary = rec.metrics_summary("sess-2")
        assert "breaches" in summary
        assert "narration_count" in summary
        assert summary["session_id"] == "sess-2"


# =========================================================================
# Session lifecycle
# =========================================================================


class TestSessionLifecycle:
    """Tests for EngineerSessionStore and EngineerSession."""

    @pytest.mark.unit
    def test_create_session(self, session_store):
        """create should return a session in GREETING stage."""
        sess = session_store.create("https://example.com")
        assert sess.state.current_stage == Stage.GREETING
        assert sess.state.url == "https://example.com"
        assert len(sess.session_id) > 0

    @pytest.mark.unit
    def test_get_session(self, session_store):
        """get should retrieve a created session."""
        sess = session_store.create("https://example.com")
        retrieved = session_store.get(sess.session_id)
        assert retrieved is not None
        assert retrieved.session_id == sess.session_id

    @pytest.mark.unit
    def test_update_session(self, session_store):
        """update should mutate session state and persist to vault."""
        sess = session_store.create("https://example.com")
        session_store.update(sess.session_id, url="https://other.com")
        updated = session_store.get(sess.session_id)
        assert updated.state.url == "https://other.com"

    @pytest.mark.unit
    def test_delete_session(self, session_store, tmp_vault):
        """delete should remove session from memory and vault."""
        sess = session_store.create("https://example.com")
        node_path = tmp_vault / "Runs" / "Engineer_Sessions" / f"{sess.session_id}.md"
        assert node_path.exists()
        session_store.delete(sess.session_id)
        assert session_store.get(sess.session_id) is None
        assert not node_path.exists()

    @pytest.mark.unit
    def test_cleanup_idle_evicts_all(self, session_store, tmp_vault):
        """cleanup_idle(0) should evict all sessions."""
        sess = session_store.create("https://example.com")
        count = session_store.cleanup_idle(0)
        assert count >= 1
        assert session_store.get(sess.session_id) is None

    @pytest.mark.unit
    def test_credentials_never_written_to_vault(self, session_store, tmp_vault):
        """Security contract: credentials must not appear in vault node."""
        sess = session_store.create("https://example.com")
        session_store.update(
            sess.session_id,
            credentials={"username": "foo", "password": "secret123"},
        )
        node_path = tmp_vault / "Runs" / "Engineer_Sessions" / f"{sess.session_id}.md"
        content = node_path.read_text()
        assert "secret123" not in content
        assert "credentials" not in content
        # In-memory must still hold them
        assert session_store.get(sess.session_id).state.credentials is not None
        assert session_store.get(sess.session_id).state.credentials.password == "secret123"

    @pytest.mark.unit
    def test_session_to_event(self, session_store):
        """EngineerSession.to_event should return the right event type."""
        sess = session_store.create("https://example.com")
        ev = sess.to_event(Stage.GREETING)
        assert isinstance(ev, GreetingEvent)
        ev2 = sess.to_event(Stage.DONE)
        assert isinstance(ev2, DoneEvent)


# =========================================================================
# Credentials
# =========================================================================


class TestCredentials:
    """Tests for CredentialHandler and log scrubbing."""

    @pytest.mark.unit
    def test_request_credential_event(self, sample_state):
        """request_credential should return an AskCredentialEvent."""
        ch = CredentialHandler()
        ev = ch.request_credential(sample_state, "password", "need login")
        assert isinstance(ev, AskCredentialEvent)
        assert ev.field == "password"
        assert ev.reason == "need login"

    @pytest.mark.unit
    def test_submit_credential_sets_field(self, sample_state):
        """submit_credential should store value in memory only."""
        ch = CredentialHandler()
        ch.submit_credential(sample_state, "password", "secret123")
        assert sample_state.credentials is not None
        assert sample_state.credentials.password == "secret123"

    @pytest.mark.unit
    def test_clear_overwrites_then_nils(self, sample_state):
        """clear should overwrite password before nulling."""
        ch = CredentialHandler()
        sample_state.credentials = Credentials(username="foo", password="secret123")
        ch.clear(sample_state)
        assert sample_state.credentials is None

    @pytest.mark.unit
    def test_scrub_log_record_removes_credential_keys(self):
        """scrub_log_record should strip password/secret/token keys."""
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
        # Original untouched
        assert "password" in rec

    @pytest.mark.unit
    def test_scrub_log_record_on_lists(self):
        """scrub_log_record should recurse into list values."""
        rec = {"items": [{"password": "x"}, {"safe": "y"}]}
        cleaned = scrub_log_record(rec)
        assert "password" not in cleaned["items"][0]
        assert cleaned["items"][1]["safe"] == "y"

    @pytest.mark.unit
    def test_assert_no_credential_in_text_raises(self):
        """assert_no_credential_in_text should raise on credential patterns."""
        assert_no_credential_in_text("hello world")  # no raise
        with pytest.raises(ValueError):
            assert_no_credential_in_text("my password is secret")
        with pytest.raises(ValueError):
            assert_no_credential_in_text("secret123")
        with pytest.raises(ValueError):
            assert_no_credential_in_text("token=abc")


# =========================================================================
# Classifier
# =========================================================================


class TestClassifier:
    """Tests for SiteClassifier and validate_override."""

    @pytest.mark.unit
    def test_validate_override_aliases(self):
        """validate_override should map common aliases to SiteType."""
        assert validate_override("blog") == SiteType.BLOG
        assert validate_override("e-commerce") == SiteType.ECOMMERCE
        assert validate_override("saas") == SiteType.SAAS_APP
        assert validate_override("landing") == SiteType.LANDING
        with pytest.raises(ValueError):
            validate_override("unknown")

    @pytest.mark.unit
    def test_classification_result_model(self):
        """ClassificationResult should validate confidence range."""
        r = ClassificationResult(site_type=SiteType.LANDING, confidence=0.5, signals=["s1"])
        assert r.confidence == 0.5
        with pytest.raises(Exception):
            ClassificationResult(site_type=SiteType.LANDING, confidence=1.5, signals=[])

    @pytest.mark.asyncio
    async def test_classifier_uses_heuristic(self):
        """Heuristic patterns should boost ecommerce confidence."""
        llm = AsyncMock()
        llm.complete = AsyncMock(return_value=MagicMock(content="ECOMMERCE"))
        classifier = SiteClassifier(llm=llm)

        html = "<html><body><button class='add-to-cart'>Add</button></body></html>"
        with patch("httpx.AsyncClient.get", AsyncMock(return_value=MagicMock(text=html, status_code=200))):
            result = await classifier.classify("https://shop.example.com")

        assert result.site_type == SiteType.ECOMMERCE
        assert any("heuristic:ecommerce" in s for s in result.signals)

    @pytest.mark.asyncio
    async def test_classifier_fallback_landing(self):
        """No signals and no LLM confidence should fall back to LANDING."""
        llm = AsyncMock()
        llm.complete = AsyncMock(return_value=MagicMock(content="none"))
        classifier = SiteClassifier(llm=llm)

        html = "<html><body>Hello world</body></html>"
        with patch("httpx.AsyncClient.get", AsyncMock(return_value=MagicMock(text=html, status_code=200))):
            result = await classifier.classify("https://plain.example.com")

        assert result.site_type == SiteType.LANDING
        assert any("fallback:landing" in s for s in result.signals)


# =========================================================================
# Narrator
# =========================================================================


class TestNarrator:
    """Tests for Narrator word budget and caching."""

    @pytest.mark.asyncio
    async def test_narrate_test_started_word_budget(self):
        """narrate_test_started should return ≤15 words."""
        from command_center.engineer.narrator import _cache

        _cache.clear()
        n = Narrator(llm=AsyncMock())
        r = MagicMock(content="Started testing your homepage now.")
        n.llm.complete = AsyncMock(return_value=r)
        ev = await n.narrate_test_started("t1", "ui_explorer")
        assert len(ev.message.split()) <= 15

    @pytest.mark.asyncio
    async def test_narrator_cache_hit(self):
        """Identical inputs should hit cache and skip LLM."""
        from command_center.engineer.narrator import _cache

        _cache.clear()
        n = Narrator(llm=AsyncMock())
        r = MagicMock(content="Done.")
        n.llm.complete = AsyncMock(return_value=r)
        await n.narrate_test_completed("t1", "pass", "")
        await n.narrate_test_completed("t1", "pass", "")
        assert n.llm.complete.call_count == 1

    @pytest.mark.asyncio
    async def test_narrator_scrubs_forbidden_words(self):
        """Forbidden words in LLM output should be scrubbed."""
        from command_center.engineer.narrator import _cache

        _cache.clear()
        n = Narrator(llm=AsyncMock())
        r = MagicMock(content="The selector is broken.")
        n.llm.complete = AsyncMock(return_value=r)
        ev = await n.narrate_test_progress("t1", 50, "msg")
        assert "selector" not in ev.message.lower()


# =========================================================================
# Report builder
# =========================================================================


class TestReportBuilder:
    """Tests for ReportBuilder sections and helpers."""

    @pytest.mark.asyncio
    async def test_build_report_has_all_sections(self):
        """build_report should return all 5 sections."""
        rb = ReportBuilder(llm=AsyncMock())
        r = MagicMock(
            content=(
                "# Summary\nYour site is fast.\n"
                "# What Works\n- Homepage loads.\n"
                "# What Needs Attention\n- Login button.\n"
                "# Recommendations\n1. Make it bigger.\n"
                "# Next Steps\n- Re-test.\n"
            )
        )
        rb.llm.complete = AsyncMock(return_value=r)
        ev = await rb.build_report(
            "sess1",
            [{"severity": "high", "title": "Login", "description": "Hard to find"}],
        )
        for section in ("Summary", "What Works", "What Needs Attention", "Recommendations", "Next Steps"):
            assert section in ev.sections

    @pytest.mark.asyncio
    async def test_build_report_sections_within_budget(self):
        """Each section should be within 150-word budget."""
        rb = ReportBuilder(llm=AsyncMock())
        r = MagicMock(
            content=(
                "# Summary\nYour site is fast.\n"
                "# What Works\n- Homepage loads.\n"
                "# What Needs Attention\n- Login button.\n"
                "# Recommendations\n1. Make it bigger.\n"
                "# Next Steps\n- Re-test.\n"
            )
        )
        rb.llm.complete = AsyncMock(return_value=r)
        ev = await rb.build_report("sess1", [])
        for k, v in ev.sections.items():
            assert len(v.split()) <= 150, f"{k} exceeds word budget"

    @pytest.mark.unit
    def test_severity_color_mapping(self):
        """severity_color should map technical labels to plain English."""
        assert "immediate" in severity_color("critical").lower()
        assert "fix soon" in severity_color("high").lower()
        assert "worth fixing" in severity_color("medium").lower()
        assert "minor polish" in severity_color("low").lower()
        assert "good to know" in severity_color("info").lower()
        assert severity_color("unknown") == "unknown"

    @pytest.mark.unit
    def test_recommendation_actionability_check(self):
        """recommendation_actionability_check should detect action verbs."""
        assert recommendation_actionability_check("Fix the login button") is True
        assert recommendation_actionability_check("Add a new field") is True
        assert recommendation_actionability_check("Maybe consider something") is False


# =========================================================================
# Conversation engine
# =========================================================================


class TestConversationEngine:
    """Tests for ConversationEngine event generation."""

    @pytest.mark.asyncio
    async def test_generate_greeting(self):
        """generate_greeting should return a GreetingEvent within word budget."""
        ce = ConversationEngine(llm=AsyncMock())
        r = MagicMock(content='{"message":"Hi! What URL?"}')
        ce.llm.complete = AsyncMock(return_value=r)
        state = SessionState(session_id="sess-123")
        ev = await ce.generate_greeting(state)
        assert isinstance(ev, GreetingEvent)
        assert len(ev.message.split()) <= 25

    @pytest.mark.asyncio
    async def test_generate_greeting_scrubs_forbidden(self):
        """generate_greeting should scrub forbidden words."""
        ce = ConversationEngine(llm=AsyncMock())
        r = MagicMock(content='{"message":"The selector broke."}')
        ce.llm.complete = AsyncMock(return_value=r)
        state = SessionState(session_id="sess-123")
        ev = await ce.generate_greeting(state)
        assert "selector" not in ev.message.lower()

    @pytest.mark.asyncio
    async def test_generate_turn_shortcut(self):
        """'test everything' shortcut should emit PlanProposedEvent."""
        ce = ConversationEngine(llm=AsyncMock())
        state = SessionState(
            session_id="s",
            current_stage=Stage.CONTEXT,
            site_type=SiteType.ECOMMERCE,
            url="https://shop.com",
            started_at=datetime.now(timezone.utc),
            last_activity_at=datetime.now(timezone.utc),
        )
        evs = await ce.generate_turn(state, "test everything", [])
        assert any(isinstance(e, PlanProposedEvent) for e in evs)

    @pytest.mark.asyncio
    async def test_direct_helpers(self):
        """Direct generate_* helpers should return correct event types."""
        ce = ConversationEngine(llm=AsyncMock())
        state = SessionState(session_id="s3", current_stage=Stage.PLAN)
        assert isinstance(await ce.generate_ask_question(state, "q1", "What?"), AskQuestionEvent)
        assert isinstance(await ce.generate_ask_credential(state, "password", "need login"), AskCredentialEvent)
        assert isinstance(await ce.generate_classify_site(state, "landing", 0.9, ["s"]), ClassifySiteEvent)
        assert isinstance(await ce.generate_confirm_classification(state), ConfirmClassificationEvent)
        assert isinstance(await ce.generate_plan_proposed(state, ["t1"], "ecommerce"), PlanProposedEvent)
        assert isinstance(await ce.generate_narrate(state, "a1", "ok", "msg"), NarrateEvent)
        assert isinstance(await ce.generate_test_started(state, "t1", "ui"), TestStartedEvent)
        assert isinstance(await ce.generate_test_progress(state, "t1", 50, "halfway"), TestProgressEvent)
        assert isinstance(await ce.generate_test_completed(state, "t1", "pass", "all good"), TestCompletedEvent)
        assert isinstance(await ce.generate_report(state, {"Summary": "ok"}), ReportEvent)
        assert isinstance(await ce.generate_done(state), DoneEvent)
        assert isinstance(await ce.generate_error(state, "E001", "oops"), ErrorEvent)


# =========================================================================
# LiveEngineer flow
# =========================================================================


class TestLiveEngineer:
    """Tests for LiveEngineer orchestrator."""

    @pytest.fixture
    def live_engineer(self, tmp_vault):
        """Return a LiveEngineer with a temp vault and mocked LLM."""
        from command_center.engineer import session as session_module

        session_module._store.clear()
        llm = AsyncMock()
        le = LiveEngineer(llm=llm)
        le.session_store = EngineerSessionStore(vault_path=tmp_vault)
        return le

    @pytest.mark.asyncio
    async def test_start_session_returns_greeting(self, live_engineer):
        """start_session should create a session and return a GreetingEvent."""
        r = MagicMock(content='{"message":"Hello! What URL?"}')
        live_engineer.conversation.llm.complete = AsyncMock(return_value=r)
        sess, events = await live_engineer.start_session("https://example.com")
        assert sess.state.url == "https://example.com"
        assert any(isinstance(e, GreetingEvent) for e in events)

    @pytest.mark.asyncio
    async def test_handle_message_returns_events(self, live_engineer):
        """handle_message should process user message and return events."""
        r_greet = MagicMock(content='{"message":"Hello!"}')
        live_engineer.conversation.llm.complete = AsyncMock(return_value=r_greet)
        sess, _ = await live_engineer.start_session("https://example.com")

        r_turn = MagicMock(
            content='{"events":[{"type":"ask_question","question_id":"q1","prompt":"What?"}]}'
        )
        live_engineer.conversation.llm.complete = AsyncMock(return_value=r_turn)
        evs = await live_engineer.handle_message(sess.session_id, "test message")
        assert any(isinstance(e, AskQuestionEvent) for e in evs)

    @pytest.mark.asyncio
    async def test_resume_session_returns_current_stage(self, live_engineer):
        """resume_session should return events for the current stage."""
        r = MagicMock(content='{"message":"Hello!"}')
        live_engineer.conversation.llm.complete = AsyncMock(return_value=r)
        sess, _ = await live_engineer.start_session("https://example.com")
        resumed = await live_engineer.resume_session(sess.session_id)
        assert any(isinstance(e, GreetingEvent) for e in resumed)

    @pytest.mark.asyncio
    async def test_run_execution_emits_test_events(self, live_engineer):
        """_run_execution should emit test lifecycle events."""
        from command_center.engineer import session as session_module

        session_module._store.clear()
        sess = live_engineer.session_store.create("https://example.com")
        sess.state.current_stage = Stage.EXECUTE
        sess.state.confirmed_plan = ["homepage", "auth_login"]
        live_engineer.narrator._call_llm = AsyncMock(return_value="Test started.")
        live_engineer.report.llm.complete = AsyncMock(
            return_value=MagicMock(
                content=(
                    "# Summary\nYour site is fast.\n"
                    "# What Works\n- Homepage loads.\n"
                    "# What Needs Attention\n- Login button.\n"
                    "# Recommendations\n1. Make it bigger.\n"
                    "# Next Steps\n- Re-test.\n"
                )
            )
        )
        exec_events = await live_engineer._run_execution(sess.state)
        assert any(isinstance(e, TestStartedEvent) for e in exec_events)
        assert any(isinstance(e, TestCompletedEvent) for e in exec_events)
        assert any(isinstance(e, ReportEvent) for e in exec_events)
        assert any(isinstance(e, DoneEvent) for e in exec_events)

    @pytest.mark.asyncio
    async def test_prepare_agent_injects_credentials(self, live_engineer):
        """_prepare_agent should inject credentials for credential-required sites."""
        from agents.feature_tester.worker import FeatureTesterWorker

        sess = live_engineer.session_store.create("https://example.com")
        sess.state.site_type = SiteType.ECOMMERCE
        sess.state.credentials = Credentials(username="u", password="p")
        await live_engineer._prepare_agent("agent-001", sess)
        w = FeatureTesterWorker.__new__(FeatureTesterWorker)
        w.agent_id = "agent-001"
        creds = w._get_pending_credentials()
        assert creds == {"username": "u", "password": "p"}

    @pytest.mark.unit
    def test_get_metrics_returns_summary(self, live_engineer):
        """get_metrics should return a dict with session_id and breaches."""
        sess = live_engineer.session_store.create("https://example.com")
        metrics = live_engineer.get_metrics(sess.session_id)
        assert isinstance(metrics, dict)
        assert metrics["session_id"] == sess.session_id
        assert "narration_count" in metrics
        assert "breaches" in metrics

    @pytest.mark.asyncio
    async def test_start_session_with_existing_id(self, live_engineer):
        """start_session with existing_session_id should resume if found."""
        r = MagicMock(content='{"message":"Hello!"}')
        live_engineer.conversation.llm.complete = AsyncMock(return_value=r)
        sess, _ = await live_engineer.start_session("https://example.com")
        sess2, events2 = await live_engineer.start_session(existing_session_id=sess.session_id)
        assert sess2.session_id == sess.session_id

    @pytest.mark.asyncio
    async def test_handle_message_with_credential(self, live_engineer):
        """handle_message should accept credential without logging or echoing."""
        r_greet = MagicMock(content='{"message":"Hello!"}')
        live_engineer.conversation.llm.complete = AsyncMock(return_value=r_greet)
        sess, _ = await live_engineer.start_session("https://example.com")

        r_turn = MagicMock(
            content='{"events":[{"type":"ask_question","question_id":"q1","prompt":"What?"}]}'
        )
        live_engineer.conversation.llm.complete = AsyncMock(return_value=r_turn)
        await live_engineer.handle_message(
            sess.session_id,
            "test",
            credential={"field": "password", "value": "secret123"},
        )
        # Credential should be stored in memory
        assert sess.state.credentials is not None
        assert sess.state.credentials.password == "secret123"
        # But never in vault
        node_path = (
            live_engineer.session_store.vault_path
            / "Runs"
            / "Engineer_Sessions"
            / f"{sess.session_id}.md"
        )
        content = node_path.read_text()
        assert "secret123" not in content
