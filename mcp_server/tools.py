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
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Configuration - use environment variable or default
VAULT_PATH = Path(os.getenv("OBSIDIAN_VAULT_PATH", "/app/obsidian_vault"))
AGENTS_DIR = Path(os.getenv("AGENTS_DIR", "/app/agents"))


class ObsidianVault:
    """Handles all Obsidian Vault file operations."""
    
    def __init__(self, vault_path: Path):
        self.vault_path = vault_path
        
    def read_node(self, node_path: str) -> Dict[str, Any]:
        """Read an Obsidian node and parse YAML frontmatter + content."""
        file_path = self.vault_path / node_path
        if not file_path.exists():
            raise FileNotFoundError(f"Node not found: {node_path}")
            
        content = file_path.read_text(encoding='utf-8')
        
        # Parse YAML frontmatter
        frontmatter = {}
        body = content
        
        if content.startswith('---'):
            parts = content.split('---', 2)
            if len(parts) >= 3:
                try:
                    frontmatter = yaml.safe_load(parts[1]) or {}
                    body = parts[2].strip()
                except yaml.YAMLError:
                    pass
        
        return {
            "path": node_path,
            "frontmatter": frontmatter,
            "content": body,
            "raw": content
        }
    
    def write_node(self, node_path: str, content: str, frontmatter: Optional[Dict] = None) -> Dict[str, Any]:
        """Write content to an Obsidian node with optional YAML frontmatter."""
        file_path = self.vault_path / node_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        if frontmatter:
            yaml_content = yaml.dump(frontmatter, default_flow_style=False, allow_unicode=True)
            full_content = f"---\n{yaml_content}---\n\n{content}"
        else:
            full_content = content
            
        file_path.write_text(full_content, encoding='utf-8')
        
        return {
            "path": node_path,
            "status": "written",
            "frontmatter": frontmatter,
            "content_length": len(content)
        }
    
    def update_frontmatter(self, node_path: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Partial update of YAML frontmatter without rewriting entire file."""
        node = self.read_node(node_path)
        current_fm = node["frontmatter"]
        
        # Merge updates
        current_fm.update(updates)
        current_fm["modified"] = datetime.utcnow().isoformat() + "Z"
        
        # Rewrite file
        return self.write_node(node_path, node["content"], current_fm)
    
    def find_wiki_links(self, node_path: str) -> List[str]:
        """Extract all wiki-links [[like_this]] from a node."""
        node = self.read_node(node_path)
        links = re.findall(r'\[\[([^\]]+)\]\]', node["content"])
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
        agent_id = f"{role}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"
        timestamp = datetime.utcnow().isoformat() + "Z"
        
        # Create agent memory node from template
        template_path = VAULT_PATH / "Templates" / "Agent_Spawn_Template.md"
        if template_path.exists():
            template_content = template_path.read_text(encoding='utf-8')
        else:
            template_content = "# Agent Log\n\n## Objective\n{{OBJECTIVE}}\n\n## Progress\n\n## Findings\n"
        
        # Replace template variables
        node_content = template_content.replace("{{ROLE}}", role).replace("{{AGENT_ID}}", agent_id).replace("{{RUN_ID}}", "current-run").replace("{{OBJECTIVE}}", objective).replace("{{TIMESTAMP}}", timestamp)
        
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
                "compute_pid": None
            }
        )
        
        # Spawn real agent worker process
        env = os.environ.copy()
        env["AGENT_ID"] = agent_id
        env["AGENT_ROLE"] = role
        env["AGENT_OBJECTIVE"] = objective
        env["AGENT_MEMORY_NODE"] = str(VAULT_PATH / memory_node)
        env["PYTHONPATH"] = "/app"
        
        # Map role to worker script
        worker_scripts = {
            "ui_explorer": "agents/ui_explorer/worker.py",
            "data_validator": "agents/data_validator/worker.py"
        }
        
        worker_script = worker_scripts.get(role)
        if not worker_script:
            # Fallback for unknown roles
            process = subprocess.Popen(
                ["python3", "-c", f"print('Agent {agent_id} started - no worker for role {role}')"],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
        else:
            # Log output for debugging
            log_file = f"/app/obsidian_vault/Runs/{agent_id}_worker.log"
            with open(log_file, 'w') as f:
                process = subprocess.Popen(
                    ["/opt/venv/bin/python3", worker_script, agent_id, memory_node],
                    env=env,
                    stdout=f,
                    stderr=subprocess.STDOUT,
                    cwd="/app"
                )
        
        self.active_processes[agent_id] = process
        
        # Update memory node with PID
        self.vault.update_frontmatter(memory_node, {
            "compute_pid": process.pid,
            "status": "active"
        })
        
        return {
            "agent_id": agent_id,
            "role": role,
            "pid": process.pid,
            "status": "active",
            "memory_node": memory_node,
            "spawned_at": timestamp
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
        timestamp = datetime.utcnow().isoformat() + "Z"
        for node_path in self.vault.list_nodes():
            try:
                node = self.vault.read_node(node_path)
                if node["frontmatter"].get("agent_id") == agent_id:
                    self.vault.update_frontmatter(node_path, {
                        "status": "terminated",
                        "terminated_at": timestamp
                    })
                    break
            except:
                continue
        
        del self.active_processes[agent_id]
        
        return {
            "agent_id": agent_id,
            "status": "terminated",
            "terminated_at": timestamp
        }
    
    def get_active_agents(self) -> List[Dict[str, Any]]:
        """List all currently active agents."""
        agents = []
        for agent_id, process in self.active_processes.items():
            agents.append({
                "agent_id": agent_id,
                "pid": process.pid,
                "status": "running" if process.poll() is None else "exited"
            })
        return agents


# Initialize vault and spawner
vault = ObsidianVault(VAULT_PATH)
spawner = AgentSpawner(vault)


# MCP Tool Definitions
TOOLS = {
    "read_obsidian_node": {
        "description": "Read an Obsidian node (Markdown file) and parse its YAML frontmatter and content",
        "parameters": {
            "node_path": {"type": "string", "description": "Relative path to the Markdown file in the vault"}
        },
        "handler": lambda params: vault.read_node(params["node_path"])
    },
    "write_obsidian_node": {
        "description": "Write content to an Obsidian node with optional YAML frontmatter",
        "parameters": {
            "node_path": {"type": "string", "description": "Relative path to the Markdown file"},
            "content": {"type": "string", "description": "Markdown content to write"},
            "frontmatter": {"type": "object", "description": "Optional YAML frontmatter dictionary", "optional": True}
        },
        "handler": lambda params: vault.write_node(
            params["node_path"], 
            params["content"], 
            params.get("frontmatter")
        )
    },
    "update_frontmatter": {
        "description": "Partial update of YAML frontmatter without rewriting entire file content",
        "parameters": {
            "node_path": {"type": "string", "description": "Relative path to the Markdown file"},
            "updates": {"type": "object", "description": "Dictionary of frontmatter fields to update/merge"}
        },
        "handler": lambda params: vault.update_frontmatter(params["node_path"], params["updates"])
    },
    "spawn_agent": {
        "description": "Dynamically spawn a specialized agent process for a discrete testing task",
        "parameters": {
            "role": {"type": "string", "description": "Agent specialization: ui_explorer or data_validator", "enum": ["ui_explorer", "data_validator"]},
            "objective": {"type": "string", "description": "Clear micro-task description for the agent"},
            "memory_node": {"type": "string", "description": "Target Obsidian file path (e.g., Runs/Login_Flow_UI.md)"}
        },
        "handler": lambda params: spawner.spawn_agent(params["role"], params["objective"], params["memory_node"])
    },
    "terminate_agent": {
        "description": "Gracefully terminate an agent process and update its memory node",
        "parameters": {
            "agent_id": {"type": "string", "description": "Unique agent identifier"}
        },
        "handler": lambda params: spawner.terminate_agent(params["agent_id"])
    },
    "list_obsidian_nodes": {
        "description": "List all Markdown files in a vault directory",
        "parameters": {
            "directory": {"type": "string", "description": "Relative directory path", "optional": True}
        },
        "handler": lambda params: {"nodes": vault.list_nodes(params.get("directory", "."))}
    },
    "query_selector": {
        "description": "Execute CSS selector against current page DOM (placeholder for Playwright integration)",
        "parameters": {
            "selector": {"type": "string", "description": "CSS selector string"}
        },
        "handler": lambda params: {
            "selector": params["selector"],
            "matches": 0,
            "visible": False,
            "note": "This is a placeholder. Integrate with Playwright/Puppeteer for actual DOM queries."
        }
    },
    "simulate_interaction": {
        "description": "Simulate user interaction on a page element (placeholder for Playwright integration)",
        "parameters": {
            "selector": {"type": "string", "description": "CSS selector of target element"},
            "action": {"type": "string", "description": "Action type: click, type, hover, focus, blur"},
            "params": {"type": "object", "description": "Additional parameters", "optional": True}
        },
        "handler": lambda params: {
            "selector": params["selector"],
            "action": params["action"],
            "success": True,
            "note": "This is a placeholder. Integrate with Playwright/Puppeteer for actual interactions."
        }
    },
    "intercept_network_request": {
        "description": "Start intercepting network requests matching pattern (placeholder)",
        "parameters": {
            "method": {"type": "string", "description": "HTTP method"},
            "url_pattern": {"type": "string", "description": "URL pattern to match"}
        },
        "handler": lambda params: {
            "request_id": f"req-{uuid.uuid4().hex[:8]}",
            "method": params["method"],
            "pattern": params["url_pattern"],
            "status": "intercepting"
        }
    }
}


def execute_tool(tool_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
    """Execute an MCP tool by name with given parameters."""
    if tool_name not in TOOLS:
        return {"error": f"Unknown tool: {tool_name}"}
    
    tool = TOOLS[tool_name]
    
    # Validate required parameters
    for param_name, param_spec in tool["parameters"].items():
        if not param_spec.get("optional", False) and param_name not in parameters:
            return {"error": f"Missing required parameter: {param_name}"}
    
    try:
        result = tool["handler"](parameters)
        return {
            "tool": tool_name,
            "status": "success",
            "result": result
        }
    except Exception as e:
        return {
            "tool": tool_name,
            "status": "error",
            "error": str(e)
        }
