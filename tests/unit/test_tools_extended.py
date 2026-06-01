"""
Extended unit tests for MCP Tools.

Tests cover:
- Tool execution error paths
- Mock browser operations in tools
- Agent lifecycle edge cases
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

import subprocess

from mcp_server.tools import (
    ObsidianVault,
    AgentSpawner,
    execute_tool,
    TOOLS,
    _run_browser_tool,
    _run_feature_tool,
)

# ──────────────────────────────────────────────
# ObsidianVault Error Paths
# ──────────────────────────────────────────────


class TestObsidianVaultAtomicWrite:
    """Test atomic write error handling."""

    @pytest.mark.unit
    def test_atomic_write_cleans_up_on_error(self, temp_vault_path):
        """Should clean up temp file on write error."""
        vault = ObsidianVault(temp_vault_path)
        target = temp_vault_path / "test.md"

        with patch("tempfile.mkstemp", return_value=(1, str(temp_vault_path / ".tmp_test.md_xxx"))):
            with patch("os.fdopen", side_effect=IOError("Write failed")):
                with patch("os.unlink") as mock_unlink:
                    with pytest.raises(IOError):
                        vault._atomic_write(target, "content")
                    mock_unlink.assert_called_once()


class TestObsidianVaultValidatePath:
    """Test path validation edge cases."""

    @pytest.mark.unit
    def test_reject_absolute_path(self, temp_vault_path):
        """Should reject absolute paths."""
        vault = ObsidianVault(temp_vault_path)
        with pytest.raises(ValueError, match="Absolute paths not allowed"):
            vault._validate_path("/etc/passwd")

    @pytest.mark.unit
    def test_reject_path_traversal(self, temp_vault_path):
        """Should reject path traversal attempts."""
        vault = ObsidianVault(temp_vault_path)
        with pytest.raises(ValueError, match="Path traversal not allowed"):
            vault._validate_path("../secret.md")

    @pytest.mark.unit
    def test_reject_path_outside_vault(self, temp_vault_path):
        """Should reject paths that resolve outside vault."""
        vault = ObsidianVault(temp_vault_path)
        # Mock relative_to to raise ValueError, simulating path outside vault
        with patch.object(Path, "relative_to", side_effect=ValueError("outside")):
            with pytest.raises(ValueError, match="Path outside vault"):
                vault._validate_path("some_file.md")


class TestObsidianVaultReadNodeErrors:
    """Test read_node error handling."""

    @pytest.mark.unit
    def test_yaml_parse_error_recovery(self, vault):
        """Should recover from YAML parse errors."""
        vault.write_node("bad_yaml.md", "---\nbad: yaml: content\n---\nBody")
        # Manually corrupt to trigger yaml error
        file_path = vault.vault_path / "bad_yaml.md"
        file_path.write_text("---\ninvalid yaml : [ : ]\n---\nBody content")

        result = vault.read_node("bad_yaml.md")
        assert "parse_error" in result
        assert result["raw"] is not None


class TestObsidianVaultWriteNodeErrors:
    """Test write_node error handling."""

    @pytest.mark.unit
    def test_write_verification_failure(self, vault):
        """Should raise VaultCorruptionError when verification fails."""
        with patch.object(vault, "_atomic_write") as _mock_write:
            with patch.object(Path, "read_text", return_value="different content"):
                with pytest.raises(Exception):
                    vault.write_node("test.md", "content")


class TestObsidianVaultUpdateFrontmatterErrors:
    """Test update_frontmatter error handling."""

    @pytest.mark.unit
    def test_update_frontmatter_yaml_parse_error(self, vault):
        """Should handle YAML parse errors during update."""
        vault.write_node("bad_frontmatter.md", "---\ninvalid yaml : [ : ]\n---\nBody")

        from mcp_server.tools import VaultError

        with pytest.raises(VaultError):
            vault.update_frontmatter("bad_frontmatter.md", {"status": "updated"})


# ──────────────────────────────────────────────
# AgentSpawner Edge Cases
# ──────────────────────────────────────────────


class TestAgentSpawnerLifecycle:
    """Test agent spawner edge cases."""

    @pytest.mark.unit
    def test_spawn_agent_unknown_role(self, vault):
        """Should handle unknown roles gracefully."""
        spawner = AgentSpawner(vault)

        with patch("subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.pid = 12345
            mock_popen.return_value = mock_process

            result = spawner.spawn_agent("unknown_role", "Test objective", "Runs/Unknown.md")

            assert result["status"] == "active"
            assert result["role"] == "unknown_role"
            mock_popen.assert_called_once()

    @pytest.mark.unit
    def test_spawn_agent_worker_not_found(self, vault):
        """Should handle missing worker script."""
        spawner = AgentSpawner(vault)

        with patch("os.path.exists", return_value=False):
            result = spawner.spawn_agent("ui_explorer", "Test", "Runs/Test.md")

            assert result["status"] == "error"
            assert "Worker script not found" in result["error"]

    @pytest.mark.unit
    def test_terminate_agent_not_found(self, vault):
        """Should return error for non-existent agent."""
        spawner = AgentSpawner(vault)
        result = spawner.terminate_agent("nonexistent-agent")
        assert "error" in result
        assert "not found" in result["error"]

    @pytest.mark.unit
    def test_terminate_agent_force_kill(self, vault):
        """Should force kill agent that doesn't terminate gracefully."""
        spawner = AgentSpawner(vault)
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.wait.side_effect = [subprocess.TimeoutExpired("cmd", 5), None]

        spawner.active_processes["agent-123"] = mock_process

        # Create a node for the agent
        vault.write_node("agent_node.md", "test", frontmatter={"agent_id": "agent-123"})

        result = spawner.terminate_agent("agent-123")

        assert result["status"] == "terminated"
        mock_process.terminate.assert_called_once()
        mock_process.kill.assert_called_once()

    @pytest.mark.unit
    def test_get_active_agents(self, vault):
        """Should list active agents with their status."""
        spawner = AgentSpawner(vault)
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.poll.return_value = None

        spawner.active_processes["agent-1"] = mock_process

        agents = spawner.get_active_agents()
        assert len(agents) == 1
        assert agents[0]["agent_id"] == "agent-1"
        assert agents[0]["status"] == "running"

    @pytest.mark.unit
    def test_get_active_agents_exited(self, vault):
        """Should show exited status for finished processes."""
        spawner = AgentSpawner(vault)
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.poll.return_value = 0

        spawner.active_processes["agent-1"] = mock_process

        agents = spawner.get_active_agents()
        assert agents[0]["status"] == "exited"


# ──────────────────────────────────────────────
# execute_tool Error Paths
# ──────────────────────────────────────────────


class TestExecuteToolErrors:
    """Test execute_tool error handling."""

    @pytest.mark.unit
    def test_unknown_tool(self):
        """Should return error for unknown tool name."""
        result = execute_tool("nonexistent_tool", {})
        assert "error" in result
        assert "Unknown tool" in result["error"]

    @pytest.mark.unit
    def test_missing_required_parameter(self):
        """Should return error for missing required parameter."""
        result = execute_tool("read_obsidian_node", {})
        assert "error" in result
        assert "Missing required parameter" in result["error"]

    @pytest.mark.unit
    def test_tool_handler_exception(self):
        """Should catch and return handler exceptions."""
        with patch.dict(
            TOOLS,
            {
                "bad_tool": {
                    "description": "A bad tool",
                    "parameters": {},
                    "handler": lambda params: (_ for _ in ()).throw(RuntimeError("Handler failed")),
                }
            },
            clear=False,
        ):
            result = execute_tool("bad_tool", {})
            assert result["status"] == "error"
            assert "Handler failed" in result["error"]


# ──────────────────────────────────────────────
# Browser Tool Error Paths
# ──────────────────────────────────────────────


class TestBrowserToolErrors:
    """Test browser tool error handling."""

    @pytest.mark.unit
    def test_browser_tool_async_error(self):
        """Should handle errors in async browser tool execution."""
        with patch("mcp_server.tools._get_browser", side_effect=Exception("Browser failed")):
            result = _run_browser_tool("query_selector", {"selector": "div"})
            assert result["status"] == "error"
            assert "Browser tool failed" in result["error"]

    @pytest.mark.unit
    def test_browser_tool_unknown_type(self):
        """Should handle unknown browser tool type."""
        import asyncio

        async def mock_browser():
            browser = MagicMock()
            browser.page = MagicMock()
            return browser

        with patch("mcp_server.tools._get_browser") as mock_get_browser:
            mock_browser_obj = MagicMock()
            mock_browser_obj.page = MagicMock()
            mock_get_browser.return_value = mock_browser_obj

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(
                    __import__(
                        "mcp_server.tools", fromlist=["_async_browser_tool"]
                    )._async_browser_tool("unknown_tool", {})
                )
                assert "error" in result
            finally:
                loop.close()


# ──────────────────────────────────────────────
# Feature Tool Error Paths
# ──────────────────────────────────────────────


class TestFeatureToolErrors:
    """Test feature tool error handling."""

    @pytest.mark.unit
    def test_feature_tool_async_error(self):
        """Should handle errors in async feature tool execution."""
        with patch("asyncio.get_event_loop", side_effect=Exception("Loop error")):
            result = _run_feature_tool("auth", {"login_url": "https://example.com"})
            assert result["status"] == "error"
            assert "Feature tool failed" in result["error"]

    @pytest.mark.unit
    def test_feature_tool_unknown_type(self):
        """Should handle unknown feature tool type."""
        import asyncio

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                __import__(
                    "mcp_server.tools", fromlist=["_async_feature_tool"]
                )._async_feature_tool("unknown_feature", {})
            )
            assert "error" in result
            assert "Unknown feature type" in result["error"]
        finally:
            loop.close()
