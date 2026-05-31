"""
Unit tests for AgentSpawner.
Uses mocked subprocess to avoid spawning real processes.
"""

import pytest
import os
import sys
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
from datetime import datetime

from mcp_server.tools import AgentSpawner, ObsidianVault, VaultError


class TestAgentSpawnerBasic:
    """Test basic AgentSpawner operations."""

    def test_spawn_agent_ui_explorer(self, vault, agent_spawner):
        """Should spawn a UI explorer agent."""
        with patch("subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.pid = 12345
            mock_process.poll.return_value = None
            mock_popen.return_value = mock_process

            result = agent_spawner.spawn_agent(
                role="ui_explorer",
                objective="Test homepage at https://example.com",
                memory_node="Runs/Homepage_Test.md",
            )

            assert result["status"] == "active"
            assert result["role"] == "ui_explorer"
            assert result["pid"] == 12345
            assert "agent_id" in result
            assert result["memory_node"] == "Runs/Homepage_Test.md"

            # Verify memory node was created
            node = vault.read_node("Runs/Homepage_Test.md")
            assert node["frontmatter"]["agent_role"] == "ui_explorer"
            assert node["frontmatter"]["status"] == "active"
            assert node["frontmatter"]["objective"] == "Test homepage at https://example.com"

    def test_spawn_agent_data_validator(self, vault, agent_spawner):
        """Should spawn a data validator agent."""
        with patch("subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.pid = 12346
            mock_process.poll.return_value = None
            mock_popen.return_value = mock_process

            result = agent_spawner.spawn_agent(
                role="data_validator",
                objective="Validate API at https://api.example.com",
                memory_node="Runs/API_Test.md",
            )

            assert result["status"] == "active"
            assert result["role"] == "data_validator"
            assert result["pid"] == 12346

    def test_spawn_agent_invalid_role(self, agent_spawner):
        """Should handle invalid agent roles."""
        with patch("subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.pid = 12347
            mock_popen.return_value = mock_process

            result = agent_spawner.spawn_agent(
                role="invalid_role", objective="Do something", memory_node="Runs/Invalid.md"
            )

            # Should still spawn a fallback process
            assert result["status"] == "active"
            assert "agent_id" in result

    def test_spawn_agent_worker_not_found(self, agent_spawner):
        """Should handle missing worker scripts gracefully."""
        with patch("os.path.exists", return_value=False):
            result = agent_spawner.spawn_agent(
                role="ui_explorer", objective="Test something", memory_node="Runs/Test.md"
            )

            assert result["status"] == "error"
            assert "Worker script not found" in result["error"]


class TestAgentSpawnerLifecycle:
    """Test agent lifecycle management."""

    def test_terminate_agent(self, vault, agent_spawner):
        """Should terminate an active agent."""
        # Spawn an agent first
        with patch("subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.pid = 12345
            mock_process.poll.return_value = None
            mock_process.wait.return_value = 0
            mock_popen.return_value = mock_process

            spawn_result = agent_spawner.spawn_agent(
                role="ui_explorer", objective="Test", memory_node="Runs/Test.md"
            )
            agent_id = spawn_result["agent_id"]

        # Now terminate it
        result = agent_spawner.terminate_agent(agent_id)

        assert result["status"] == "terminated"
        assert result["agent_id"] == agent_id
        assert "terminated_at" in result

        # Verify memory node updated
        node = vault.read_node("Runs/Test.md")
        assert node["frontmatter"]["status"] == "terminated"

    def test_terminate_nonexistent_agent(self, agent_spawner):
        """Should handle terminating non-existent agents."""
        result = agent_spawner.terminate_agent("nonexistent-agent")
        assert "error" in result
        assert "not found" in result["error"]

    def test_get_active_agents(self, agent_spawner):
        """Should list active agents."""
        with patch("subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.pid = 12345
            mock_process.poll.return_value = None
            mock_popen.return_value = mock_process

            agent_spawner.spawn_agent(
                role="ui_explorer", objective="Test 1", memory_node="Runs/Test1.md"
            )
            agent_spawner.spawn_agent(
                role="data_validator", objective="Test 2", memory_node="Runs/Test2.md"
            )

        agents = agent_spawner.get_active_agents()
        assert len(agents) == 2
        assert all(a["status"] == "running" for a in agents)

    def test_get_active_agents_exited(self, agent_spawner):
        """Should detect exited agents."""
        with patch("subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.pid = 12345
            mock_process.poll.return_value = 0  # Exited
            mock_popen.return_value = mock_process

            agent_spawner.spawn_agent(
                role="ui_explorer", objective="Test", memory_node="Runs/Test.md"
            )

        agents = agent_spawner.get_active_agents()
        assert len(agents) == 1
        assert agents[0]["status"] == "exited"


class TestAgentSpawnerEnvironment:
    """Test environment variable setup for spawned agents."""

    def test_spawn_sets_environment(self, agent_spawner):
        """Should set correct environment variables for agent."""
        with patch("subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.pid = 12345
            mock_process.poll.return_value = None
            mock_popen.return_value = mock_process

            agent_spawner.spawn_agent(
                role="ui_explorer", objective="Test", memory_node="Runs/Test.md"
            )

            # Check that Popen was called with correct env
            call_args = mock_popen.call_args
            env = call_args[1].get("env", call_args[0][1] if len(call_args[0]) > 1 else {})

            assert env.get("AGENT_ROLE") == "ui_explorer"
            assert env.get("AGENT_OBJECTIVE") == "Test"
            assert "AGENT_ID" in env
            assert "PYTHONPATH" in env


class TestAgentSpawnerCleanup:
    """Test cleanup and error handling."""

    def test_spawn_creates_log_file(self, vault, agent_spawner):
        """Should create worker log file."""
        with patch("subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.pid = 12345
            mock_process.poll.return_value = None
            mock_popen.return_value = mock_process

            result = agent_spawner.spawn_agent(
                role="ui_explorer", objective="Test", memory_node="Runs/Test.md"
            )

            # Verify Runs directory exists
            runs_dir = vault.vault_path / "Runs"
            assert runs_dir.exists()
