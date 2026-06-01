"""
Unit tests for StateManager.

Tests agent state persistence, memory node discovery, orphaned agent
detection/cleanup, and graceful shutdown signal handling.
"""

import pytest
from unittest.mock import MagicMock, patch, ANY

from mcp_server.state_manager import (
    StateManager,
    get_state_manager,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_vault():
    """Create a fully mocked ObsidianVault."""
    vault = MagicMock()
    vault.list_nodes = MagicMock(return_value=[])
    vault.read_node = MagicMock(side_effect=FileNotFoundError("Not found"))
    vault.write_node = MagicMock(
        return_value={"path": "Global/Agent_State_Backup.md", "status": "written"}
    )
    vault.update_frontmatter = MagicMock(
        return_value={"path": "Global/Agent_State_Backup.md", "status": "updated"}
    )
    return vault


@pytest.fixture
def mock_spawner():
    """Create a mocked AgentSpawner."""
    spawner = MagicMock()
    spawner.get_active_agents = MagicMock(return_value=[])
    return spawner


@pytest.fixture
def state_manager(mock_vault, mock_spawner):
    """Create a StateManager with mocked vault and spawner."""
    with (
        patch("mcp_server.state_manager.get_vault", return_value=mock_vault),
        patch("mcp_server.state_manager.get_spawner", return_value=mock_spawner),
    ):
        sm = StateManager()
        yield sm


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------


class TestStateManagerInit:
    """Test StateManager initialization."""

    @pytest.mark.unit
    def test_init_creates_vault_and_spawner(self, state_manager, mock_vault, mock_spawner):
        """Should store vault and spawner instances."""
        assert state_manager.vault is mock_vault
        assert state_manager.spawner is mock_spawner
        assert state_manager._shutdown_requested is False


# ---------------------------------------------------------------------------
# save_state
# ---------------------------------------------------------------------------


class TestSaveState:
    """Test saving agent state to vault."""

    @pytest.mark.unit
    def test_save_no_active_agents(self, state_manager, mock_spawner, mock_vault):
        """Should skip saving when no active agents exist."""
        mock_spawner.get_active_agents.return_value = []

        state_manager.save_state()

        mock_vault.write_node.assert_not_called()

    @pytest.mark.unit
    def test_save_with_active_agents(self, state_manager, mock_spawner, mock_vault):
        """Should save state with active agent details."""
        mock_spawner.get_active_agents.return_value = [
            {"agent_id": "agent-001", "pid": 12345, "status": "running"},
            {"agent_id": "agent-002", "pid": 12346, "status": "running"},
        ]

        # Each agent has a memory node
        mock_vault.list_nodes.side_effect = None
        mock_vault.list_nodes.return_value = [
            "Runs/Agent_001.md",
            "Runs/Agent_002.md",
        ]

        def read_node_side_effect(path):
            nodes = {
                "Runs/Agent_001.md": {
                    "frontmatter": {"agent_id": "agent-001"},
                    "content": "# Agent 001 Log",
                    "path": "Runs/Agent_001.md",
                },
                "Runs/Agent_002.md": {
                    "frontmatter": {"agent_id": "agent-002"},
                    "content": "# Agent 002 Log",
                    "path": "Runs/Agent_002.md",
                },
            }
            return nodes.get(path, {"frontmatter": {}, "content": ""})

        mock_vault.read_node.side_effect = read_node_side_effect

        state_manager.save_state()

        # Should have written the backup node
        mock_vault.write_node.assert_called_once()
        call_args = mock_vault.write_node.call_args
        assert call_args[0][0] == "Global/Agent_State_Backup.md"

        # Frontmatter should have the right keys
        frontmatter = call_args[1]["frontmatter"]
        assert frontmatter["agent_count"] == 2
        assert "saved_at" in frontmatter
        assert "status" in frontmatter

    @pytest.mark.unit
    def test_save_with_memory_node_lookup_failure(self, state_manager, mock_spawner, mock_vault):
        """Should handle memory node lookup failures gracefully."""
        mock_spawner.get_active_agents.return_value = [
            {"agent_id": "agent-001", "pid": 12345, "status": "running"},
        ]

        # list_nodes raises an exception
        mock_vault.list_nodes.side_effect = Exception("Vault unavailable")

        # Should not raise — the exception is caught
        state_manager.save_state()

        # write_node should still be called (agent entry without memory node)
        mock_vault.write_node.assert_called_once()

    @pytest.mark.unit
    def test_save_handles_exception_gracefully(self, state_manager, mock_spawner, mock_vault):
        """Should catch and log exceptions during save."""
        mock_spawner.get_active_agents.side_effect = RuntimeError("Spawner crashed")

        # Should not propagate the exception
        state_manager.save_state()


# ---------------------------------------------------------------------------
# restore_state
# ---------------------------------------------------------------------------


class TestRestoreState:
    """Test restoring agent state from vault."""

    @pytest.mark.unit
    def test_restore_no_backup(self, state_manager, mock_vault):
        """Should return empty list when no backup exists."""
        mock_vault.read_node.side_effect = FileNotFoundError("Not found")

        # Also patch STATE_BACKUP_PATH.exists to return False
        with patch("mcp_server.state_manager.STATE_BACKUP_PATH") as mock_path:
            mock_path.exists.return_value = False
            result = state_manager.restore_state()

        assert result == []

    @pytest.mark.unit
    def test_restore_orphans_found(self, state_manager, mock_vault):
        """Should return orphaned agents from backup."""
        backup_content = """
### agent-001
- **PID**: 12345
- **Status**: running
- **Memory Node**: Runs/Agent_001.md
- **Saved At**: 2025-01-01T00:00:00Z

### agent-002
- **PID**: 12346
- **Status**: running
- **Memory Node**: Unknown
- **Saved At**: 2025-01-01T00:00:00Z
"""
        # Clear side_effect set by fixture so return_value is used instead
        mock_vault.read_node.side_effect = None
        mock_vault.read_node.return_value = {
            "frontmatter": {
                "status": "saved",
                "agent_count": 2,
            },
            "content": backup_content,
        }
        mock_vault.update_frontmatter.return_value = {"status": "updated"}

        with patch("mcp_server.state_manager.STATE_BACKUP_PATH") as mock_path:
            mock_path.exists.return_value = True
            result = state_manager.restore_state()

        assert len(result) == 2
        assert result[0]["agent_id"] == "agent-001"
        assert result[0]["pid"] == 12345
        assert result[0]["memory_node"] == "Runs/Agent_001.md"
        assert result[1]["agent_id"] == "agent-002"
        assert result[1]["memory_node"] is None

        # Should mark the backup as restored
        mock_vault.update_frontmatter.assert_any_call(
            "Global/Agent_State_Backup.md",
            {"status": "restored", "restored_at": ANY},
        )

    @pytest.mark.unit
    def test_restore_marks_memory_nodes_orphaned(self, state_manager, mock_vault):
        """Should mark each agent's memory node as orphaned."""
        backup_content = """
### agent-001
- **PID**: 12345
- **Status**: running
- **Memory Node**: Runs/Agent_001.md
- **Saved At**: 2025-01-01T00:00:00Z
"""
        # Clear side_effect set by fixture so return_value is used instead
        mock_vault.read_node.side_effect = None
        mock_vault.read_node.return_value = {
            "frontmatter": {"status": "saved", "agent_count": 1},
            "content": backup_content,
        }

        with patch("mcp_server.state_manager.STATE_BACKUP_PATH") as mock_path:
            mock_path.exists.return_value = True
            state_manager.restore_state()

        # Should have called update_frontmatter for the memory node
        call_found = False
        for c in mock_vault.update_frontmatter.call_args_list:
            if c[0][0] == "Runs/Agent_001.md":
                args = c[0][1]
                assert args["status"] == "orphaned"
                assert "orphaned_at" in args
                call_found = True
                break
        assert call_found, "Memory node was not marked as orphaned"

    @pytest.mark.unit
    def test_restore_already_restored(self, state_manager, mock_vault):
        """Should return empty list when backup was already restored."""
        mock_vault.read_node.side_effect = None
        mock_vault.read_node.return_value = {
            "frontmatter": {"status": "restored"},
            "content": "",
        }

        with patch("mcp_server.state_manager.STATE_BACKUP_PATH") as mock_path:
            mock_path.exists.return_value = True
            result = state_manager.restore_state()

        assert result == []

    @pytest.mark.unit
    def test_restore_read_exception(self, state_manager, mock_vault):
        """Should handle exceptions during restore gracefully."""
        mock_vault.read_node.side_effect = Exception("Corrupted file")

        with patch("mcp_server.state_manager.STATE_BACKUP_PATH") as mock_path:
            mock_path.exists.return_value = True
            result = state_manager.restore_state()

        assert result == []


# ---------------------------------------------------------------------------
# _find_agent_memory_node
# ---------------------------------------------------------------------------


class TestFindAgentMemoryNode:
    """Test finding agent memory nodes."""

    @pytest.mark.unit
    def test_find_existing_agent(self, state_manager, mock_vault):
        """Should find memory node for an existing agent."""
        mock_vault.list_nodes.return_value = [
            "Runs/Agent_001.md",
            "Runs/Agent_002.md",
        ]

        def read_node_side_effect(path):
            nodes = {
                "Runs/Agent_001.md": {
                    "frontmatter": {"agent_id": "agent-001"},
                },
                "Runs/Agent_002.md": {
                    "frontmatter": {"agent_id": "agent-002"},
                },
            }
            return nodes.get(path, {"frontmatter": {}})

        mock_vault.read_node.side_effect = read_node_side_effect

        result = state_manager._find_agent_memory_node("agent-002")

        assert result == "Runs/Agent_002.md"

    @pytest.mark.unit
    def test_find_nonexistent_agent(self, state_manager, mock_vault):
        """Should return None for a non-existent agent."""
        mock_vault.list_nodes.return_value = ["Runs/Agent_001.md"]
        mock_vault.read_node.return_value = {"frontmatter": {"agent_id": "other-agent"}}

        result = state_manager._find_agent_memory_node("ghost-agent")

        assert result is None

    @pytest.mark.unit
    def test_find_empty_nodes_list(self, state_manager, mock_vault):
        """Should return None when no nodes exist."""
        mock_vault.list_nodes.return_value = []

        result = state_manager._find_agent_memory_node("agent-001")

        assert result is None

    @pytest.mark.unit
    def test_find_skips_unreadable_nodes(self, state_manager, mock_vault):
        """Should skip nodes that cannot be read and continue scanning."""
        mock_vault.list_nodes.return_value = [
            "Runs/Broken.md",
            "Runs/Agent_001.md",
        ]

        call_count = 0

        def read_node_side_effect(path):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Corrupted file")
            return {"frontmatter": {"agent_id": "agent-001"}}

        mock_vault.read_node.side_effect = read_node_side_effect

        result = state_manager._find_agent_memory_node("agent-001")

        assert result == "Runs/Agent_001.md"


# ---------------------------------------------------------------------------
# check_orphaned_agents
# ---------------------------------------------------------------------------


class TestCheckOrphanedAgents:
    """Test checking for orphaned agents."""

    @pytest.mark.unit
    def test_no_orphans(self, state_manager, mock_vault):
        """Should return empty list when no orphans exist."""
        mock_vault.list_nodes.return_value = ["Runs/Agent_001.md"]
        mock_vault.read_node.return_value = {
            "frontmatter": {"status": "active", "agent_id": "agent-001"},
        }

        result = state_manager.check_orphaned_agents()

        assert result == []

    @pytest.mark.unit
    def test_finds_orphaned_agents(self, state_manager, mock_vault):
        """Should find and return orphaned agents."""
        mock_vault.list_nodes.return_value = [
            "Runs/Orphaned_001.md",
            "Runs/Active_001.md",
        ]

        def read_node_side_effect(path):
            nodes = {
                "Runs/Orphaned_001.md": {
                    "frontmatter": {
                        "status": "orphaned",
                        "agent_id": "agent-orphan-1",
                        "orphaned_at": "2025-01-01T00:00:00Z",
                    },
                },
                "Runs/Active_001.md": {
                    "frontmatter": {
                        "status": "active",
                        "agent_id": "agent-active-1",
                    },
                },
            }
            return nodes.get(path, {"frontmatter": {}})

        mock_vault.read_node.side_effect = read_node_side_effect

        result = state_manager.check_orphaned_agents()

        assert len(result) == 1
        assert result[0]["agent_id"] == "agent-orphan-1"
        assert result[0]["memory_node"] == "Runs/Orphaned_001.md"

    @pytest.mark.unit
    def test_orphaned_check_list_error(self, state_manager, mock_vault):
        """Should handle list_nodes errors gracefully."""
        mock_vault.list_nodes.side_effect = Exception("Permission denied")

        result = state_manager.check_orphaned_agents()

        assert result == []


# ---------------------------------------------------------------------------
# cleanup_orphaned_agents
# ---------------------------------------------------------------------------


class TestCleanupOrphanedAgents:
    """Test cleaning up orphaned agents."""

    @pytest.mark.unit
    def test_cleanup_all_orphans(self, state_manager, mock_vault):
        """Should clean up all orphaned agents."""
        mock_vault.list_nodes.return_value = ["Runs/Orphan_001.md"]
        # Clear side_effect set by fixture so return_value is used instead
        mock_vault.read_node.side_effect = None
        mock_vault.read_node.return_value = {
            "frontmatter": {
                "status": "orphaned",
                "agent_id": "agent-orphan-1",
                "orphaned_at": "2025-01-01T00:00:00Z",
            },
        }

        count = state_manager.cleanup_orphaned_agents()

        assert count == 1
        mock_vault.update_frontmatter.assert_called_once()
        call_args = mock_vault.update_frontmatter.call_args
        assert call_args[0][0] == "Runs/Orphan_001.md"
        assert call_args[0][1]["status"] == "terminated"

    @pytest.mark.unit
    def test_cleanup_specific_orphans(self, state_manager, mock_vault):
        """Should clean up only specified orphaned agents."""
        mock_vault.list_nodes.return_value = [
            "Runs/Orphan_001.md",
            "Runs/Orphan_002.md",
        ]

        def read_node_side_effect(path):
            nodes = {
                "Runs/Orphan_001.md": {
                    "frontmatter": {
                        "status": "orphaned",
                        "agent_id": "agent-a",
                        "orphaned_at": "2025-01-01T00:00:00Z",
                    },
                },
                "Runs/Orphan_002.md": {
                    "frontmatter": {
                        "status": "orphaned",
                        "agent_id": "agent-b",
                        "orphaned_at": "2025-01-01T00:00:00Z",
                    },
                },
            }
            return nodes.get(path, {"frontmatter": {}})

        mock_vault.read_node.side_effect = read_node_side_effect

        count = state_manager.cleanup_orphaned_agents(agent_ids=["agent-a"])

        assert count == 1
        # Only agent-a should have been updated
        mock_vault.update_frontmatter.assert_called_once()
        assert mock_vault.update_frontmatter.call_args[0][0] == "Runs/Orphan_001.md"

    @pytest.mark.unit
    def test_cleanup_no_orphans(self, state_manager, mock_vault):
        """Should return 0 when no orphans exist."""
        mock_vault.list_nodes.return_value = []
        mock_vault.read_node.side_effect = FileNotFoundError("Not found")

        count = state_manager.cleanup_orphaned_agents()

        assert count == 0


# ---------------------------------------------------------------------------
# Signal handlers
# ---------------------------------------------------------------------------


class TestSignalHandlers:
    """Test signal handler registration and behavior."""

    @pytest.mark.unit
    def test_register_signal_handlers(self, state_manager):
        """Should register SIGTERM, SIGINT and atexit handlers."""
        with (
            patch("mcp_server.state_manager.signal.signal") as mock_signal,
            patch("mcp_server.state_manager.atexit.register") as mock_atexit,
        ):
            state_manager.register_signal_handlers()

            assert mock_signal.call_count == 2
            mock_atexit.assert_called_once()

    @pytest.mark.unit
    def test_sigterm_triggers_save(self, state_manager):
        """SIGTERM handler should set shutdown flag and call save."""
        with patch.object(state_manager, "save_state") as mock_save:
            state_manager._handle_sigterm(15, None)

            assert state_manager._shutdown_requested is True
            mock_save.assert_called_once()

    @pytest.mark.unit
    def test_sigint_triggers_save(self, state_manager):
        """SIGINT handler should set shutdown flag and call save."""
        with patch.object(state_manager, "save_state") as mock_save:
            state_manager._handle_sigint(2, None)

            assert state_manager._shutdown_requested is True
            mock_save.assert_called_once()

    @pytest.mark.unit
    def test_cleanup_skips_save_if_already_shutdown(self, state_manager):
        """Cleanup should skip save if shutdown was already requested."""
        state_manager._shutdown_requested = True
        with patch.object(state_manager, "save_state") as mock_save:
            state_manager._cleanup()

            mock_save.assert_not_called()

    @pytest.mark.unit
    def test_cleanup_saves_if_not_shutdown(self, state_manager):
        """Cleanup should save state if shutdown was not already requested."""
        state_manager._shutdown_requested = False
        with patch.object(state_manager, "save_state") as mock_save:
            state_manager._cleanup()

            mock_save.assert_called_once()


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------


class TestStateManagerSingleton:
    """Test the get_state_manager singleton."""

    @pytest.mark.unit
    def test_singleton_returns_same_instance(self):
        """Should return the same StateManager on repeated calls."""
        import mcp_server.state_manager as sm_mod

        sm_mod._state_manager_instance = None

        with (
            patch("mcp_server.state_manager.get_vault"),
            patch("mcp_server.state_manager.get_spawner"),
        ):
            s1 = get_state_manager()
            s2 = get_state_manager()

        assert s1 is s2
        assert isinstance(s1, StateManager)
