"""
Unit tests for the MCP server module.

Tests cover:
- MCPServer initialization
- MCP request handling (tools/list, tools/call, agents/list, vault/nodes, errors)
- FastAPI health and readiness endpoints
"""

import pytest
from unittest.mock import patch, MagicMock

from mcp_server.server import MCPServer

# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────


@pytest.fixture
def mock_state_manager():
    """Create a mock StateManager."""
    sm = MagicMock()
    sm.register_signal_handlers.return_value = None
    sm.restore_state.return_value = []
    sm.save_state.return_value = None
    sm.check_orphaned_agents.return_value = []
    return sm


@pytest.fixture
def mock_tools():
    """Sample TOOLS registry for testing."""
    return {
        "read_node": {
            "description": "Read a node from the vault",
            "parameters": {"type": "object", "properties": {"node_path": {"type": "string"}}},
        },
        "write_node": {
            "description": "Write a node to the vault",
            "parameters": {
                "type": "object",
                "properties": {
                    "node_path": {"type": "string"},
                    "content": {"type": "string"},
                },
            },
        },
    }


@pytest.fixture
def server(mock_state_manager):
    """Create an MCPServer with mocked state manager."""
    with patch("mcp_server.server.get_state_manager", return_value=mock_state_manager):
        srv = MCPServer(transport="stdio")
        return srv


# ──────────────────────────────────────────────
# Initialization
# ──────────────────────────────────────────────


class TestMCPServerInit:
    """Test MCPServer construction and defaults."""

    @pytest.mark.unit
    def test_initialization_defaults(self, mock_state_manager):
        """Should set default transport and initialise state manager."""
        with patch("mcp_server.server.get_state_manager", return_value=mock_state_manager):
            srv = MCPServer()
        assert srv.transport == "stdio"
        assert srv.request_id == 0
        assert srv.state_manager is mock_state_manager

    @pytest.mark.unit
    def test_initialization_with_sse_transport(self, mock_state_manager):
        """Should accept SSE as a valid transport."""
        with patch("mcp_server.server.get_state_manager", return_value=mock_state_manager):
            srv = MCPServer(transport="sse")
        assert srv.transport == "sse"
        assert srv.request_id == 0


# ──────────────────────────────────────────────
# MCP Request Handling
# ──────────────────────────────────────────────


class TestHandleRequest:
    """Test the core MCP request handler."""

    @pytest.mark.unit
    async def test_handle_tools_list(self, server, mock_tools):
        """Should return the list of available tools."""
        with patch("mcp_server.tools.TOOLS", mock_tools):
            response = await server.handle_request({"method": "tools/list", "id": 1})

        assert response["jsonrpc"] == "2.0"
        assert response["id"] == 1
        assert "result" in response
        tools = response["result"]["tools"]
        assert len(tools) == 2
        names = [t["name"] for t in tools]
        assert "read_node" in names
        assert "write_node" in names
        # Verify tool spec is included
        read_node = next(t for t in tools if t["name"] == "read_node")
        assert read_node["description"] == "Read a node from the vault"
        assert "parameters" in read_node

    @pytest.mark.unit
    async def test_handle_tools_call(self, server):
        """Should execute a tool and return its result."""
        expected_result = {"content": "# Test", "frontmatter": {}}
        with patch("mcp_server.server.execute_tool", return_value=expected_result) as mock_exec:
            response = await server.handle_request(
                {
                    "method": "tools/call",
                    "id": 2,
                    "params": {
                        "name": "read_node",
                        "arguments": {"node_path": "test.md"},
                    },
                }
            )

        assert response["jsonrpc"] == "2.0"
        assert response["id"] == 2
        assert response["result"] == expected_result
        mock_exec.assert_called_once_with("read_node", {"node_path": "test.md"})

    @pytest.mark.unit
    async def test_handle_tools_call_without_arguments(self, server):
        """Should handle a tools/call with no arguments gracefully."""
        with patch("mcp_server.server.execute_tool", return_value={}) as mock_exec:
            response = await server.handle_request(
                {"method": "tools/call", "id": 3, "params": {"name": "some_tool"}}
            )

        assert response["jsonrpc"] == "2.0"
        # execute_tool should receive empty dict as arguments
        mock_exec.assert_called_once_with("some_tool", {})

    @pytest.mark.unit
    async def test_handle_agents_list(self, server):
        """Should list active agents via the spawner."""
        fake_agents = [
            {"agent_id": "agent-1", "status": "running", "pid": 12345},
            {"agent_id": "agent-2", "status": "exited", "pid": 12346},
        ]
        mock_spawner = MagicMock()
        mock_spawner.get_active_agents.return_value = fake_agents

        with patch("mcp_server.server.get_spawner", return_value=mock_spawner):
            response = await server.handle_request({"method": "agents/list", "id": 4})

        assert response["jsonrpc"] == "2.0"
        assert response["id"] == 4
        assert response["result"]["agents"] == fake_agents

    @pytest.mark.unit
    async def test_handle_vault_nodes(self, server):
        """Should list vault nodes via the vault."""
        fake_nodes = ["test.md", "Runs/Test.md"]
        mock_vault = MagicMock()
        mock_vault.list_nodes.return_value = fake_nodes

        with patch("mcp_server.server.get_vault", return_value=mock_vault):
            response = await server.handle_request(
                {"method": "vault/nodes", "id": 5, "params": {"directory": "Runs"}}
            )

        assert response["jsonrpc"] == "2.0"
        assert response["id"] == 5
        assert response["result"]["nodes"] == fake_nodes
        mock_vault.list_nodes.assert_called_once_with("Runs")

    @pytest.mark.unit
    async def test_handle_vault_nodes_default_directory(self, server):
        """Should default to current directory when no directory specified."""
        mock_vault = MagicMock()
        mock_vault.list_nodes.return_value = []

        with patch("mcp_server.server.get_vault", return_value=mock_vault):
            response = await server.handle_request({"method": "vault/nodes", "id": 6})

        assert response["jsonrpc"] == "2.0"
        mock_vault.list_nodes.assert_called_once_with(".")

    @pytest.mark.unit
    async def test_handle_unknown_method_returns_error(self, server):
        """Should return a JSON-RPC error for unrecognised methods."""
        response = await server.handle_request({"method": "unknown/method", "id": 99})

        assert response["jsonrpc"] == "2.0"
        assert response["id"] == 99
        assert "error" in response
        assert response["error"]["code"] == -32601
        assert "Method not found" in response["error"]["message"]

    @pytest.mark.unit
    async def test_handle_request_without_id(self, server):
        """Should handle a request that has no 'id' field by using 0."""
        with patch("mcp_server.tools.TOOLS", {}):
            response = await server.handle_request({"method": "tools/list"})

        assert response["jsonrpc"] == "2.0"
        assert response["id"] == 0  # Default when no id provided


# ──────────────────────────────────────────────
# FastAPI Endpoints
# ──────────────────────────────────────────────


class TestFastAPIEndpoints:
    """Test the FastAPI-based HTTP endpoints created by run_sse()."""

    @pytest.fixture
    def sse_app(self, mock_state_manager):
        """Capture the FastAPI app from run_sse() for testing.

        We patch uvicorn.run to intercept the FastAPI app instance, then
        raise SystemExit to break out of the (otherwise blocking) method.
        The app is returned for use with TestClient.
        """
        pytest.importorskip("fastapi", reason="fastapi not installed")

        captured = {}

        def mock_uvicorn_run(app, **kwargs):
            captured["app"] = app
            raise SystemExit("Captured app")

        with patch("mcp_server.server.get_state_manager", return_value=mock_state_manager):
            with patch("uvicorn.run", side_effect=mock_uvicorn_run):
                with patch.object(mock_state_manager, "register_signal_handlers"):
                    with patch.object(mock_state_manager, "restore_state", return_value=[]):
                        server = MCPServer(transport="sse")
                        try:
                            server.run_sse(host="localhost", port=0)
                        except SystemExit:
                            pass

        app = captured.get("app")
        assert app is not None, "Failed to capture FastAPI app from run_sse()"
        return app

    @pytest.mark.unit
    def test_health_endpoint_returns_healthy(self, sse_app):
        """GET /health should return 200 with healthy status."""
        from fastapi.testclient import TestClient

        client = TestClient(sse_app)
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "vectra-qa-mcp"
        assert "timestamp" in data

    @pytest.mark.unit
    def test_ready_endpoint_success(self, sse_app):
        """GET /ready should return 200 when vault is writable."""
        from fastapi.testclient import TestClient

        mock_vault = MagicMock()
        mock_vault.write_node.return_value = None
        mock_vault.read_node.return_value = {"frontmatter": {}, "content": "ok"}

        with patch("mcp_server.server.get_vault", return_value=mock_vault):
            client = TestClient(sse_app)
            response = client.get("/ready")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
        assert data["vault"] == "writable"
        assert data["service"] == "vectra-qa-mcp"

    @pytest.mark.unit
    def test_ready_endpoint_vault_failure(self, sse_app):
        """GET /ready should return 503 when vault operations fail."""
        from fastapi.testclient import TestClient

        mock_vault = MagicMock()
        mock_vault.write_node.side_effect = RuntimeError("Vault unavailable")

        with patch("mcp_server.server.get_vault", return_value=mock_vault):
            client = TestClient(sse_app)
            response = client.get("/ready")

        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "not_ready"
        assert "error" in data
        assert "Vault unavailable" in data["error"]

    @pytest.mark.unit
    def test_metrics_endpoint(self, sse_app):
        """GET /metrics should return agent metrics."""
        from fastapi.testclient import TestClient

        fake_agents = [
            {"agent_id": "a1", "status": "running", "pid": 111},
            {"agent_id": "a2", "status": "running", "pid": 222},
            {"agent_id": "a3", "status": "exited", "pid": 333},
        ]
        mock_spawner = MagicMock()
        mock_spawner.get_active_agents.return_value = fake_agents

        with patch("mcp_server.server.get_spawner", return_value=mock_spawner):
            client = TestClient(sse_app)
            response = client.get("/metrics")

        assert response.status_code == 200
        data = response.json()
        assert data["active_agents_total"] == 3
        assert data["active_agents_running"] == 2
        assert data["active_agents_exited"] == 1
        assert "orphaned_agents" in data
        assert "timestamp" in data

    @pytest.mark.unit
    def test_mcp_endpoint_proxies_requests(self, sse_app):
        """POST /mcp should proxy the JSON body to handle_request."""
        from fastapi.testclient import TestClient

        with patch("mcp_server.tools.TOOLS", {}):
            client = TestClient(sse_app)
            response = client.post("/mcp", json={"method": "tools/list", "id": 1})

        assert response.status_code == 200
        data = response.json()
        assert data["jsonrpc"] == "2.0"
        assert data["id"] == 1
        assert data["result"]["tools"] == []
