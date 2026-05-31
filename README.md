# Vectra QA

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-009688.svg)](https://fastapi.tiangolo.com)
[![Tests](https://img.shields.io/badge/tests-79%20passing-brightgreen.svg)](tests/)

## The Death of Static E2E Testing

Traditional E2E testing is **dead**. Static scripts, brittle selectors, and monolithic test suites cannot keep pace with modern development velocity. Every UI refactor breaks your tests. Every API change invalidates your assertions. You spend more time maintaining tests than writing features.

**Vectra QA** is a paradigm shift. We don't write tests. We **deploy agents**.

Our framework treats testing as an autonomous, multi-agent exploration problem. A Test Manager agent dynamically spawns specialized sub-agents—UI Explorers that hunt for broken flows, Data Validators that intercept network traffic and verify payloads, Auth Testers that probe login flows for security flaws—each operating with its own behavioral DNA, memory, and objectives. When their mission is complete, they gracefully terminate, freeing compute resources.

## Why Obsidian-Backed Memory?

Agents don't use JSON blobs. They read and write **Markdown files** in a local [Obsidian](https://obsidian.md/) Vault. This isn't just storage—it's a **relational memory layer**:

- **YAML frontmatter** tracks structured state (pass/fail metrics, agent status, timestamps)
- **Wiki-links** (`[[ ]]`) create semantic connections between test findings
- **Native LLM compatibility**: Markdown is the lingua franca of large language models
- **Human-readable**: Your test history is a browsable knowledge graph, not a database dump
- **File locking + atomic writes**: Safe concurrent access without database complexity

## Key Features

- **🤖 Dynamic Agent Spawning**: The Orchestrator instantiates specialized agents on-demand, not as pre-running daemons
- **🧠 LLM-Driven Agents**: Full LLM reasoning for every decision—no brittle keyword matching
- **🔐 Security Testing**: Auth flow validation, session cookie security, HTTPS enforcement
- **📊 Performance Monitoring**: Core Web Vitals (LCP, FID, CLS, TTFB, FCP), Lighthouse CI integration
- **🎨 Visual Regression**: Screenshot comparison with baseline management
- **🔌 API Contract Validation**: OpenAPI schema verification for REST endpoints
- **♿ Accessibility Testing**: axe-core integration with WCAG compliance checks
- **🌐 Cross-Browser Testing**: Chromium, Firefox, WebKit smoke tests
- **⚡ LLM Response Caching**: SHA256-based cache with TTL, reducing API costs by 60-80%
- **📡 Distributed Workers**: Redis-backed task queue for horizontal scaling
- **🎛️ Live Command Center**: Dark-mode HTMX dashboard with Server-Sent Events
- **📡 MCP Skill System**: Extensible Model Context Protocol tools
- **⚡ Resource Efficient**: Agents auto-terminate after completion, BrowserPool limits concurrent instances

## Quickstart

### Prerequisites

- Python 3.12+
- [Obsidian](https://obsidian.md/) (optional, for visual graph browsing)
- Chrome/Chromium, Firefox, WebKit (for Playwright browser automation)
- Redis (optional, for distributed workers)

### Installation

```bash
# Clone the repository
git clone https://github.com/your-org/vectra-qa.git
cd vectra-qa

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install chromium firefox webkit

# Validate environment
python scripts/validate_env.py
```

### Initialize the Obsidian Vault

```bash
# The vault is pre-configured in obsidian_vault/
# Open it in Obsidian for the full experience
# Or use it headlessly—the agents write Markdown directly
```

### Environment Setup

Vectra QA uses a `.env` file for configuration. This keeps secrets out of code and lets you customize the framework for your stack.

```bash
# 1. Copy the example file
cp .env.example .env

# 2. Edit .env with your favorite editor
nano .env  # or vim, code, etc.
```

#### Minimum Required for "Hello World"

To run your first agentic test, you **only** need to configure:

1. **One LLM provider** (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `MINIMAX_API_KEY`, or `KIMI_API_KEY`)
2. **Obsidian Vault path** (`OBSIDIAN_VAULT_PATH`)

```bash
### Minimal .env for first run ###
OPENAI_API_KEY=sk-your-key-here
OBSIDIAN_VAULT_PATH=/home/$(whoami)/Documents/obsidian_vault
MCP_SERVER_PORT=8080
COMMAND_CENTER_PORT=3000
```

**Supported Providers:**
- **OpenAI** — GPT-4o, GPT-4o-mini (general purpose)
- **Anthropic** — Claude 3.5 Sonnet (UI analysis, reasoning)
- **MiniMax** — minimax-text-01 (Chinese/English, structured output)
- **Kimi** — kimi-k2 (ultra-long context up to 2M tokens)
- **Local** — Ollama, LM Studio (privacy, cost control)

#### Advanced Configuration

```bash
# Orchestrator model (test planner)
ORCHESTRATOR_MODEL=openai/gpt-4o

# UI Explorer model (browser automation)
UI_EXPLORER_MODEL=anthropic/claude-3-5-sonnet-20241022

# LLM Worker toggle (true=LLM-driven, false=legacy keyword matching)
VECTRA_LLM_WORKERS=true

# LLM Response Cache (reduces API costs)
VECTRA_LLM_CACHE=true
VECTRA_LLM_CACHE_TTL=3600

# Redis for distributed workers (optional)
REDIS_URL=redis://localhost:6379/0

# Browser settings
HEADLESS=true
```

#### Setting Up Your Obsidian Vault

The vault is just a directory of Markdown files. Create it anywhere safe:

```bash
# Create vault directory
mkdir -p ~/Documents/vectra-qa-vault/{Global,Runs,Templates,Baselines}

# The framework will create memory nodes here automatically
# Open this folder in Obsidian for the visual graph experience
```

**Important:** The vault path must be:
- **Absolute** (not relative like `./vault`)
- **Writable** by the user running the agents
- **Outside version control** (add it to `.gitignore`)

#### Verifying Your Setup

```bash
# Test LLM connectivity (OpenAI example)
python -c "import openai; print('OpenAI OK')"

# For MiniMax/Kimi, the framework uses the OpenAI SDK with custom base URLs
# Just ensure your API keys are set in .env

# Test vault path
ls $OBSIDIAN_VAULT_PATH

# Validate full environment
python scripts/validate_env.py

# Start services
python mcp_server/server.py &
python command_center/main.py &
```

Open `http://localhost:3000` — you should see the dark-mode Command Center.

### 🐳 Docker Quickstart (Recommended)

The fastest way to get started is with Docker Compose. This spins up the entire stack—MCP Server, Command Center Dashboard, Redis, and Obsidian Vault—with a single command.

#### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) 20.10+
- [Docker Compose](https://docs.docker.com/compose/install/) 2.0+

#### One-Command Setup

```bash
# 1. Clone and enter the repository
git clone https://github.com/your-org/vectra-qa.git
cd vectra-qa

# 2. Configure your environment
cp .env.example .env
# Edit .env and add at least one LLM API key

# 3. Launch the entire stack
docker compose up --build

# 4. Open the dashboard
open http://localhost:3000
```

That's it! The dashboard will be available at **`http://localhost:3000`** and the MCP Server at **`http://localhost:8080`**.

### 🧪 Testing Your Own Project

Now that Vectra QA is running, test your web application:

#### 1. Configure Your Target

Edit `.env`:

```bash
# Your application's URL (required)
TARGET_URL=http://localhost:3001  # Your dev server
# Or: TARGET_URL=https://staging.myapp.com

# Test credentials (if your app requires login)
TEST_USERNAME=test@example.com
TEST_PASSWORD=your-test-password
```

#### 2. Create a Test Scenario

Create `examples/my_app_test.py`:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp_server.tools import execute_tool

# Test authentication flow
result = execute_tool("test_auth_flow", {
    "login_url": "http://localhost:3001/login",
    "username": "test@example.com",
    "password": "password123",
    "logout_url": "http://localhost:3001/logout"
})
print(f"Auth test: {result['status']}")

# Test performance
result = execute_tool("test_performance", {
    "url": "http://localhost:3001",
    "thresholds": {"lcp_ms": 2500, "ttfb_ms": 600}
})
print(f"Performance: {result['metrics']}")

# Test accessibility
result = execute_tool("test_accessibility", {
    "url": "http://localhost:3001",
    "standard": "wcag2aa"
})
print(f"Accessibility: {len(result['findings'])} findings")

# Spawn an agent for comprehensive UI exploration
result = execute_tool("spawn_agent", {
    "role": "ui_explorer",
    "objective": (
        "Test the login page at http://localhost:3001/login. "
        "1. Verify email and password fields. "
        "2. Test form validation. "
        "3. Submit test credentials. "
        "4. Verify redirect to dashboard."
    ),
    "memory_node": "Runs/MyApp_Login_Test.md"
})

print(f"Agent spawned: {result['result']['agent_id']}")
print("Check http://localhost:3000 for live results")
```

#### 3. Run the Test

```bash
# In a new terminal
python examples/my_app_test.py
```

#### 4. View Results

- **Live Dashboard**: http://localhost:3000
- **Detailed Reports**: `obsidian_vault/Runs/MyApp_Login_Test.md`

For a complete guide, see [USER_GUIDE.md](USER_GUIDE.md).
For a full example, see [examples/test_real_app.py](examples/test_real_app.py).

#### Docker Services

| Service | Port | Description |
|---------|------|-------------|
| `mcp-server` | `8080` | MCP Tool Server (spawn_agent, feature tests, Obsidian tools) |
| `command-center` | `3000` | HTMX Dashboard with live SSE updates |
| `redis` | `6379` | Task queue and LLM cache backend |
| `worker-pool` | — | Distributed agent workers |
| `vault-watcher` | — | File watcher for Obsidian vault changes |

#### Useful Docker Commands

```bash
# Start in detached mode (background)
docker compose up -d

# Scale worker pool
docker compose up -d --scale worker-pool=3

# View logs
docker compose logs -f

# View specific service logs
docker compose logs -f mcp-server

# Restart a service
docker compose restart command-center

# Stop everything
docker compose down

# Stop and remove volumes (clears Obsidian vault)
docker compose down -v
```

#### Running Test Scenarios in Docker

```bash
# Execute a test scenario inside the MCP container
docker compose exec mcp-server python examples/test_scenario.py

# Or mount the examples directory and run from host
docker compose exec mcp-server python -m examples.test_scenario
```

#### Local LLM with Docker (Optional)

To use a local LLM like Ollama, uncomment the `ollama` service in `docker-compose.yml`:

```yaml
# docker-compose.yml
services:
  ollama:
    image: ollama/ollama:latest
    ports:
      - "11434:11434"
    volumes:
      - ollama-data:/root/.ollama
```

Then pull a model:

```bash
docker compose exec ollama ollama pull llama3.1:70b
```

And set your `.env`:

```bash
LOCAL_LLM_BASE_URL=http://localhost:11434/v1
LOCAL_LLM_MODEL=llama3.1:70b
DATA_VALIDATOR_MODEL=local/llama3.1:70b
```

### Start the System (Manual)

```bash
# Terminal 1: Start Redis (if using distributed workers)
redis-server

# Terminal 2: Start the MCP Server
python mcp_server/server.py --transport sse --port 8080

# Terminal 3: Start the Command Center Dashboard
cd command_center
python main.py

# Terminal 4: Run a test scenario
python examples/test_scenario.py
```

Open your browser to **`http://localhost:3000`** to watch the live Command Center.

### Your First Agentic Test

```python
from mcp_server.tools import execute_tool

# Direct feature test - no agent needed
result = execute_tool("test_performance", {
    "url": "https://example.com",
    "thresholds": {"lcp_ms": 2500}
})
print(f"Performance: {result['metrics']}")

# Or spawn an agent for complex exploration
result = execute_tool("spawn_agent", {
    "role": "ui_explorer",
    "objective": "Verify login form rendering and accessibility",
    "memory_node": "Runs/Login_Test.md"
})

print(f"Agent spawned: {result['result']['agent_id']}")
# Agent writes findings to Runs/Login_Test.md
# Check the Command Center to see live updates!
```

## Agent Roles

Vectra QA supports multiple specialized agent roles:

| Role | Description | Use Case |
|------|-------------|----------|
| `ui_explorer` | LLM-driven browser automation | Complex UI flows, exploration |
| `data_validator` | Network traffic validation | API response verification |
| `auth_tester` | Authentication flow testing | Login/logout security |
| `visual_regression_tester` | Screenshot comparison | UI consistency checks |
| `performance_tester` | Core Web Vitals measurement | Page speed monitoring |
| `api_contract_tester` | OpenAPI schema validation | API contract compliance |
| `accessibility_tester` | WCAG compliance checks | Accessibility auditing |
| `multi_browser_tester` | Cross-browser smoke tests | Browser compatibility |

## Architecture

For a deep dive into the system design, memory layer, and agent communication protocol, see [ARCHITECTURE.md](ARCHITECTURE.md).

### System Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                      Vectra QA Framework                     │
├─────────────────────────────────────────────────────────────┤
│  Command Center (Port 3000)                                  │
│  ├── HTMX Dashboard (SSE live updates)                      │
│  ├── Chatbot (LLM-powered QA assistant)                     │
│  └── Health/Metrics endpoints                               │
├─────────────────────────────────────────────────────────────┤
│  MCP Server (Port 8080)                                      │
│  ├── Tools: read/write Obsidian nodes                       │
│  ├── Tools: spawn/terminate agents                          │
│  ├── Tools: browser automation (query, click, intercept)    │
│  ├── Tools: feature tests (auth, perf, a11y, etc.)         │
│  ├── Pydantic input validation                              │
│  ├── Tenacity retry logic                                   │
│  └── Structlog structured logging                           │
├─────────────────────────────────────────────────────────────┤
│  Orchestrator                                                │
│  ├── LLM-driven test planning                               │
│  ├── Parallel task execution                                │
│  └── Report compilation                                     │
├─────────────────────────────────────────────────────────────┤
│  Agents                                                      │
│  ├── UI Explorer (LLM observe-plan-act loop)               │
│  ├── Data Validator                                         │
│  └── Feature Testers (auth, visual, perf, API, a11y)      │
├─────────────────────────────────────────────────────────────┤
│  Infrastructure                                              │
│  ├── BrowserPool (max 10 concurrent)                        │
│  ├── AgentResourceTracker (steps/time/LLM limits)           │
│  ├── StateManager (SIGTERM persistence)                     │
│  ├── TaskQueue (Redis or in-memory)                         │
│  └── LLMCache (SHA256-based, TTL expiration)                │
├─────────────────────────────────────────────────────────────┤
│  Memory Layer                                                │
│  ├── Obsidian Vault (Markdown + YAML frontmatter)           │
│  ├── File locking + atomic writes                           │
│  └── Wiki-links for relational data                         │
└─────────────────────────────────────────────────────────────┘
```

## Testing

Vectra QA has **79 unit tests** covering:

- **Vault Operations**: Read/write, concurrency, atomic writes, path security
- **Agent Spawning**: Spawn, terminate, lifecycle management
- **Browser Tools**: Navigation, interaction, screenshot, console capture
- **MCP Tools**: Query selector, simulate interaction, network interception
- **Feature Modules**: Auth, visual regression, performance, API contract, accessibility, multi-browser
- **LLM Router**: Provider routing, response caching
- **Orchestrator**: Planning, execution, reporting
- **Models**: Pydantic validation, path traversal protection

```bash
# Run all tests
python -m pytest tests/ -v

# Run with coverage
python -m pytest tests/ --cov=mcp_server --cov=agents

# Run specific test file
python -m pytest tests/unit/test_features.py -v
```

## Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on adding new MCP skills, tuning agent personas, and local development setup.

## License

MIT License - see [LICENSE](LICENSE) for details.

---

**Built with obsession by the Vectra QA team.**
