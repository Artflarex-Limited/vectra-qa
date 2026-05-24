# Vectra QA

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-009688.svg)](https://fastapi.tiangolo.com)

## The Death of Static E2E Testing

Traditional E2E testing is **dead**. Static scripts, brittle selectors, and monolithic test suites cannot keep pace with modern development velocity. Every UI refactor breaks your tests. Every API change invalidates your assertions. You spend more time maintaining tests than writing features.

**Vectra QA** is a paradigm shift. We don't write tests. We **deploy agents**.

Our framework treats testing as an autonomous, multi-agent exploration problem. A Test Manager agent dynamically spawns specialized sub-agents—UI Explorers that hunt for broken flows, Data Validators that intercept network traffic and verify payloads—each operating with its own behavioral DNA, memory, and objectives. When their mission is complete, they gracefully terminate, freeing compute resources.

## Why Obsidian-Backed Memory?

Agents don't use JSON blobs. They read and write **Markdown files** in a local [Obsidian](https://obsidian.md/) Vault. This isn't just storage—it's a **relational memory layer**:

- **YAML frontmatter** tracks structured state (pass/fail metrics, agent status, timestamps)
- **Wiki-links** (`[[ ]]`) create semantic connections between test findings
- **Native LLM compatibility**: Markdown is the lingua franca of large language models
- **Human-readable**: Your test history is a browsable knowledge graph, not a database dump

## Key Features

- **🤖 Dynamic Agent Spawning**: The Orchestrator instantiates UI Explorers and Data Validators on-demand, not as pre-running daemons
- **🧠 MCP Skill System**: Extensible Model Context Protocol tools for DOM manipulation, network interception, and database validation
- **📡 RAG Integration**: Agents retrieve user stories and requirements from vector stores to inform test strategies
- **🎛️ Live Command Center**: Dark-mode HTMX dashboard with Server-Sent Events for real-time test monitoring
- **📊 Obsidian Memory Layer**: YAML frontmatter + wiki-links for structured, relational test logging
- **⚡ Resource Efficient**: Agents auto-terminate after completion, freeing compute for the next test wave

## Quickstart

### Prerequisites

- Python 3.11+
- [Obsidian](https://obsidian.md/) (optional, for visual graph browsing)
- Chrome/Chromium (for Playwright browser automation)

### Installation

```bash
# Clone the repository
git clone https://github.com/your-org/vectra-qa.git
cd vectra-qa

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers (for UI automation)
playwright install chromium
```

### Initialize the Obsidian Vault

```bash
# The vault is pre-configured in obsidian_vault/
# Open it in Obsidian for the full experience
# Or use it headlessly—the agents write Markdown directly
```

### Start the System

```bash
# Terminal 1: Start the MCP Server
python mcp_server/server.py --transport sse --port 8080

# Terminal 2: Start the Command Center Dashboard
cd command_center
python main.py

# Terminal 3: Run a test scenario
python examples/test_scenario.py
```

Open your browser to **`http://localhost:3000`** to watch the live Command Center.

### Your First Agentic Test

```python
from mcp_server.tools import execute_tool

# The Orchestrator spawns a UI Explorer agent
result = execute_tool("spawn_agent", {
    "role": "ui_explorer",
    "objective": "Verify login form rendering and accessibility",
    "memory_node": "Runs/Login_Test.md"
})

print(f"Agent spawned: {result['result']['agent_id']}")
# Agent writes findings to Runs/Login_Test.md
# Check the Command Center to see live updates!
```

## Architecture

For a deep dive into the system design, memory layer, and agent communication protocol, see [ARCHITECTURE.md](ARCHITECTURE.md).

## Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on adding new MCP skills, tuning agent personas, and local development setup.

## License

MIT License - see [LICENSE](LICENSE) for details.

---

**Built with obsession by the Vectra QA team.**
