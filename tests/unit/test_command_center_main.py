"""
Unit tests for command_center/main.py FastAPI application.

Covers all HTTP endpoints, SSE streaming, engineer integration,
markdown extraction helpers, and MCP tool calls.
"""

import asyncio
import json
import os
import tempfile
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, mock_open, patch

import pytest

# ---------------------------------------------------------------------------
# Set up environment before importing command_center modules
# ---------------------------------------------------------------------------
_VAULT_TMPDIR = tempfile.mkdtemp(prefix="vectra_test_vault_")
os.environ["OBSIDIAN_VAULT_PATH"] = _VAULT_TMPDIR

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from command_center.main import (  # noqa: E402
    agents_sse,
    app,
    call_mcp_tool,
    event_generator,
    json_serialize,
    orchestrator_sse,
    result_sse,
    sse_stream,
    _extract_findings,
    _extract_recommendations,
    _extract_sections,
    _extract_summary,
)


@pytest.fixture
def client():
    """Return a FastAPI TestClient with mocked dependencies."""
    with patch("command_center.main.reader") as mock_reader:
        # Default mock returns
        mock_reader.get_orchestrator_status = MagicMock(return_value={"status": "running"})
        mock_reader.get_active_agents = MagicMock(return_value=[])
        mock_reader.get_global_nodes = MagicMock(return_value={})
        mock_reader.get_run_nodes = MagicMock(return_value=[])
        mock_reader.read_node = MagicMock(return_value=None)

        client = TestClient(app)
        yield client, mock_reader
        client.close()  # Prevent ResourceWarning: unclosed event loop


# =========================================================================
# Helpers
# =========================================================================


@pytest.fixture
def sample_run_node():
    """Return a sample ObsidianNode-like object for result parsing."""
    node = MagicMock()
    node.path = "Runs/Test_20240101_120000.md"
    node.frontmatter = {
        "agent_id": "agent-20240101000000-abc123",
        "agent_role": "ui_explorer",
        "status": "completed",
        "result": "pass",
        "objective": "Test https://example.com",
        "progress_percent": 100,
        "screenshots": ["shot1.png"],
        "spawned_at": "2024-01-01T12:00:00Z",
        "end_time": "2024-01-01T12:05:00Z",
        "timestamp": "2024-01-01T12:00:00Z",
        "last_action": "Validated homepage",
    }
    node.content = """# Test Report

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
    node.to_dict = MagicMock(return_value=node.frontmatter)
    return node


@pytest.fixture
def sample_markdown_content():
    """Return sample markdown content for extraction tests."""
    return """# Test Report

## [2024-01-01T12:00:00Z] Step 1
- **Action**: Loaded homepage
- **Result**: Success

## [2024-01-01T12:01:00Z] Step 2
- **Action**: Clicked nav

## ✅ Homepage
Page looks good.

### Findings
- 🔴 Critical: Missing alt text
- 🟠 High: Slow load time: 5s
- 🟡 Medium: Minor alignment issue
- 🔵 Low: Color contrast warning
- ⚪ Info: Using latest framework

### Metrics
- **Load Time**: 1.2s
- **Console Errors**: 0

## ❌ Navigation
Broken links found.

### Findings
- 🔴 Critical: /about returns 404

## 📝 Recommendations
1. Fix broken links
2. Add alt text to images
3. Optimize images

| Sections Passed | 1 |
| Sections Failed | 1 |
| Warnings | 2 |
| Total Checks | 4 |
"""


# =========================================================================
# JSON serializer
# =========================================================================


class TestJsonSerialize:
    """Tests for json_serialize helper."""

    @pytest.mark.unit
    def test_serializes_datetime(self):
        """Should format datetime as ISO string with Z suffix."""
        dt = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        result = json_serialize(dt)
        assert result == "2024-01-01T12:00:00Z"

    @pytest.mark.unit
    def test_rejects_unknown_type(self):
        """Should raise TypeError for unsupported types."""
        with pytest.raises(TypeError, match="is not JSON serializable"):
            json_serialize({1, 2, 3})


# =========================================================================
# MCP tool caller
# =========================================================================


class TestCallMcpTool:
    """Tests for call_mcp_tool helper."""

    @pytest.mark.unit
    async def test_returns_result_on_success(self):
        """Should return the nested result when MCP call succeeds."""
        mock_response = MagicMock()
        mock_response.json = MagicMock(return_value={"result": {"status": "ok", "data": "test"}})

        with patch("httpx.AsyncClient") as MockClient:
            instance = MagicMock()
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            instance.post = AsyncMock(return_value=mock_response)
            MockClient.return_value = instance

            result = await call_mcp_tool("test_tool", {"key": "val"})
            assert result == {"status": "ok", "data": "test"}

    @pytest.mark.unit
    async def test_returns_error_when_no_result_key(self):
        """Should return error dict when response lacks result key."""
        mock_response = MagicMock()
        mock_response.json = MagicMock(return_value={"error": "Tool not found"})

        with patch("httpx.AsyncClient") as MockClient:
            instance = MagicMock()
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            instance.post = AsyncMock(return_value=mock_response)
            MockClient.return_value = instance

            result = await call_mcp_tool("bad_tool", {})
            assert result["status"] == "error"
            assert "Tool not found" in result["error"]


# =========================================================================
# Health endpoints
# =========================================================================


class TestHealthEndpoints:
    """Tests for /health and /ready."""

    @pytest.mark.unit
    def test_health_returns_ok(self, client):
        """GET /health should return status ok."""
        c, _ = client
        response = c.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    @pytest.mark.unit
    def test_ready_returns_ready(self, client):
        """GET /ready should return status ready."""
        c, _ = client
        response = c.get("/ready")
        assert response.status_code == 200
        assert response.json() == {"status": "ready"}


# =========================================================================
# Dashboard
# =========================================================================


class TestDashboard:
    """Tests for the root dashboard endpoint."""

    @pytest.mark.unit
    def test_serves_index_html(self, client):
        """GET / should serve command_center/static/index.html."""
        c, _ = client
        html_content = "<html><body>Dashboard</body></html>"

        with patch("builtins.open", mock_open(read_data=html_content)):
            response = c.get("/")

        assert response.status_code == 200
        assert "Dashboard" in response.text


# =========================================================================
# API — Orchestrator
# =========================================================================


class TestOrchestratorApi:
    """Tests for orchestrator status endpoints."""

    @pytest.mark.unit
    def test_orchestrator_status(self, client):
        """GET /api/orchestrator/status should return reader status."""
        c, mock_reader = client
        mock_reader.get_orchestrator_status = MagicMock(
            return_value={"status": "running", "phase": "execution"}
        )

        response = c.get("/api/orchestrator/status")
        assert response.status_code == 200
        assert response.json()["status"] == "running"

    @pytest.mark.unit
    def test_active_agents(self, client):
        """GET /api/agents/active should return agents list."""
        c, mock_reader = client
        mock_reader.get_active_agents = MagicMock(
            return_value=[{"role": "ui_explorer", "status": "active"}]
        )

        response = c.get("/api/agents/active")
        assert response.status_code == 200
        assert response.json()["agents"][0]["role"] == "ui_explorer"


# =========================================================================
# API — Nodes
# =========================================================================


class TestNodesApi:
    """Tests for node reading endpoints."""

    @pytest.mark.unit
    def test_global_nodes(self, client):
        """GET /api/nodes/global should return all global nodes as dicts."""
        c, mock_reader = client
        node = MagicMock()
        node.to_dict = MagicMock(return_value={"path": "Test.md", "content_preview": "Hi"})
        mock_reader.get_global_nodes = MagicMock(return_value={"Test": node})

        response = c.get("/api/nodes/global")
        assert response.status_code == 200
        assert response.json()["Test"]["path"] == "Test.md"

    @pytest.mark.unit
    def test_read_node_found(self, client):
        """GET /api/nodes/{path} should return node dict when found."""
        c, mock_reader = client
        node = MagicMock()
        node.to_dict = MagicMock(return_value={"path": "Global/Test.md", "content": "# Test"})
        mock_reader.read_node = MagicMock(return_value=node)

        response = c.get("/api/nodes/Global/Test.md")
        assert response.status_code == 200
        assert response.json()["path"] == "Global/Test.md"

    @pytest.mark.unit
    def test_read_node_not_found(self, client):
        """GET /api/nodes/{path} should return error when node missing."""
        c, mock_reader = client
        mock_reader.read_node = MagicMock(return_value=None)

        response = c.get("/api/nodes/missing.md")
        assert response.status_code == 200
        assert "error" in response.json()


# =========================================================================
# API — Tests
# =========================================================================


class TestTestTypesApi:
    """Tests for test type listing and test execution."""

    @pytest.mark.unit
    def test_get_test_types(self, client):
        """GET /api/tests/types should list all available test types."""
        c, _ = client
        response = c.get("/api/tests/types")
        assert response.status_code == 200
        data = response.json()
        assert "types" in data
        ids = [t["id"] for t in data["types"]]
        assert "homepage" in ids
        assert "navigation" in ids
        assert "full" in ids

    @pytest.mark.unit
    def test_run_test_unknown_type(self, client):
        """POST /api/tests/run should reject unknown test types."""
        c, _ = client
        response = c.post(
            "/api/tests/run", data={"url": "https://example.com", "test_type": "unknown"}
        )
        assert response.status_code == 400
        assert "error" in response.json()

    @pytest.mark.unit
    def test_run_test_success(self, client):
        """POST /api/tests/run should spawn agent via MCP on success."""
        c, _ = client
        with patch("command_center.main.call_mcp_tool", new_callable=AsyncMock) as mock_mcp:
            mock_mcp.return_value = {"status": "success", "result": {"agent_id": "agent-123"}}

            response = c.post(
                "/api/tests/run", data={"url": "https://example.com", "test_type": "homepage"}
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["agent_id"] == "agent-123"

    @pytest.mark.unit
    def test_run_test_mcp_error(self, client):
        """POST /api/tests/run should return 500 when MCP call fails."""
        c, _ = client
        with patch("command_center.main.call_mcp_tool", new_callable=AsyncMock) as mock_mcp:
            mock_mcp.return_value = {"status": "error", "error": "MCP down"}

            response = c.post(
                "/api/tests/run", data={"url": "https://example.com", "test_type": "homepage"}
            )

        assert response.status_code == 500
        assert "MCP down" in response.json()["error"]

    @pytest.mark.unit
    def test_run_test_exception(self, client):
        """POST /api/tests/run should return 500 on unexpected exception."""
        c, _ = client
        with patch("command_center.main.call_mcp_tool", new_callable=AsyncMock) as mock_mcp:
            mock_mcp.side_effect = RuntimeError("boom")

            response = c.post(
                "/api/tests/run", data={"url": "https://example.com", "test_type": "homepage"}
            )

        assert response.status_code == 500
        assert "boom" in response.json()["error"]


# =========================================================================
# API — Results
# =========================================================================


class TestResultsApi:
    """Tests for results listing and detail endpoints."""

    @pytest.mark.unit
    def test_list_results(self, client, sample_run_node):
        """GET /api/results should return sorted list of test runs."""
        c, mock_reader = client
        mock_reader.get_run_nodes = MagicMock(return_value=[sample_run_node])

        response = c.get("/api/results")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert data["results"][0]["agent_id"] == "agent-20240101000000-abc123"

    @pytest.mark.unit
    def test_list_results_skips_none_nodes(self, client):
        """GET /api/results should skip None nodes gracefully."""
        c, mock_reader = client
        mock_reader.get_run_nodes = MagicMock(return_value=[None])

        response = c.get("/api/results")
        assert response.status_code == 200
        assert response.json()["count"] == 0

    @pytest.mark.unit
    def test_get_result_found(self, client, sample_run_node):
        """GET /api/results/{agent_id} should return full result data."""
        c, mock_reader = client
        mock_reader.get_run_nodes = MagicMock(return_value=[sample_run_node])

        response = c.get("/api/results/agent-20240101000000-abc123")
        assert response.status_code == 200
        data = response.json()
        assert data["agent_id"] == "agent-20240101000000-abc123"
        assert "sections" in data
        assert "recommendations" in data
        assert "summary" in data
        assert "findings" in data

    @pytest.mark.unit
    def test_get_result_not_found(self, client):
        """GET /api/results/{agent_id} should return 404 when missing."""
        c, mock_reader = client
        mock_reader.get_run_nodes = MagicMock(return_value=[])

        response = c.get("/api/results/nonexistent")
        assert response.status_code == 404


# =========================================================================
# Result page HTML
# =========================================================================


class TestResultPage:
    """Tests for /results/{agent_id} HTML endpoint."""

    @pytest.mark.unit
    def test_serves_result_html(self, client):
        """Should serve result.html when file exists."""
        c, _ = client
        html = "<html><body>Result</body></html>"

        with patch("builtins.open", mock_open(read_data=html)):
            response = c.get("/results/agent-123")

        assert response.status_code == 200
        assert "Result" in response.text

    @pytest.mark.unit
    def test_result_page_not_found(self, client):
        """Should return 404 HTML when result.html is missing."""
        c, _ = client

        def raise_fnf(*args, **kwargs):
            raise FileNotFoundError()

        with patch("builtins.open", side_effect=raise_fnf):
            response = c.get("/results/agent-123")

        assert response.status_code == 404
        assert "Result page not found" in response.text


# =========================================================================
# SSE Endpoints
# =========================================================================


class TestSseEndpoints:
    """Tests for Server-Sent Events endpoints."""

    @pytest.mark.unit
    def test_sse_stream_returns_event_stream(self, client):
        """GET /api/sse/stream should return a StreamingResponse with event-stream media type."""
        c, mock_reader = client
        mock_reader.get_orchestrator_status = MagicMock(return_value={})
        mock_reader.get_active_agents = MagicMock(return_value=[])
        mock_reader.get_global_nodes = MagicMock(return_value={})

        async def _call():
            from fastapi import Request

            request = MagicMock(spec=Request)
            return await sse_stream(request)

        response = asyncio.run(_call())
        assert response.media_type == "text/event-stream"
        assert response.headers["Cache-Control"] == "no-cache"

    @pytest.mark.unit
    def test_agents_sse_returns_event_stream(self, client):
        """GET /api/sse/agents should return a StreamingResponse with event-stream media type."""
        c, mock_reader = client
        mock_reader.get_active_agents = MagicMock(return_value=[])

        async def _call():
            from fastapi import Request

            request = MagicMock(spec=Request)
            return await agents_sse(request)

        response = asyncio.run(_call())
        assert response.media_type == "text/event-stream"

    @pytest.mark.unit
    def test_orchestrator_sse_returns_event_stream(self, client):
        """GET /api/sse/orchestrator should return a StreamingResponse with event-stream media type."""
        c, mock_reader = client
        mock_reader.get_orchestrator_status = MagicMock(return_value={})

        async def _call():
            from fastapi import Request

            request = MagicMock(spec=Request)
            return await orchestrator_sse(request)

        response = asyncio.run(_call())
        assert response.media_type == "text/event-stream"

    @pytest.mark.unit
    def test_result_sse_returns_event_stream(self, client):
        """GET /api/sse/results/{agent_id} should return a StreamingResponse with event-stream media type."""
        c, mock_reader = client
        mock_reader.get_run_nodes = MagicMock(return_value=[])

        async def _call():
            from fastapi import Request

            request = MagicMock(spec=Request)
            return await result_sse(request, "agent-123")

        response = asyncio.run(_call())
        assert response.media_type == "text/event-stream"

    @pytest.mark.unit
    def test_event_generator_yields_data(self, client):
        """event_generator should yield a properly formatted SSE data line."""
        c, mock_reader = client
        mock_reader.get_orchestrator_status = MagicMock(return_value={"status": "ok"})
        mock_reader.get_active_agents = MagicMock(return_value=[])
        mock_reader.get_global_nodes = MagicMock(return_value={})

        async def consume():
            gen = event_generator()
            with patch("command_center.main.asyncio.sleep", new_callable=MagicMock):
                item = await gen.__anext__()
                return item

        item = asyncio.run(consume())
        assert item.startswith("data: ")
        data = json.loads(item.replace("data: ", "").strip())
        assert "timestamp" in data
        assert "orchestrator" in data


# =========================================================================
# Markdown extraction helpers
# =========================================================================


class TestExtractFindings:
    """Tests for _extract_findings."""

    @pytest.mark.unit
    def test_extracts_timestamped_sections(self, sample_markdown_content):
        """Should extract timestamped sections as findings."""
        findings = _extract_findings(sample_markdown_content)
        assert len(findings) >= 2
        assert findings[0]["timestamp"] == "2024-01-01T12:00:00Z"
        assert any("Action" in item for item in findings[0]["items"])

    @pytest.mark.unit
    def test_empty_content_returns_empty(self):
        """Should return empty list for empty content."""
        assert _extract_findings("") == []

    @pytest.mark.unit
    def test_no_timestamped_sections_returns_empty(self):
        """Should return empty list when no ## [timestamp] sections exist."""
        assert _extract_findings("# Hello\n\nPlain text.") == []


class TestExtractSections:
    """Tests for _extract_sections."""

    @pytest.mark.unit
    def test_extracts_pass_fail_sections(self, sample_markdown_content):
        """Should parse sections with pass/fail emojis and findings."""
        sections = _extract_sections(sample_markdown_content)
        assert len(sections) >= 2

        homepage = next((s for s in sections if s["title"] == "Homepage"), None)
        assert homepage is not None
        assert homepage["status"] == "pass"
        assert len(homepage["findings"]) >= 1

        navigation = next((s for s in sections if s["title"] == "Navigation"), None)
        assert navigation is not None
        assert navigation["status"] == "fail"

    @pytest.mark.unit
    def test_extracts_metrics(self, sample_markdown_content):
        """Should parse metrics under ### Metrics."""
        sections = _extract_sections(sample_markdown_content)
        homepage = next((s for s in sections if s["title"] == "Homepage"), None)
        assert homepage is not None
        assert "Load Time" in homepage["metrics"]
        assert homepage["metrics"]["Load Time"] == "1.2s"

    @pytest.mark.unit
    def test_extracts_severity_levels(self, sample_markdown_content):
        """Should map emoji prefixes to severity levels."""
        sections = _extract_sections(sample_markdown_content)
        homepage = next((s for s in sections if s["title"] == "Homepage"), None)
        severities = {f["severity"] for f in homepage["findings"]}
        assert "critical" in severities
        assert "high" in severities
        assert "medium" in severities
        assert "low" in severities
        assert "info" in severities

    @pytest.mark.unit
    def test_empty_content_returns_empty(self):
        """Should return empty list for empty content."""
        assert _extract_sections("") == []

    @pytest.mark.unit
    def test_bold_format_parsing(self):
        """Should parse findings with colon separator."""
        content = "## ✅ Test\n\n### Findings\n- 🔴 **Critical Issue**: Something is broken\n"
        sections = _extract_sections(content)
        # The ": " branch is taken first, so ** remain in title
        assert "Critical Issue" in sections[0]["findings"][0]["title"]
        assert sections[0]["findings"][0]["description"] == "Something is broken"

    @pytest.mark.unit
    def test_bold_format_without_colon(self):
        """Should parse bold format when no plain colon exists."""
        content = "## ✅ Test\n\n### Findings\n- 🔴 **Critical Issue**\n"
        sections = _extract_sections(content)
        # No ": " so it falls through to the ** handler (which leaves it as-is since no match)
        assert "Critical Issue" in sections[0]["findings"][0]["title"]


class TestExtractRecommendations:
    """Tests for _extract_recommendations."""

    @pytest.mark.unit
    def test_extracts_numbered_recommendations(self, sample_markdown_content):
        """Should extract numbered items under Recommendations section."""
        recs = _extract_recommendations(sample_markdown_content)
        assert len(recs) >= 2
        assert "Fix broken links" in recs[0]
        assert "alt text" in recs[1]

    @pytest.mark.unit
    def test_empty_content_returns_empty(self):
        """Should return empty list when no Recommendations section exists."""
        assert _extract_recommendations("# Hello\n\nNo recs here.") == []


class TestExtractSummary:
    """Tests for _extract_summary."""

    @pytest.mark.unit
    def test_extracts_table_values(self, sample_markdown_content):
        """Should parse pass/fail/warning/total from markdown table."""
        summary = _extract_summary(sample_markdown_content)
        assert summary["pass"] == 1
        assert summary["fail"] == 1
        assert summary["warning"] == 2
        assert summary["total"] == 4

    @pytest.mark.unit
    def test_missing_table_returns_zeros(self):
        """Should return zeros when no summary table is present."""
        summary = _extract_summary("# Hello\n\nNo tables.")
        assert summary == {"pass": 0, "fail": 0, "warning": 0, "total": 0}

    @pytest.mark.unit
    def test_malformed_table_ignored(self):
        """Should ignore malformed table rows gracefully."""
        content = "| Sections Passed | abc |\n| Sections Failed | 2 |"
        summary = _extract_summary(content)
        assert summary["pass"] == 0  # abc can't be parsed
        assert summary["fail"] == 2


# =========================================================================
# API — Live QA Engineer
# =========================================================================


@pytest.fixture
def mock_live_engineer():
    """Return a mock LiveEngineer with predictable async responses."""
    from command_center.engineer.events import GreetingEvent, AskQuestionEvent
    from command_center.engineer.state_machine import Stage

    mock = MagicMock()

    mock_sess = MagicMock()
    mock_sess.session_id = "test-session-123"
    mock_sess.state.current_stage.value = "greeting"

    async def _start_session(*, url=None, existing_session_id=None):
        greeting = GreetingEvent(
            session_id="test-session-123",
            stage=Stage.GREETING,
            timestamp="2024-01-01T12:00:00Z",
            message="Hi! I'm Vectra.",
        )
        return mock_sess, [greeting]

    mock.start_session = _start_session

    async def _handle_message(*, session_id, user_message, credential=None):
        return [
            AskQuestionEvent(
                session_id=session_id,
                stage=Stage.GREETING,
                timestamp="2024-01-01T12:00:00Z",
                question_id="q1",
                prompt="What URL?",
            )
        ]

    mock.handle_message = _handle_message

    async def _resume_session(session_id):
        return [
            GreetingEvent(
                session_id=session_id,
                stage=Stage.GREETING,
                timestamp="2024-01-01T12:00:00Z",
                message="Hi! I'm Vectra.",
            )
        ]

    mock.resume_session = _resume_session

    mock.get_metrics = MagicMock(
        return_value={"narration_count": 0, "breaches": []}
    )

    return mock


class TestEngineerEndpoints:
    """Tests for /api/engineer/* endpoints."""

    @pytest.mark.unit
    def test_engineer_start_returns_session(self, client, mock_live_engineer):
        """POST /api/engineer/start should return session_id, events, stage."""
        c, _ = client
        with patch("command_center.main._get_live_engineer", return_value=mock_live_engineer):
            response = c.post("/api/engineer/start", json={})
        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert "events" in data
        assert "stage" in data
        assert data["stage"] == "greeting"
        assert len(data["events"]) == 1
        assert data["events"][0]["type"] == "greeting"

    @pytest.mark.unit
    def test_engineer_start_sets_cookie(self, client, mock_live_engineer):
        """POST /api/engineer/start should set session_id cookie."""
        c, _ = client
        with patch("command_center.main._get_live_engineer", return_value=mock_live_engineer):
            response = c.post("/api/engineer/start", json={})
        assert "session_id" in response.cookies

    @pytest.mark.unit
    def test_engineer_start_with_url(self, client, mock_live_engineer):
        """POST /api/engineer/start should pass url to live_engineer."""
        c, _ = client
        with patch("command_center.main._get_live_engineer", return_value=mock_live_engineer):
            response = c.post("/api/engineer/start", json={"url": "https://example.com"})
        assert response.status_code == 200

    @pytest.mark.unit
    def test_engineer_start_with_existing_session(self, client, mock_live_engineer):
        """POST /api/engineer/start should resume when session_id provided."""
        c, _ = client
        with patch("command_center.main._get_live_engineer", return_value=mock_live_engineer):
            response = c.post("/api/engineer/start", json={"session_id": "test-session-123"})
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == "test-session-123"

    @pytest.mark.unit
    def test_engineer_message_returns_events(self, client, mock_live_engineer):
        """POST /api/engineer/{sid}/message should return events list."""
        c, _ = client
        with patch("command_center.main._get_live_engineer", return_value=mock_live_engineer):
            response = c.post(
                "/api/engineer/test-session-123/message",
                json={"message": "hello"},
            )
        assert response.status_code == 200
        data = response.json()
        assert "events" in data
        assert "stage" in data

    @pytest.mark.unit
    def test_engineer_message_with_credential(self, client, mock_live_engineer):
        """POST /api/engineer/{sid}/message should accept credential."""
        c, _ = client
        with patch("command_center.main._get_live_engineer", return_value=mock_live_engineer):
            response = c.post(
                "/api/engineer/test-session-123/message",
                json={
                    "message": "[credential_submitted]",
                    "credential": {"field": "password", "value": "secret"},
                },
            )
        assert response.status_code == 200

    @pytest.mark.unit
    def test_engineer_stream_returns_event_stream(self, client, mock_live_engineer):
        """GET /api/engineer/{sid}/stream should return text/event-stream."""
        c, _ = client
        with patch("command_center.main._get_live_engineer", return_value=mock_live_engineer):
            response = c.get("/api/engineer/test-session-123/stream")
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]

    @pytest.mark.unit
    def test_engineer_stream_includes_heartbeat(self, client, mock_live_engineer):
        """GET /api/engineer/{sid}/stream should yield heartbeat events."""
        c, _ = client
        with patch("command_center.main._get_live_engineer", return_value=mock_live_engineer):
            response = c.get("/api/engineer/test-session-123/stream")
        assert response.status_code == 200
        assert "heartbeat" in response.text

    @pytest.mark.unit
    def test_engineer_metrics_returns_metrics(self, client, mock_live_engineer):
        """GET /api/engineer/{sid}/metrics should return metrics dict."""
        c, _ = client
        with patch("command_center.main._get_live_engineer", return_value=mock_live_engineer):
            response = c.get("/api/engineer/test-session-123/metrics")
        assert response.status_code == 200
        data = response.json()
        assert "narration_count" in data

    @pytest.mark.unit
    def test_engineer_resume_returns_events(self, client, mock_live_engineer):
        """GET /api/engineer/{sid}/resume should return events and stage."""
        c, _ = client
        with patch("command_center.main._get_live_engineer", return_value=mock_live_engineer):
            response = c.get("/api/engineer/test-session-123/resume")
        assert response.status_code == 200
        data = response.json()
        assert "events" in data
        assert "stage" in data

    @pytest.mark.unit
    def test_engineer_message_fallback_on_exception(self, client):
        """POST /api/engineer/{sid}/message should return fallback on exception."""
        c, _ = client
        bad_engineer = MagicMock()
        bad_engineer.handle_message = AsyncMock(side_effect=RuntimeError("boom"))
        with patch("command_center.main._get_live_engineer", return_value=bad_engineer):
            response = c.post(
                "/api/engineer/test-session-123/message",
                json={"message": "hello"},
            )
        assert response.status_code == 200
        data = response.json()
        assert "events" in data
        assert data["events"][0]["type"] == "ask_question"

    @pytest.mark.unit
    def test_engineer_stream_session_not_found(self, client):
        """GET /api/engineer/{sid}/stream should handle missing session gracefully."""
        c, _ = client
        bad_engineer = MagicMock()

        async def _raise(*args, **kwargs):
            raise KeyError("nope")

        bad_engineer.resume_session = _raise
        with patch("command_center.main._get_live_engineer", return_value=bad_engineer):
            response = c.get("/api/engineer/missing/stream")
        assert response.status_code == 200
        assert "error" in response.text


# =========================================================================
# API — Removed chat endpoints (must return 404)
# =========================================================================


class TestChatEndpointsRemoved:
    """Tests confirming old /api/chat/* endpoints return 404."""

    @pytest.mark.unit
    def test_chat_history_returns_404(self, client):
        """GET /api/chat/history should return 404."""
        c, _ = client
        response = c.get("/api/chat/history")
        assert response.status_code == 404

    @pytest.mark.unit
    def test_chat_message_returns_404(self, client):
        """POST /api/chat/message should return 404."""
        c, _ = client
        response = c.post("/api/chat/message", json={"message": "hi"})
        assert response.status_code == 404

    @pytest.mark.unit
    def test_chat_execute_returns_404(self, client):
        """POST /api/chat/execute should return 404."""
        c, _ = client
        response = c.post("/api/chat/execute", json={"command": "test"})
        assert response.status_code == 404

    @pytest.mark.unit
    def test_chat_sse_returns_404(self, client):
        """GET /api/chat/sse should return 404."""
        c, _ = client
        response = c.get("/api/chat/sse")
        assert response.status_code == 404

    @pytest.mark.unit
    def test_chat_interpret_returns_404(self, client):
        """GET /api/chat/interpret/{agent_id} should return 404."""
        c, _ = client
        response = c.get("/api/chat/interpret/agent-123")
        assert response.status_code == 404
