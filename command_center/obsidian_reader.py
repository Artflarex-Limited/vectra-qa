"""
Obsidian Vault Reader for Command Center UI
Provides real-time file watching and SSE updates.
"""

import os
import yaml
import time
from pathlib import Path
from typing import Dict, Any, List, Optional
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

VAULT_PATH = Path(os.getenv("OBSIDIAN_VAULT_PATH", "/app/obsidian_vault"))


class ObsidianNode:
    """Represents an Obsidian markdown node with parsed frontmatter."""

    def __init__(self, path: str, frontmatter: Dict, content: str, mtime: float):
        self.path = path
        self.frontmatter = frontmatter
        self.content = content
        self.mtime = mtime

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "frontmatter": self.frontmatter,
            "content_preview": self.content[:500] if self.content else "",
            "last_modified": self.mtime,
        }


class VaultWatcher(FileSystemEventHandler):
    """Watchdog handler for Obsidian vault file changes."""

    def __init__(self):
        self._callbacks = []
        self._cache: Dict[str, ObsidianNode] = {}

    def on_modified(self, event):
        if event.is_directory:
            return
        if event.src_path.endswith(".md"):
            rel_path = os.path.relpath(event.src_path, VAULT_PATH)
            self._notify_change(rel_path)

    def on_created(self, event):
        if event.is_directory:
            return
        if event.src_path.endswith(".md"):
            rel_path = os.path.relpath(event.src_path, VAULT_PATH)
            self._notify_change(rel_path)

    def add_callback(self, callback):
        self._callbacks.append(callback)

    def _notify_change(self, path: str):
        for callback in self._callbacks:
            try:
                callback(path)
            except Exception:
                pass


class ObsidianReader:
    """Reads and monitors Obsidian vault files for the Command Center."""

    def __init__(self, vault_path: Path):
        self.vault_path = vault_path
        self.watcher = VaultWatcher()
        self.observer = Observer()
        self._cache: Dict[str, ObsidianNode] = {}

    def start_watching(self):
        """Start file system watcher."""
        self.observer.schedule(self.watcher, str(self.vault_path), recursive=True)
        self.observer.start()

    def stop_watching(self):
        """Stop file system watcher."""
        self.observer.stop()
        self.observer.join()

    def read_node(self, node_path: str) -> Optional[ObsidianNode]:
        """Read and parse a single Obsidian node."""
        file_path = self.vault_path / node_path
        if not file_path.exists():
            return None

        try:
            stat = file_path.stat()
            content = file_path.read_text(encoding="utf-8")

            # Parse YAML frontmatter
            frontmatter: Dict[str, Any] = {}
            body = content

            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    try:
                        frontmatter = yaml.safe_load(parts[1]) or {}
                        body = parts[2].strip()
                    except yaml.YAMLError:
                        pass

            node = ObsidianNode(node_path, frontmatter, body, stat.st_mtime)
            self._cache[node_path] = node
            return node

        except Exception as e:
            print(f"Error reading {node_path}: {e}")
            return None

    def get_global_nodes(self) -> Dict[str, Optional[ObsidianNode]]:
        """Read all global memory nodes."""
        global_dir = self.vault_path / "Global"
        nodes = {}

        if global_dir.exists():
            for file_path in global_dir.glob("*.md"):
                rel_path = str(file_path.relative_to(self.vault_path))
                nodes[file_path.stem] = self.read_node(rel_path)

        return nodes

    def get_run_nodes(self) -> List[ObsidianNode]:
        """Read all test run nodes."""
        runs_dir = self.vault_path / "Runs"
        nodes = []

        if runs_dir.exists():
            for file_path in runs_dir.rglob("*.md"):
                rel_path = str(file_path.relative_to(self.vault_path))
                node = self.read_node(rel_path)
                if node:
                    nodes.append(node)

        return nodes

    def get_active_agents(self) -> List[Dict[str, Any]]:
        """Extract active agent information from all nodes."""
        agents = []

        # Check global nodes
        for name in ["Test_Run_Master", "UI_State_Log", "Data_Validation_Log"]:
            node = self.read_node(f"Global/{name}.md")
            if node and node.frontmatter:
                role = node.frontmatter.get("agent_role")
                status = node.frontmatter.get("status")

                if role and status in ["active", "spawned", "running"]:
                    agents.append(
                        {
                            "agent_id": node.frontmatter.get("agent_id", "unknown"),
                            "role": role,
                            "status": status,
                            "objective": node.frontmatter.get("objective", ""),
                            "node_path": node.path,
                            "last_action": node.frontmatter.get("last_action", ""),
                            "start_time": node.frontmatter.get("start_time", ""),
                            "progress_percent": node.frontmatter.get("progress_percent", 0),
                            "screenshots": node.frontmatter.get("screenshots", []),
                            "timestamp": node.frontmatter.get("timestamp", ""),
                        }
                    )

        # Check run nodes
        for node in self.get_run_nodes():
            if node.frontmatter:
                role = node.frontmatter.get("agent_role")
                status = node.frontmatter.get("status")

                if role and status in ["active", "spawned", "running"]:
                    agents.append(
                        {
                            "agent_id": node.frontmatter.get("agent_id", "unknown"),
                            "role": role,
                            "status": status,
                            "objective": node.frontmatter.get("objective", ""),
                            "node_path": node.path,
                            "last_action": node.frontmatter.get("last_action", ""),
                            "start_time": node.frontmatter.get("start_time", ""),
                            "progress_percent": node.frontmatter.get("progress_percent", 0),
                            "screenshots": node.frontmatter.get("screenshots", []),
                            "timestamp": node.frontmatter.get("timestamp", ""),
                        }
                    )

        return agents

    def get_orchestrator_status(self) -> Dict[str, Any]:
        """Get current orchestrator status from Test_Run_Master."""
        node = self.read_node("Global/Test_Run_Master.md")
        if not node:
            return {"error": "Test_Run_Master not found"}

        fm = node.frontmatter
        return {
            "status": fm.get("status", "unknown"),
            "phase": fm.get("phase", "unknown"),
            "overall_result": fm.get("overall_result", "pending"),
            "metrics": {
                "pass": fm.get("pass_count", 0),
                "fail": fm.get("fail_count", 0),
                "skip": fm.get("skip_count", 0),
            },
            "active_agents": fm.get("active_agents", []),
            "completed_agents": fm.get("completed_agents", []),
            "last_updated": fm.get("modified", ""),
            "thoughts": self._extract_orchestrator_thoughts(node.content),
        }

    def _extract_orchestrator_thoughts(self, content: str) -> List[str]:
        """Extract orchestrator notes/thoughts from content."""
        thoughts = []
        lines = content.split("\n")
        in_notes = False

        for line in lines:
            if "##" in line and "Notes" in line:
                in_notes = True
                continue
            if in_notes:
                if line.startswith("##") and "Notes" not in line:
                    in_notes = False
                    continue
                if line.strip().startswith("-") or line.strip().startswith("*"):
                    thoughts.append(line.strip().lstrip("- ").lstrip("* "))

        return thoughts[-10:]  # Last 10 thoughts


# Global reader instance
reader = ObsidianReader(VAULT_PATH)
reader.start_watching()


if __name__ == "__main__":
    import time

    print("Vault watcher started. Monitoring for changes...")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        reader.stop_watching()
        print("Vault watcher stopped.")
