"""
State persistence for Vectra QA.

Handles graceful shutdown, state backup, and restoration.
Ensures agents can survive MCP server restarts.
"""

import os
import signal
import atexit
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import structlog

from mcp_server.tools import get_vault, get_spawner

logger = structlog.get_logger()

VAULT_PATH = Path(os.getenv("OBSIDIAN_VAULT_PATH", "/app/obsidian_vault"))
STATE_BACKUP_PATH = VAULT_PATH / "Global" / "Agent_State_Backup.md"


class StateManager:
    """Manages agent state persistence across restarts."""

    def __init__(self):
        self.vault = get_vault()
        self.spawner = get_spawner()
        self._shutdown_requested = False

    def register_signal_handlers(self):
        """Register handlers for graceful shutdown."""
        signal.signal(signal.SIGTERM, self._handle_sigterm)
        signal.signal(signal.SIGINT, self._handle_sigint)
        atexit.register(self._cleanup)
        logger.info("signal_handlers_registered")

    def _handle_sigterm(self, signum, frame):
        """Handle SIGTERM - initiate graceful shutdown."""
        logger.info("sigterm_received", signal=signum)
        self._shutdown_requested = True
        self.save_state()

    def _handle_sigint(self, signum, frame):
        """Handle SIGINT (Ctrl+C) - initiate graceful shutdown."""
        logger.info("sigint_received", signal=signum)
        self._shutdown_requested = True
        self.save_state()

    def _cleanup(self):
        """Cleanup function called at exit."""
        if not self._shutdown_requested:
            logger.info("atexit_cleanup")
            self.save_state()

    def save_state(self):
        """Save current agent state to vault."""
        try:
            agents = self.spawner.get_active_agents()

            if not agents:
                logger.info("no_active_agents_to_save")
                return

            state = {
                "saved_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z",
                "agent_count": len(agents),
                "agents": [],
            }

            for agent in agents:
                agent_id = agent["agent_id"]

                # Find memory node for this agent
                memory_node = self._find_agent_memory_node(agent_id)

                state["agents"].append(
                    {
                        "agent_id": agent_id,
                        "pid": agent["pid"],
                        "status": agent["status"],
                        "memory_node": memory_node,
                        "saved_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z",
                    }
                )

            # Write state to vault
            content = f"""# Agent State Backup

## Saved At
{state['saved_at']}

## Active Agents
{len(state['agents'])} agent(s) were active when the server shut down.

## Agent Details
"""
            for agent in state["agents"]:
                content += f"""
### {agent['agent_id']}
- **PID**: {agent['pid']}
- **Status**: {agent['status']}
- **Memory Node**: {agent['memory_node'] or 'Unknown'}
- **Saved At**: {agent['saved_at']}
"""

            self.vault.write_node(
                "Global/Agent_State_Backup.md",
                content=content,
                frontmatter={
                    "saved_at": state["saved_at"],
                    "agent_count": len(state["agents"]),
                    "status": "saved",
                    "shutdown_type": "graceful" if self._shutdown_requested else "unexpected",
                },
            )

            logger.info(
                "state_saved", agent_count=len(state["agents"]), path=str(STATE_BACKUP_PATH)
            )

        except Exception as e:
            logger.error("state_save_error", error=str(e))

    def restore_state(self) -> List[Dict[str, Any]]:
        """Restore agent state from vault. Returns orphaned agents."""
        try:
            if not STATE_BACKUP_PATH.exists():
                logger.info("no_state_backup_found")
                return []

            node = self.vault.read_node("Global/Agent_State_Backup.md")
            frontmatter = node["frontmatter"]

            if frontmatter.get("status") != "saved":
                logger.info("state_already_restored_or_not_saved")
                return []

            agent_count = frontmatter.get("agent_count", 0)
            logger.info("restoring_state", agent_count=agent_count)

            orphaned = []

            # Parse agent details from content
            import re

            agent_sections = re.findall(
                r"### (.*?)\n.*?\*\*PID\*\*: (\d+).*?\*\*Status\*\*: (\w+).*?\*\*Memory Node\*\*: (.*?)\n",
                node["content"],
                re.DOTALL,
            )

            for match in agent_sections:
                agent_id, pid, status, memory_node = match
                memory_node = memory_node.strip()
                if memory_node == "Unknown":
                    memory_node = None

                orphaned.append(
                    {
                        "agent_id": agent_id.strip(),
                        "pid": int(pid),
                        "status": status.strip(),
                        "memory_node": memory_node,
                    }
                )

                # Mark agent's memory node as orphaned
                if memory_node:
                    try:
                        self.vault.update_frontmatter(
                            memory_node,
                            {
                                "status": "orphaned",
                                "orphaned_at": datetime.now(timezone.utc).strftime(
                                    "%Y-%m-%dT%H:%M:%S"
                                )
                                + "Z",
                                "note": "Agent process lost during server restart",
                            },
                        )
                    except Exception as e:
                        logger.warning("failed_to_mark_orphaned", agent_id=agent_id, error=str(e))

            # Mark backup as restored
            self.vault.update_frontmatter(
                "Global/Agent_State_Backup.md",
                {
                    "status": "restored",
                    "restored_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z",
                },
            )

            logger.info("state_restored", orphaned_count=len(orphaned))
            return orphaned

        except FileNotFoundError:
            logger.info("no_state_backup_found")
            return []
        except Exception as e:
            logger.error("state_restore_error", error=str(e))
            return []

    def _find_agent_memory_node(self, agent_id: str) -> Optional[str]:
        """Find memory node for an agent by ID."""
        try:
            for node_path in self.vault.list_nodes("Runs"):
                try:
                    node = self.vault.read_node(node_path)
                    if node["frontmatter"].get("agent_id") == agent_id:
                        return node_path
                except Exception:
                    continue
        except Exception:
            pass
        return None

    def check_orphaned_agents(self) -> List[Dict[str, Any]]:
        """Check for orphaned agents and offer cleanup."""
        orphaned = []

        try:
            for node_path in self.vault.list_nodes("Runs"):
                try:
                    node = self.vault.read_node(node_path)
                    frontmatter = node["frontmatter"]

                    if frontmatter.get("status") == "orphaned":
                        orphaned.append(
                            {
                                "agent_id": frontmatter.get("agent_id", "unknown"),
                                "memory_node": node_path,
                                "orphaned_at": frontmatter.get("orphaned_at", "unknown"),
                            }
                        )
                except Exception:
                    continue
        except Exception:
            pass

        return orphaned

    def cleanup_orphaned_agents(self, agent_ids: Optional[List[str]] = None):
        """Clean up orphaned agents. If agent_ids is None, clean all."""
        orphaned = self.check_orphaned_agents()

        cleaned = 0
        for agent in orphaned:
            if agent_ids is None or agent["agent_id"] in agent_ids:
                try:
                    # Update status to terminated
                    self.vault.update_frontmatter(
                        agent["memory_node"],
                        {
                            "status": "terminated",
                            "terminated_at": datetime.now(timezone.utc).strftime(
                                "%Y-%m-%dT%H:%M:%S"
                            )
                            + "Z",
                            "note": "Cleaned up orphaned agent",
                        },
                    )
                    cleaned += 1
                except Exception as e:
                    logger.warning("cleanup_failed", agent_id=agent["agent_id"], error=str(e))

        logger.info("orphaned_agents_cleaned", count=cleaned)
        return cleaned


# Global state manager instance
_state_manager_instance: Optional[StateManager] = None


def get_state_manager() -> StateManager:
    """Get or create the StateManager instance."""
    global _state_manager_instance
    if _state_manager_instance is None:
        _state_manager_instance = StateManager()
    return _state_manager_instance
