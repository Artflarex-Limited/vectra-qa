"""
MCP Tools for Obsidian Vault Integration
Provides tools for agents to read, write, and interlink Markdown files in the Obsidian Vault.
"""

import os
import re
import yaml
import uuid
import asyncio
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, cast

import structlog
from filelock import FileLock, Timeout
from tenacity import retry, stop_after_attempt, wait_exponential

# Configuration - use environment variable or default
VAULT_PATH = Path(os.getenv("OBSIDIAN_VAULT_PATH", "/app/obsidian_vault"))
AGENTS_DIR = Path(os.getenv("AGENTS_DIR", "/app/agents"))

logger = structlog.get_logger()


class VaultError(Exception):
    """Base exception for vault operations."""

    pass


class VaultCorruptionError(VaultError):
    """Raised when vault file is corrupted."""

    pass


class ObsidianVault:
    """Handles all Obsidian Vault file operations with file locking and atomic writes."""

    def __init__(self, vault_path: Path):
        self.vault_path = vault_path
        self.vault_path.mkdir(parents=True, exist_ok=True)

    def _get_lock_path(self, file_path: Path) -> Path:
        """Get the lock file path for a given file."""
        return Path(str(file_path) + ".lock")

    def _atomic_write(self, file_path: Path, content: str) -> None:
        """Write content atomically using a temporary file and rename."""
        # Ensure parent directory exists
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Write to temporary file in the same directory
        temp_fd, temp_path = tempfile.mkstemp(
            dir=file_path.parent, prefix=f".tmp_{file_path.name}_"
        )
        try:
            with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
                f.write(content)
            # Atomic rename
            os.replace(temp_path, file_path)
        except Exception:
            # Clean up temp file on error
            try:
                os.unlink(temp_path)
            except OSError:
                pass
            raise

    def _validate_path(self, node_path: str) -> Path:
        """Validate node path for security."""
        # Reject absolute paths
        if node_path.startswith("/"):
            raise ValueError(f"Absolute paths not allowed: {node_path}")

        # Reject path traversal attempts
        if ".." in node_path:
            raise ValueError(f"Path traversal not allowed: {node_path}")

        # Ensure path is relative to vault
        target = self.vault_path / node_path
        try:
            resolved = target.resolve()
            vault_resolved = self.vault_path.resolve()
            resolved.relative_to(vault_resolved)
        except (ValueError, RuntimeError):
            raise ValueError(f"Path outside vault: {node_path}")

        return target

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.1, min=0.1, max=1.0),
        reraise=True,
    )
    def read_node(self, node_path: str) -> Dict[str, Any]:
        """Read an Obsidian node and parse YAML frontmatter + content."""
        file_path = self._validate_path(node_path)
        if not file_path.exists():
            raise FileNotFoundError(f"Node not found: {node_path}")

        lock_path = self._get_lock_path(file_path)
        lock = FileLock(str(lock_path), timeout=5)

        try:
            with lock:
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
                        except yaml.YAMLError as e:
                            logger.error("yaml_parse_error", node_path=node_path, error=str(e))
                            # Try to recover: return raw content
                            return {
                                "path": node_path,
                                "frontmatter": {},
                                "content": content,
                                "raw": content,
                                "parse_error": str(e),
                            }

                return {
                    "path": node_path,
                    "frontmatter": frontmatter,
                    "content": body,
                    "raw": content,
                }
        except Timeout:
            logger.error("vault_read_timeout", node_path=node_path, lock_path=str(lock_path))
            raise VaultError(f"Timeout acquiring lock for {node_path}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.1, min=0.1, max=1.0),
        reraise=True,
    )
    def write_node(
        self, node_path: str, content: str, frontmatter: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Write content to an Obsidian node with optional YAML frontmatter."""
        file_path = self._validate_path(node_path)
        lock_path = self._get_lock_path(file_path)
        lock = FileLock(str(lock_path), timeout=5)

        try:
            with lock:
                if frontmatter:
                    yaml_content = yaml.dump(
                        frontmatter, default_flow_style=False, allow_unicode=True
                    )
                    full_content = f"---\n{yaml_content}---\n\n{content}"
                else:
                    full_content = content

                self._atomic_write(file_path, full_content)

                # Verify write by reading back
                verify = file_path.read_text(encoding="utf-8")
                if verify != full_content:
                    raise VaultCorruptionError(f"Write verification failed for {node_path}")

                logger.info(
                    "vault_write_success",
                    node_path=node_path,
                    content_length=len(content),
                    has_frontmatter=frontmatter is not None,
                )

                return {
                    "path": node_path,
                    "status": "written",
                    "frontmatter": frontmatter,
                    "content_length": len(content),
                }
        except Timeout:
            logger.error("vault_write_timeout", node_path=node_path, lock_path=str(lock_path))
            raise VaultError(f"Timeout acquiring lock for {node_path}")

    def update_frontmatter(self, node_path: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Partial update of YAML frontmatter without rewriting entire file."""
        file_path = self._validate_path(node_path)
        lock_path = self._get_lock_path(file_path)
        lock = FileLock(str(lock_path), timeout=5)

        try:
            with lock:
                # Read current state (inside same lock)
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
                        except yaml.YAMLError as e:
                            logger.error("yaml_parse_error", node_path=node_path, error=str(e))
                            raise VaultError(f"Cannot parse YAML in {node_path}: {e}")

                # Merge updates
                frontmatter.update(updates)
                frontmatter["modified"] = (
                    datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z"
                )

                # Rewrite file atomically (still inside lock)
                yaml_content = yaml.dump(frontmatter, default_flow_style=False, allow_unicode=True)
                full_content = f"---\n{yaml_content}---\n\n{body}"

                self._atomic_write(file_path, full_content)

                logger.info(
                    "vault_update_success", node_path=node_path, updates=list(updates.keys())
                )

                return {
                    "path": node_path,
                    "status": "updated",
                    "frontmatter": frontmatter,
                    "content_length": len(body),
                }
        except Timeout:
            logger.error("vault_update_timeout", node_path=node_path, lock_path=str(lock_path))
            raise VaultError(f"Timeout acquiring lock for {node_path}")

    def find_wiki_links(self, node_path: str) -> List[str]:
        """Extract all wiki-links [[like_this]] from a node."""
        node = self.read_node(node_path)
        links = re.findall(r"\[\[([^\]]+)\]\]", node["content"])
        return links

    def list_nodes(self, directory: str = ".") -> List[str]:
        """List all Markdown files in a vault directory."""
        target_dir = self.vault_path / directory
        if not target_dir.exists():
            return []
        return [str(f.relative_to(self.vault_path)) for f in target_dir.rglob("*.md")]


class AgentSpawner:
    """Handles dynamic agent spawning and lifecycle management."""

    def __init__(self, vault: ObsidianVault):
        self.vault = vault
        self.active_processes: Dict[str, subprocess.Popen] = {}

    def spawn_agent(self, role: str, objective: str, memory_node: str) -> Dict[str, Any]:
        """
        Dynamically spawn a new agent process.

        Args:
            role: Agent specialization (ui_explorer | data_validator)
            objective: Clear micro-task description
            memory_node: Target Obsidian file path for agent logs

        Returns:
            Dict with agent_id, pid, status, and memory_node
        """
        # Check resource limits
        from mcp_server.resource_manager import get_resource_tracker, MAX_AGENT_DURATION_SECONDS

        tracker = get_resource_tracker()

        agent_id = (
            f"{role}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"
        )
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z"

        # Register agent with resource tracker
        tracker.register_agent(agent_id, max_duration=MAX_AGENT_DURATION_SECONDS)

        # Create agent memory node from template
        template_path = VAULT_PATH / "Templates" / "Agent_Spawn_Template.md"
        if template_path.exists():
            template_content = template_path.read_text(encoding="utf-8")
        else:
            template_content = (
                "# Agent Log\n\n## Objective\n{{OBJECTIVE}}\n\n## Progress\n\n## Findings\n"
            )

        # Replace template variables
        node_content = (
            template_content.replace("{{ROLE}}", role)
            .replace("{{AGENT_ID}}", agent_id)
            .replace("{{RUN_ID}}", "current-run")
            .replace("{{OBJECTIVE}}", objective)
            .replace("{{TIMESTAMP}}", timestamp)
        )

        # Write agent memory node
        self.vault.write_node(
            memory_node,
            node_content,
            frontmatter={
                "agent_role": role,
                "agent_id": agent_id,
                "status": "spawned",
                "objective": objective,
                "spawned_at": timestamp,
                "terminated_at": None,
                "result": "pending",
                "compute_pid": None,
            },
        )

        # Spawn real agent worker process
        env = os.environ.copy()
        env["AGENT_ID"] = agent_id
        env["AGENT_ROLE"] = role
        env["AGENT_OBJECTIVE"] = objective
        env["AGENT_MEMORY_NODE"] = str(VAULT_PATH / memory_node)
        env["PYTHONPATH"] = "/app"

        # Map role to worker script
        # Use LLM-driven worker if enabled
        use_llm_workers = os.getenv("VECTRA_LLM_WORKERS", "true").lower() == "true"
        if use_llm_workers:
            worker_scripts = {
                "ui_explorer": "agents/ui_explorer/worker_llm.py",
                "data_validator": "agents/data_validator/worker.py",
                "auth_tester": "agents/feature_tester/worker.py",
                "visual_regression_tester": "agents/feature_tester/worker.py",
                "performance_tester": "agents/feature_tester/worker.py",
                "api_contract_tester": "agents/feature_tester/worker.py",
                "accessibility_tester": "agents/feature_tester/worker.py",
                "multi_browser_tester": "agents/feature_tester/worker.py",
            }
        else:
            worker_scripts = {
                "ui_explorer": "agents/ui_explorer/worker.py",
                "data_validator": "agents/data_validator/worker.py",
                "auth_tester": "agents/feature_tester/worker.py",
                "visual_regression_tester": "agents/feature_tester/worker.py",
                "performance_tester": "agents/feature_tester/worker.py",
                "api_contract_tester": "agents/feature_tester/worker.py",
                "accessibility_tester": "agents/feature_tester/worker.py",
                "multi_browser_tester": "agents/feature_tester/worker.py",
            }

        worker_script = worker_scripts.get(role)
        if not worker_script:
            # Fallback for unknown roles
            process = subprocess.Popen(
                ["python3", "-c", f"print('Agent {agent_id} started - no worker for role {role}')"],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        else:
            # Log output for debugging
            log_file = f"/app/obsidian_vault/Runs/{agent_id}_worker.log"
            worker_path = f"/app/{worker_script}"

            # Verify worker exists before spawning
            import os as os_module

            if not os_module.path.exists(worker_path):
                # Try to find the worker script
                alt_paths = [
                    worker_script,
                    f"./{worker_script}",
                    f"/app/agents/{role}/worker.py",
                    f"agents/{role}/worker.py",
                ]
                for alt in alt_paths:
                    if os_module.path.exists(alt):
                        worker_path = alt
                        break
                else:
                    return {
                        "agent_id": agent_id,
                        "role": role,
                        "status": "error",
                        "error": f"Worker script not found: {worker_path}",
                        "checked_paths": alt_paths,
                    }

            process = subprocess.Popen(
                ["/opt/venv/bin/python3", worker_path, agent_id, memory_node],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd="/app",
            )

            # Start a thread to capture output to log file
            def capture_output(proc, log_path):
                try:
                    log_path = Path(log_path)
                    log_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(log_path, "w") as f:
                        for line in proc.stdout:
                            f.write(line.decode("utf-8", errors="replace"))
                            f.flush()
                except Exception:
                    pass  # Silently fail if log capture fails

            import threading

            t = threading.Thread(target=capture_output, args=(process, log_file))
            t.daemon = True
            t.start()

        self.active_processes[agent_id] = process

        # Update memory node with PID
        self.vault.update_frontmatter(memory_node, {"compute_pid": process.pid, "status": "active"})

        return {
            "agent_id": agent_id,
            "role": role,
            "pid": process.pid,
            "status": "active",
            "memory_node": memory_node,
            "spawned_at": timestamp,
        }

    def terminate_agent(self, agent_id: str) -> Dict[str, Any]:
        """Gracefully terminate an agent process and update its memory node."""
        if agent_id not in self.active_processes:
            return {"error": f"Agent {agent_id} not found"}

        process = self.active_processes[agent_id]

        # Graceful termination
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()

        # Find and update memory node
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z"
        for node_path in self.vault.list_nodes():
            try:
                node = self.vault.read_node(node_path)
                if node["frontmatter"].get("agent_id") == agent_id:
                    self.vault.update_frontmatter(
                        node_path, {"status": "terminated", "terminated_at": timestamp}
                    )
                    break
            except Exception:
                continue

        del self.active_processes[agent_id]

        return {"agent_id": agent_id, "status": "terminated", "terminated_at": timestamp}

    def get_active_agents(self) -> List[Dict[str, Any]]:
        """List all currently active agents."""
        agents = []
        for agent_id, process in self.active_processes.items():
            agents.append(
                {
                    "agent_id": agent_id,
                    "pid": process.pid,
                    "status": "running" if process.poll() is None else "exited",
                }
            )
        return agents


# Lazy initialization of vault and spawner
_vault_instance: Optional[ObsidianVault] = None
_spawner_instance: Optional[AgentSpawner] = None


def get_vault() -> ObsidianVault:
    """Get or create the ObsidianVault instance."""
    global _vault_instance
    if _vault_instance is None:
        _vault_instance = ObsidianVault(VAULT_PATH)
    return _vault_instance


def get_spawner() -> AgentSpawner:
    """Get or create the AgentSpawner instance."""
    global _spawner_instance
    if _spawner_instance is None:
        _spawner_instance = AgentSpawner(get_vault())
    return _spawner_instance


# MCP Tool Definitions
TOOLS = {
    "read_obsidian_node": {
        "description": "Read an Obsidian node (Markdown file) and parse its YAML frontmatter and content",
        "parameters": {
            "node_path": {
                "type": "string",
                "description": "Relative path to the Markdown file in the vault",
            }
        },
        "handler": lambda params: get_vault().read_node(params["node_path"]),
    },
    "write_obsidian_node": {
        "description": "Write content to an Obsidian node with optional YAML frontmatter",
        "parameters": {
            "node_path": {"type": "string", "description": "Relative path to the Markdown file"},
            "content": {"type": "string", "description": "Markdown content to write"},
            "frontmatter": {
                "type": "object",
                "description": "Optional YAML frontmatter dictionary",
                "optional": True,
            },
        },
        "handler": lambda params: get_vault().write_node(
            params["node_path"], params["content"], params.get("frontmatter")
        ),
    },
    "update_frontmatter": {
        "description": "Partial update of YAML frontmatter without rewriting entire file content",
        "parameters": {
            "node_path": {"type": "string", "description": "Relative path to the Markdown file"},
            "updates": {
                "type": "object",
                "description": "Dictionary of frontmatter fields to update/merge",
            },
        },
        "handler": lambda params: get_vault().update_frontmatter(
            params["node_path"], params["updates"]
        ),
    },
    "spawn_agent": {
        "description": "Dynamically spawn a specialized agent process for a discrete testing task",
        "parameters": {
            "role": {
                "type": "string",
                "description": "Agent specialization: ui_explorer or data_validator",
                "enum": ["ui_explorer", "data_validator"],
            },
            "objective": {
                "type": "string",
                "description": "Clear micro-task description for the agent",
            },
            "memory_node": {
                "type": "string",
                "description": "Target Obsidian file path (e.g., Runs/Login_Flow_UI.md)",
            },
        },
        "handler": lambda params: get_spawner().spawn_agent(
            params["role"], params["objective"], params["memory_node"]
        ),
    },
    "terminate_agent": {
        "description": "Gracefully terminate an agent process and update its memory node",
        "parameters": {"agent_id": {"type": "string", "description": "Unique agent identifier"}},
        "handler": lambda params: get_spawner().terminate_agent(params["agent_id"]),
    },
    "list_obsidian_nodes": {
        "description": "List all Markdown files in a vault directory",
        "parameters": {
            "directory": {
                "type": "string",
                "description": "Relative directory path",
                "optional": True,
            }
        },
        "handler": lambda params: {"nodes": get_vault().list_nodes(params.get("directory", "."))},
    },
    "query_selector": {
        "description": "Execute CSS selector against current page DOM using Playwright",
        "parameters": {"selector": {"type": "string", "description": "CSS selector string"}},
        "handler": lambda params: _run_browser_tool("query_selector", params),
    },
    "simulate_interaction": {
        "description": "Simulate user interaction on a page element using Playwright",
        "parameters": {
            "selector": {"type": "string", "description": "CSS selector of target element"},
            "action": {
                "type": "string",
                "description": "Action type: click, type, hover, focus, blur",
            },
            "params": {"type": "object", "description": "Additional parameters", "optional": True},
        },
        "handler": lambda params: _run_browser_tool("simulate_interaction", params),
    },
    "intercept_network_request": {
        "description": "Start intercepting network requests matching pattern",
        "parameters": {
            "method": {"type": "string", "description": "HTTP method"},
            "url_pattern": {"type": "string", "description": "URL pattern to match"},
        },
        "handler": lambda params: _run_browser_tool("intercept_network", params),
    },
    "test_auth_flow": {
        "description": "Test authentication flow (login/logout) with security validation",
        "parameters": {
            "login_url": {"type": "string", "description": "URL of the login page"},
            "username": {
                "type": "string",
                "description": "Username for login test",
                "optional": True,
            },
            "password": {
                "type": "string",
                "description": "Password for login test",
                "optional": True,
            },
            "logout_url": {
                "type": "string",
                "description": "URL of the logout page",
                "optional": True,
            },
        },
        "handler": lambda params: _run_feature_tool("auth", params),
    },
    "test_visual_regression": {
        "description": "Compare current page screenshot against baseline",
        "parameters": {
            "url": {"type": "string", "description": "URL to capture and compare"},
            "name": {
                "type": "string",
                "description": "Name for this baseline (e.g. 'homepage')",
                "optional": True,
            },
        },
        "handler": lambda params: _run_feature_tool("visual_regression", params),
    },
    "test_performance": {
        "description": "Measure Core Web Vitals and page performance metrics",
        "parameters": {
            "url": {"type": "string", "description": "URL to test"},
            "thresholds": {
                "type": "object",
                "description": "Custom thresholds {lcp_ms, fid_ms, cls, ttfb_ms, fcp_ms}",
                "optional": True,
            },
        },
        "handler": lambda params: _run_feature_tool("performance", params),
    },
    "test_api_contract": {
        "description": "Validate API response against OpenAPI schema",
        "parameters": {
            "base_url": {"type": "string", "description": "Base URL of the API"},
            "endpoint": {"type": "string", "description": "API endpoint path (e.g. /api/v1/users)"},
            "method": {
                "type": "string",
                "description": "HTTP method",
                "enum": ["GET", "POST", "PUT", "DELETE", "PATCH"],
            },
            "schema_path": {
                "type": "string",
                "description": "Path to OpenAPI schema file",
                "optional": True,
            },
            "body": {
                "type": "object",
                "description": "Request body for POST/PUT",
                "optional": True,
            },
        },
        "handler": lambda params: _run_feature_tool("api_contract", params),
    },
    "test_accessibility": {
        "description": "Run accessibility checks (axe-core + manual) on a page",
        "parameters": {
            "url": {"type": "string", "description": "URL to test"},
            "standard": {
                "type": "string",
                "description": "WCAG standard: wcag2a, wcag2aa, wcag21aa",
                "enum": ["wcag2a", "wcag2aa", "wcag21aa"],
                "optional": True,
            },
        },
        "handler": lambda params: _run_feature_tool("accessibility", params),
    },
    "test_multi_browser": {
        "description": "Run smoke test across Chromium, Firefox, and WebKit",
        "parameters": {"url": {"type": "string", "description": "URL to test"}},
        "handler": lambda params: _run_feature_tool("multi_browser", params),
    },
}


# Browser instance for MCP tools (shared across tool calls)
_browser_instance: Optional[Any] = None


def _get_browser() -> Any:
    """Get or create shared BrowserAutomation instance for MCP tools."""
    global _browser_instance
    if _browser_instance is None:
        from mcp_server.browser_tools import BrowserAutomation

        _browser_instance = BrowserAutomation(headless=True)
    return _browser_instance


def _run_browser_tool(tool_type: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Run a browser-based MCP tool asynchronously."""
    try:
        # Try to get or create an event loop
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        if loop.is_running():
            # If we're in an async context, create a new loop in a thread
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(
                    lambda: asyncio.new_event_loop().run_until_complete(
                        _async_browser_tool(tool_type, params)
                    )
                )
                return future.result()
        else:
            return loop.run_until_complete(_async_browser_tool(tool_type, params))
    except Exception as e:
        logger.error("browser_tool_error", tool=tool_type, error=str(e))
        return {"error": f"Browser tool failed: {str(e)}", "tool": tool_type, "status": "error"}


async def _async_browser_tool(tool_type: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Async implementation of browser tools."""
    browser = _get_browser()

    # Ensure browser is started
    if browser.page is None:
        await browser.start()

    if tool_type == "query_selector":
        selector = params.get("selector", "")
        try:
            elements = await browser.page.query_selector_all(selector)
            visible_count = 0
            for el in elements:
                try:
                    if await el.is_visible():
                        visible_count += 1
                except Exception:
                    pass

            return {
                "selector": selector,
                "matches": len(elements),
                "visible": visible_count,
                "status": "success",
            }
        except Exception as e:
            return {
                "selector": selector,
                "matches": 0,
                "visible": 0,
                "error": str(e),
                "status": "error",
            }

    elif tool_type == "simulate_interaction":
        selector = params.get("selector", "")
        action = params.get("action", "")
        extra_params = params.get("params", {})

        try:
            if action == "click":
                result = await browser.click(selector)
            elif action == "type":
                text = extra_params.get("text", "")
                result = await browser.fill(selector, text)
            elif action == "hover":
                await browser.page.hover(selector)
                result = {"success": True, "action": "hover"}
            elif action == "focus":
                await browser.page.focus(selector)
                result = {"success": True, "action": "focus"}
            elif action == "blur":
                await browser.page.evaluate(f'document.querySelector("{selector}").blur()')
                result = {"success": True, "action": "blur"}
            else:
                result = {"success": False, "error": f"Unknown action: {action}"}

            return {
                "selector": selector,
                "action": action,
                "status": "success" if result.get("success") else "error",
                **result,
            }
        except Exception as e:
            return {"selector": selector, "action": action, "error": str(e), "status": "error"}

    elif tool_type == "intercept_network":
        # Network interception is handled at browser context level
        # Return info about current network logs
        return {
            "request_id": f"req-{uuid.uuid4().hex[:8]}",
            "method": params.get("method", "GET"),
            "pattern": params.get("url_pattern", "**/*"),
            "status": "intercepting",
            "network_logs_count": len(browser.network_logs),
            "note": "Network logs are being captured automatically",
        }

    return {"error": "Unknown tool type", "tool": tool_type}


def _run_feature_tool(feature_type: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Run a feature test MCP tool asynchronously."""
    try:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        if loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(
                    lambda: asyncio.new_event_loop().run_until_complete(
                        _async_feature_tool(feature_type, params)
                    )
                )
                return future.result()
        else:
            return loop.run_until_complete(_async_feature_tool(feature_type, params))
    except Exception as e:
        logger.error("feature_tool_error", feature=feature_type, error=str(e))
        return {
            "error": f"Feature tool failed: {str(e)}",
            "feature": feature_type,
            "status": "error",
        }


async def _async_feature_tool(feature_type: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Async implementation of feature test tools."""
    from mcp_server.features.auth_testing import AuthFlowTester
    from mcp_server.features.visual_regression import VisualRegressionTester
    from mcp_server.features.performance import PerformanceTester
    from mcp_server.features.api_contract import APIContractTester
    from mcp_server.features.accessibility import AccessibilityTester
    from mcp_server.features.multi_browser import MultiBrowserTester
    from mcp_server.browser_tools import BrowserAutomation

    browser = None

    try:
        if feature_type == "auth":
            browser = BrowserAutomation()
            await browser.start()
            tester = AuthFlowTester(browser)
            result = await tester.test_login_flow(
                login_url=params["login_url"],
                username=params.get("username", ""),
                password=params.get("password", ""),
            )
            if params.get("logout_url"):
                logout_result = await tester.test_logout_flow(params["logout_url"])
                result["logout_test"] = logout_result
            return result

        elif feature_type == "visual_regression":
            browser = BrowserAutomation()
            await browser.start()
            vr_tester = VisualRegressionTester(VAULT_PATH / "Baselines")
            return await vr_tester.test_visual_regression(browser, params["url"])

        elif feature_type == "performance":
            browser = BrowserAutomation()
            await browser.start()
            perf_tester = PerformanceTester()
            thresholds = params.get("thresholds")
            return await perf_tester.test_performance(browser, params["url"], thresholds)

        elif feature_type == "api_contract":
            api_tester = APIContractTester()
            schema_path = params.get("schema_path")
            if schema_path and os.path.exists(schema_path):
                api_tester.load_schema(schema_path)
            return await api_tester.test_endpoint(
                params["base_url"], params["endpoint"], params["method"], params.get("body")
            )

        elif feature_type == "accessibility":
            browser = BrowserAutomation()
            await browser.start()
            a11y_tester = AccessibilityTester()
            return await a11y_tester.test_accessibility(browser, params["url"])

        elif feature_type == "multi_browser":
            mb_tester = MultiBrowserTester()

            async def test_fn(browser, url):
                result = await browser.visit(url)
                return {
                    "status": "pass" if result["success"] else "fail",
                    "findings": [],
                    "metrics": {"http_status": result.get("status")},
                }

            return await mb_tester.test_all_browsers(test_fn, params["url"])

        return {"error": f"Unknown feature type: {feature_type}"}

    finally:
        if browser:
            await browser.close()


def execute_tool(tool_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
    """Execute an MCP tool by name with given parameters."""
    if tool_name not in TOOLS:
        return {"error": f"Unknown tool: {tool_name}"}

    tool = TOOLS[tool_name]
    tool_params = cast(Dict[str, Any], tool["parameters"])
    tool_handler = cast(Any, tool["handler"])

    # Validate required parameters
    for param_name, param_spec in tool_params.items():
        if not param_spec.get("optional", False) and param_name not in parameters:
            return {"error": f"Missing required parameter: {param_name}"}

    # Validate with Pydantic models if available
    try:
        from mcp_server.models import REQUEST_MODELS

        if tool_name in REQUEST_MODELS:
            REQUEST_MODELS[tool_name](**parameters)
    except Exception as e:
        logger.warning(
            "tool_validation_error", tool=tool_name, error=str(e), error_type=type(e).__name__
        )
        return {"tool": tool_name, "status": "error", "error": f"Validation error: {str(e)}"}

    try:
        result = tool_handler(parameters)
        return {"tool": tool_name, "status": "success", "result": result}
    except Exception as e:
        logger.error(
            "tool_execution_error", tool=tool_name, error=str(e), error_type=type(e).__name__
        )
        return {"tool": tool_name, "status": "error", "error": str(e)}
