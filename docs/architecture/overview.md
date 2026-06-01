# Architecture Overview

Vectra QA follows a distributed multi-agent architecture where specialized agents collaborate to test web applications autonomously.

## High-Level Architecture

```mermaid
graph TB
    subgraph "User Layer"
        U[User]
        D[Dashboard
HTMX + SSE]
    end

    subgraph "Control Layer"
        CC[Command Center
FastAPI + SSE]
        CH[Chatbot Engine
LLM Router]
    end

    subgraph "Tool Layer"
        MCP[MCP Server
Tool Registry]
        LLM[LLM Router
Multi-Provider + Cache]
        FT[Feature Testers
Auth / Perf / A11y / Visual]
    end

    subgraph "Agent Layer"
        O[Orchestrator Agent
LLM-Driven Planning]
        UE[UI Explorer
LLM observe-plan-act]
        DV[Data Validator
Network Interception]
        AT[Auth Tester
Security Validation]
        PT[Performance Tester
Core Web Vitals]
        VT[Visual Regression
Screenshot Compare]
    end

    subgraph "Infrastructure Layer"
        BP[BrowserPool
Max 10 Concurrent]
        RT[Resource Tracker
Steps / Time / LLM Limits]
        SM[State Manager
SIGTERM Persistence]
        TQ[Task Queue
Redis / In-Memory]
    end

    subgraph "Memory Layer"
        V[Obsidian Vault
Markdown + YAML]
        R[Redis
Cache + Queue]
    end

    U -- HTTP --> D
    D -- HTMX/SSE --> CC
    U -- Chat --> CH
    CH -- LLM --> LLM
    CC -- JSON-RPC --> MCP
    MCP -- Spawn --> UE
    MCP -- Spawn --> DV
    MCP -- Spawn --> AT
    MCP -- Spawn --> PT
    MCP -- Spawn --> VT
    MCP -- Direct Call --> FT
    UE -- Read/Write --> V
    DV -- Read/Write --> V
    AT -- Read/Write --> V
    PT -- Read/Write --> V
    VT -- Read/Write --> V
    CC -- Read --> V
    O -- Coordinate --> MCP
    LLM -- Cache --> R
    TQ -- Enqueue/Dequeue --> R
    BP -- Manage --> UE
    BP -- Manage --> AT
    RT -- Monitor --> UE
    RT -- Monitor --> PT
    SM -- Backup --> V
```

## Key Principles

### 1. Agent-Centric Design

Instead of writing test scripts, you **deploy agents** with objectives. Each agent:

- Has a unique behavioral DNA (persona from `soul.md` and `agents.md`)
- Maintains its own memory in the Obsidian Vault
- Communicates through the vault (not direct messaging)
- Auto-terminates after mission completion
- Uses LLM reasoning for every decision (no keyword matching)

### 2. Filesystem as Message Bus

Agents don't use HTTP APIs or message queues to communicate. They read/write **Markdown files** in the Obsidian Vault:

- **Frontmatter** (YAML) for structured state (status, metrics, timestamps)
- **Content** for findings and logs
- **Wiki-links** (`[[ ]]`) for semantic relationships between tests
- **File locking** prevents corruption during concurrent writes
- **Atomic writes** ensure no partial files on crash

### 3. Real-Time Observation

The Command Center doesn't poll. It uses:

- **Watchdog** file system events → instant updates
- **Server-Sent Events** → push to browser
- **HTMX** → partial page updates without full reloads

### 4. Production Reliability

- **Graceful Shutdown**: SIGTERM handlers persist agent state
- **Health Checks**: `/health`, `/ready`, `/metrics` endpoints
- **Resource Limits**: BrowserPool (max 10), AgentResourceTracker (steps/time/LLM limits)
- **Test Isolation**: Fresh browser contexts, cookie clearing between agents
- **State Backup**: Orphaned agents detected and marked on startup

## Component Breakdown

### Command Center

- **FastAPI** backend with async endpoints
- **HTMX** frontend for hypermedia-driven UI
- **SSE streams** for live data (agents, orchestrator, results)
- **Chatbot engine** with intent classification
- **Health endpoints**: `/health`, `/ready`, `/metrics`

### MCP Server

- **Tool registry** exposing 15+ tools (spawn, read/write, feature tests)
- **Agent spawner** managing subprocess lifecycle
- **Pydantic validation** for all tool inputs
- **Tenacity retry** logic with exponential backoff
- **Structured logging** with structlog
- **SSE transport** for agent updates

### Feature Testers (Direct Execution)

No agent spawning needed — execute directly via MCP tools:

- **`test_auth_flow`**: Login/logout with security validation
- **`test_performance`**: Core Web Vitals + Lighthouse CI
- **`test_accessibility`**: axe-core + manual WCAG checks
- **`test_visual_regression`**: Screenshot baseline comparison
- **`test_api_contract`**: OpenAPI schema validation
- **`test_multi_browser`**: Chromium/Firefox/WebKit smoke tests

### Agent Workers (LLM-Driven Exploration)

For complex scenarios requiring AI reasoning:

- **UI Explorer**: Playwright + LLM observe-plan-act loop
- **Data Validator**: Network interception and API validation
- **Auth Tester**: Security-focused authentication testing
- **Performance Tester**: Comprehensive performance audit
- **Accessibility Tester**: Deep accessibility analysis
- **Visual Regression Tester**: Visual consistency checks
- **API Contract Tester**: Schema compliance validation
- **Multi-Browser Tester**: Cross-browser compatibility
- **Orchestrator**: Mission planning and multi-agent coordination

### Infrastructure

- **BrowserPool**: Limits concurrent browser instances (max 10)
- **AgentResourceTracker**: Enforces step/time/LLM call limits per agent
- **StateManager**: Handles SIGTERM, persists state, restores on startup
- **TaskQueue**: Redis-backed or in-memory priority queue for distributed workers
- **LLMCache**: SHA256-based response cache with TTL and disk persistence

### Obsidian Vault

- **Global nodes**: System state, logs, chat history, agent state backups
- **Run nodes**: Individual test results with YAML frontmatter
- **Templates**: Agent spawn templates
- **Screenshots**: Visual test evidence
- **Baselines**: Visual regression baseline images

## Data Flow

### Feature Test Execution Flow

```mermaid
sequenceDiagram
    participant U as User
    participant D as Dashboard
    participant CC as Command Center
    participant MCP as MCP Server
    participant FT as Feature Tester
    participant BP as BrowserPool
    participant V as Obsidian Vault

    U->>D: Select feature test
    D->>CC: POST /api/tests/run
    CC->>MCP: execute_tool("test_performance", {...})
    MCP->>MCP: Validate with Pydantic
    MCP->>MCP: Check LLM cache
    MCP->>FT: Run performance test
    FT->>BP: Request browser instance
    BP->>FT: Return browser
    FT->>FT: Navigate + measure metrics
    FT->>V: Write results
    FT->>BP: Release browser
    MCP->>MCP: Cache LLM response
    MCP->>CC: Return results
    CC->>D: SSE: test_complete
```

### Agent-Based Test Execution Flow

```mermaid
sequenceDiagram
    participant U as User
    participant D as Dashboard
    participant CC as Command Center
    participant MCP as MCP Server
    participant A as Agent Worker
    participant V as Obsidian Vault
    participant RT as Resource Tracker

    U->>D: Submit complex test
    D->>CC: POST /api/tests/run
    CC->>MCP: spawn_agent(role, objective)
    MCP->>RT: Register agent (steps/time limits)
    MCP->>V: Create memory node
    MCP->>A: Start subprocess
    A->>A: LLM planning + browser tests
    A->>RT: Report step usage
    A->>V: Update progress
    V->>CC: File change detected
    CC->>D: SSE: agent_update
    A->>V: Write findings
    A->>V: status=completed
    RT->>MCP: Agent finished
    MCP->>CC: Agent done
    CC->>D: SSE: test_complete
```

### Orchestrator Flow (Multi-Agent)

```mermaid
sequenceDiagram
    participant U as User
    participant O as Orchestrator
    participant LLM as LLM Router
    participant MCP as MCP Server
    participant A1 as Agent 1
    participant A2 as Agent 2
    participant V as Obsidian Vault

    U->>O: "Test my e-commerce site"
    O->>LLM: Plan tests
    LLM-->>O: Test plan (5 tasks)
    O->>V: Create Test_Run_Master
    
    par Parallel Group 1
        O->>MCP: spawn_agent(ui_explorer, "Test homepage")
        MCP->>A1: Start worker
        A1->>V: Write results
    and Parallel Group 1
        O->>MCP: spawn_agent(auth_tester, "Test login")
        MCP->>A2: Start worker
        A2->>V: Write results
    end
    
    O->>V: Compile final report
    O-->>U: Report complete
```

### Chat Flow

```mermaid
sequenceDiagram
    participant U as User
    participant CH as Chat Widget
    participant CE as Chat Engine
    participant LLM as LLM Router
    participant V as Obsidian Vault

    U->>CH: "Test contact form"
    CH->>CE: POST /api/chat/message
    CE->>V: Save user message
    CE->>LLM: Classify intent
    LLM-->>CE: intent=plan_tests
    CE->>LLM: Extract test plan
    LLM-->>CE: {url, tests}
    CE->>V: Save assistant message
    CE-->>CH: Return plan for confirmation
    U->>CH: Click "Run"
    CH->>CE: POST /api/chat/execute
    CE->>MCP: Spawn agents
    CE->>V: Save execution log
```

## Technology Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | FastAPI, Python 3.12+ |
| **Frontend** | Vanilla HTML/CSS/JS, HTMX |
| **Real-Time** | Server-Sent Events |
| **Browser Automation** | Playwright (Chromium, Firefox, WebKit) |
| **Memory** | Obsidian Vault (Markdown + YAML + File Locking) |
| **LLM Routing** | OpenAI, Anthropic, Google, MiniMax, Kimi, Local |
| **LLM Cache** | SHA256-based with TTL and disk persistence |
| **Task Queue** | Redis (distributed) or In-Memory (single-node) |
| **Validation** | Pydantic v2 |
| **Logging** | structlog |
| **Retry Logic** | tenacity |
| **Container** | Docker, Docker Compose |
| **Documentation** | MkDocs Material |
| **CI/CD** | GitHub Actions |

## Resource Efficiency

Unlike traditional testing frameworks that keep browsers open indefinitely:

- **Agents spawn on-demand** — No idle processes
- **Auto-termination** — Workers exit after completion
- **BrowserPool** — Limits concurrent browsers (max 10)
- **LLM Cache** — Reduces API costs by 60-80%
- **Shared vault** — No database connections to maintain
- **Headless by default** — Minimal resource usage
- **Test isolation** — Fresh contexts, cleared cookies between agents

## Scalability

Current architecture supports:

- **10+ concurrent agents** per MCP server (configurable)
- **Distributed workers** via Redis task queue
- **Horizontal scaling** — Multiple MCP servers behind load balancer
- **1000+ test runs** in vault (limited by filesystem)
- **Multiple LLM providers** with automatic fallback

## Performance Benchmarks

| Metric | Value |
|--------|-------|
| Test Suite Execution | ~2.0 seconds (79 tests) |
| LLM Cache Hit Rate | 60-80% (typical) |
| Agent Spawn Time | ~500ms |
| Browser Start Time | ~2-3 seconds |
| Vault Write Latency | ~10ms (SSD) |
