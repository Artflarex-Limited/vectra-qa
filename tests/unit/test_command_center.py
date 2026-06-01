"""
Unit tests for the Command Center modules.

Covers ChatEngine (intent classification, URL extraction, test plan extraction,
response generation, message history) and ObsidianReader (node parsing,
orchestrator status).
"""

import os
import tempfile
import pytest
import yaml
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, mock_open, PropertyMock
from typing import Dict, Any, List, Optional

# ---------------------------------------------------------------------------
# Set OBSIDIAN_VAULT_PATH to a writable temp location before importing
# command_center modules.  The module-level ChatEngine() instantiation in
# command_center/chatbot.py tries to create vault directories on import, so
# we must redirect the vault path first.
# ---------------------------------------------------------------------------
_VAULT_TMPDIR = tempfile.mkdtemp(prefix="vectra_test_vault_")
os.environ["OBSIDIAN_VAULT_PATH"] = _VAULT_TMPDIR

from command_center.chatbot import ChatEngine, ChatMessage, TEST_TYPES
from command_center.obsidian_reader import ObsidianReader, ObsidianNode


def teardown_module(module):
    """Clean up the temporary vault directory created at module import."""
    import shutil
    shutil.rmtree(_VAULT_TMPDIR, ignore_errors=True)


# =========================================================================
# Fixtures
# =========================================================================


@pytest.fixture
def chat_engine():
    """Create a ChatEngine with mocked LLMRouter."""
    engine = ChatEngine()
    engine.llm = MagicMock()
    return engine


@pytest.fixture
def sample_node_content():
    """Return a sample markdown node with YAML frontmatter."""
    return """---
agent_id: test-agent-20240101000000-abc123
agent_role: ui_explorer
status: running
objective: Test the homepage at https://example.com
progress_percent: 50
---

# Test Report

## ✅ Homepage Load
The page loaded successfully.
"""


@pytest.fixture
def sample_run_node():
    """Return a sample test run node for result parsing tests."""
    return """---
agent_id: explorer-20250101000000-xyz789
agent_role: ui_explorer
status: completed
result: pass
objective: Test navigation on https://example.com
progress_percent: 100
---

# Test Report

## ✅ Page Load
Page loaded successfully.

### Metrics
- **Load Time**: 1.2s
- **Console Errors**: 0

## ❌ Navigation
Some links had issues.

### Findings
- 🔴 Broken link: /about page returns 404

## 📝 Recommendations
1. Fix the /about page redirect
2. Add a custom 404 handler

| Sections Passed | 1 |
| Sections Failed | 1 |
| Warnings | 0 |
| Total Checks | 2 |
"""


# =========================================================================
# ChatEngine — intent classification
# =========================================================================


class TestClassifyIntent:
    """Tests for ChatEngine._classify_intent."""

    @pytest.mark.unit
    def test_classify_plan_tests(self, chat_engine):
        """Should classify messages containing test-related keywords as plan_tests."""
        chat_engine.llm.complete = MagicMock(
            side_effect=RuntimeError("LLM unavailable")  # Force fallback
        )
        intent = chat_engine._classify_intent("Can you run some tests on https://example.com?")
        assert intent == "plan_tests"

    @pytest.mark.unit
    def test_classify_interpret_results(self, chat_engine):
        """Should classify messages about results as interpret_results."""
        chat_engine.llm.complete = MagicMock(
            side_effect=RuntimeError("LLM unavailable")
        )
        intent = chat_engine._classify_intent("What did the test find?")
        assert intent == "interpret_results"

    @pytest.mark.unit
    def test_classify_chat(self, chat_engine):
        """Should fall back to 'chat' for general conversation."""
        chat_engine.llm.complete = MagicMock(
            side_effect=RuntimeError("LLM unavailable")
        )
        intent = chat_engine._classify_intent("Hello, how are you?")
        assert intent == "chat"

    @pytest.mark.unit
    def test_classify_uses_llm_when_available(self, chat_engine):
        """Should use LLM when it succeeds, and return the parsed intent."""
        chat_engine.llm.complete = MagicMock(
            return_value=MagicMock(content="plan_tests")
        )
        intent = chat_engine._classify_intent("I need to test something")
        assert intent == "plan_tests"

    @pytest.mark.unit
    def test_classify_llm_rejects_invalid_intent(self, chat_engine):
        """Should reject an intent not in the valid set."""
        chat_engine.llm.complete = MagicMock(
            return_value=MagicMock(content="invalid_response")
        )
        # Fallback should fire
        intent = chat_engine._classify_intent("Hello")
        assert intent in ("chat", "plan_tests", "interpret_results")


# =========================================================================
# ChatEngine — URL extraction
# =========================================================================


class TestExtractUrl:
    """Tests for ChatEngine._extract_url."""

    @pytest.mark.unit
    def test_extracts_http_url(self, chat_engine):
        """Should extract an http URL from a message."""
        url = chat_engine._extract_url("Test https://example.com please")
        assert url == "https://example.com"

    @pytest.mark.unit
    def test_extracts_url_with_path(self, chat_engine):
        """Should extract a URL with a path component."""
        url = chat_engine._extract_url("Check out http://example.com/about/team")
        assert url == "http://example.com/about/team"

    @pytest.mark.unit
    def test_extracts_url_with_query_params(self, chat_engine):
        """Should extract a URL with query parameters."""
        url = chat_engine._extract_url("Go to https://example.com/page?foo=1&bar=2")
        assert url is not None
        assert url.startswith("https://example.com/")

    @pytest.mark.unit
    def test_no_url_returns_none(self, chat_engine):
        """Should return None when no URL is present in the message."""
        url = chat_engine._extract_url("Just a general question about testing")
        assert url is None


# =========================================================================
# ChatEngine — test plan extraction
# =========================================================================


class TestExtractTestPlan:
    """Tests for ChatEngine._extract_test_plan."""

    @pytest.mark.unit
    def test_plan_with_keyword_match(self, chat_engine):
        """Should extract URL and matching test types via keyword matching."""
        chat_engine.llm.complete = MagicMock(
            side_effect=RuntimeError("LLM unavailable")
        )
        plan = chat_engine._extract_test_plan(
            "Run a homepage test on https://example.com"
        )

        assert plan is not None
        assert plan["url"] == "https://example.com"
        assert "homepage" in plan["tests"]

    @pytest.mark.unit
    def test_plan_no_url_returns_none(self, chat_engine):
        """Should return None when no URL is found."""
        chat_engine.llm.complete = MagicMock(
            side_effect=RuntimeError("LLM unavailable")
        )
        plan = chat_engine._extract_test_plan("Run some tests")
        assert plan is None

    @pytest.mark.unit
    def test_plan_defaults_to_homepage(self, chat_engine):
        """Should default to homepage test when URL is present but no tests match."""
        chat_engine.llm.complete = MagicMock(
            side_effect=RuntimeError("LLM unavailable")
        )
        plan = chat_engine._extract_test_plan(
            "Just check the site https://example.com"
        )

        assert plan is not None
        assert plan["url"] == "https://example.com"
        assert plan["tests"] == ["homepage"]


# =========================================================================
# ChatEngine — response generation
# =========================================================================


class TestGeneratePlanResponse:
    """Tests for ChatEngine.generate_plan_response."""

    @pytest.mark.unit
    def test_formats_test_plan(self, chat_engine):
        """Should generate a readable plan response listing all test types."""
        plan = {
            "url": "https://example.com",
            "tests": ["homepage", "navigation"],
            "test_configs": [
                TEST_TYPES["homepage"],
                TEST_TYPES["navigation"],
            ],
        }
        response = chat_engine.generate_plan_response(plan)

        assert "https://example.com" in response
        assert "Homepage" in response
        assert "Navigation" in response
        assert "Does this look correct?" in response

    @pytest.mark.unit
    def test_empty_test_list(self, chat_engine):
        """Should handle a plan with an empty test configs list."""
        plan = {"url": "https://example.com", "tests": [], "test_configs": []}
        response = chat_engine.generate_plan_response(plan)

        assert "https://example.com" in response
        assert "Does this look correct?" in response


# =========================================================================
# ChatEngine — message history (add_message / get_history)
# =========================================================================


class TestMessageHistory:
    """Tests for ChatEngine message persistence."""

    @pytest.mark.unit
    def test_add_and_get_messages(self, chat_engine):
        """Should persist a message and retrieve it from history."""
        engine = chat_engine

        with patch.object(Path, "exists", return_value=True), patch.object(
            Path, "read_text", return_value="---\nmessage_count: 0\n---\n\n# Chat Log\n\n"
        ), patch.object(Path, "write_text") as mock_write:

            engine.add_message("user", "Hello Vectra!")
            engine.add_message("assistant", "How can I help you?")

            # Verify write was called with updated content
            written = mock_write.call_args[0][0]
            assert "assistant" in written
            assert "How can I help you?" in written

    @pytest.mark.unit
    def test_get_history_returns_messages(self, chat_engine):
        """Should parse and return chat messages from the log body."""
        raw_log = """---
message_count: 2
---

## [2024-01-01T12:00:00Z] user
Hello Vectra!

## [2024-01-01T12:00:05Z] assistant
How can I help you?
"""

        with patch.object(Path, "exists", return_value=True), patch.object(
            Path, "read_text", return_value=raw_log
        ), patch.object(Path, "write_text"):
            history = chat_engine.get_history(limit=10)

        assert len(history) == 2
        assert history[0]["role"] == "user"
        assert "Hello Vectra!" in history[0]["content"]
        assert history[1]["role"] == "assistant"
        assert "How can I help you?" in history[1]["content"]

    @pytest.mark.unit
    def test_get_history_respects_limit(self, chat_engine):
        """Should limit the number of returned messages."""
        raw_log = """---
message_count: 4
---

## [2024-01-01T12:00:00Z] user
Message 1

## [2024-01-01T12:00:05Z] assistant
Reply 1

## [2024-01-01T12:00:10Z] user
Message 2

## [2024-01-01T12:00:15Z] assistant
Reply 2
"""

        with patch.object(Path, "exists", return_value=True), patch.object(
            Path, "read_text", return_value=raw_log
        ), patch.object(Path, "write_text"):
            history = chat_engine.get_history(limit=2)

        assert len(history) == 2
        assert history[0]["content"] == "Message 2"
        assert history[1]["content"] == "Reply 2"


# =========================================================================
# ChatMessage model
# =========================================================================


class TestChatMessage:
    """Tests for the ChatMessage model."""

    @pytest.mark.unit
    def test_to_dict(self):
        """Should serialize to a dictionary with role, content, timestamp, metadata."""
        msg = ChatMessage(
            role="user",
            content="Hello!",
            timestamp="2024-01-01T12:00:00Z",
            metadata={"source": "web"},
        )
        d = msg.to_dict()
        assert d["role"] == "user"
        assert d["content"] == "Hello!"
        assert d["timestamp"] == "2024-01-01T12:00:00Z"
        assert d["metadata"] == {"source": "web"}

    @pytest.mark.unit
    def test_default_timestamp(self):
        """Should auto-generate a timestamp when none is provided."""
        msg = ChatMessage(role="user", content="Hi")
        assert msg.timestamp.endswith("Z")
        assert "T" in msg.timestamp


# =========================================================================
# ObsidianReader
# =========================================================================


class TestObsidianReader:
    """Tests for ObsidianReader."""

    @pytest.mark.unit
    def test_read_node_parses_frontmatter(self, tmp_path):
        """Should parse YAML frontmatter from an Obsidian markdown file."""
        vault_dir = tmp_path / "vault"
        vault_dir.mkdir()
        node_file = vault_dir / "test.md"
        node_file.write_text(
            "---\n"
            "title: Test Page\n"
            "status: active\n"
            "tags: [test, sample]\n"
            "---\n"
            "\n"
            "# Test Page\n\n"
            "This is the content.\n"
        )

        reader = ObsidianReader(vault_dir)
        node = reader.read_node("test.md")

        assert node is not None
        assert node.frontmatter["title"] == "Test Page"
        assert node.frontmatter["status"] == "active"
        assert node.frontmatter["tags"] == ["test", "sample"]
        assert "# Test Page" in node.content

    @pytest.mark.unit
    def test_read_nonexistent_node_returns_none(self, tmp_path):
        """Should return None when the requested node does not exist."""
        vault_dir = tmp_path / "vault"
        vault_dir.mkdir()

        reader = ObsidianReader(vault_dir)
        node = reader.read_node("nonexistent.md")
        assert node is None

    @pytest.mark.unit
    def test_read_node_without_frontmatter(self, tmp_path):
        """Should return empty frontmatter for files without YAML frontmatter."""
        vault_dir = tmp_path / "vault"
        vault_dir.mkdir()
        node_file = vault_dir / "plain.md"
        node_file.write_text("# Just Content\n\nNo frontmatter here.\n")

        reader = ObsidianReader(vault_dir)
        node = reader.read_node("plain.md")

        assert node is not None
        assert node.frontmatter == {}
        assert "# Just Content" in node.content

    @pytest.mark.unit
    def test_get_global_nodes(self, tmp_path):
        """Should return all markdown files from the Global directory."""
        vault_dir = tmp_path / "vault"
        global_dir = vault_dir / "Global"
        global_dir.mkdir(parents=True)

        (global_dir / "Test_Run_Master.md").write_text(
            "---\nstatus: active\n---\n# Master\n"
        )
        (global_dir / "UI_State_Log.md").write_text(
            "---\nstatus: idle\n---\n# UI State\n"
        )

        reader = ObsidianReader(vault_dir)
        nodes = reader.get_global_nodes()

        assert "Test_Run_Master" in nodes
        assert "UI_State_Log" in nodes
        assert nodes["Test_Run_Master"] is not None
        assert nodes["UI_State_Log"] is not None

    @pytest.mark.unit
    def test_get_orchestrator_status(self, tmp_path):
        """Should return orchestrator status parsed from Test_Run_Master."""
        vault_dir = tmp_path / "vault"
        global_dir = vault_dir / "Global"
        global_dir.mkdir(parents=True)

        (global_dir / "Test_Run_Master.md").write_text(
            "---\n"
            "status: running\n"
            "phase: execution\n"
            "overall_result: pending\n"
            "pass_count: 5\n"
            "fail_count: 1\n"
            "skip_count: 0\n"
            "active_agents: [agent-1, agent-2]\n"
            "completed_agents: [agent-0]\n"
            "modified: 2024-01-01T12:00:00Z\n"
            "---\n"
            "\n"
            "# Test Run Master\n\n"
            "## Notes\n"
            "- All homepage tests passed\n"
            "- Navigation tests in progress\n"
        )

        reader = ObsidianReader(vault_dir)
        status = reader.get_orchestrator_status()

        assert status["status"] == "running"
        assert status["phase"] == "execution"
        assert status["overall_result"] == "pending"
        assert status["metrics"]["pass"] == 5
        assert status["metrics"]["fail"] == 1
        assert "active_agents" in status
        assert "All homepage tests passed" in status["thoughts"]

    @pytest.mark.unit
    def test_get_orchestrator_status_missing_node(self, tmp_path):
        """Should return an error dict when Test_Run_Master doesn't exist."""
        vault_dir = tmp_path / "vault"
        vault_dir.mkdir()

        reader = ObsidianReader(vault_dir)
        status = reader.get_orchestrator_status()

        assert "error" in status
        assert "not found" in status["error"]

    @pytest.mark.unit
    def test_get_active_agents(self, tmp_path):
        """Should return agents with active/spawned/running status."""
        vault_dir = tmp_path / "vault"
        global_dir = vault_dir / "Global"
        global_dir.mkdir(parents=True)

        (global_dir / "Test_Run_Master.md").write_text(
            "---\n"
            "agent_id: master-1\n"
            "agent_role: orchestrator\n"
            "status: active\n"
            "objective: Run test suite\n"
            "---\n"
            "# Master\n"
        )

        reader = ObsidianReader(vault_dir)
        agents = reader.get_active_agents()

        assert len(agents) >= 1
        # The "orchestrator" status "active" should be included
        roles = [a["role"] for a in agents]
        assert "orchestrator" in roles
