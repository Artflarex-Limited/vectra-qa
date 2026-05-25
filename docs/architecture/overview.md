# Architecture Overview

Vectra QA follows a distributed multi-agent architecture where specialized agents collaborate to test web applications autonomously.

## High-Level Architecture

```mermaid
graph TB
    subgraph "User Layer"
        U[User]
        D[Dashboard]
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
Multi-Provider]
    end

    subgraph "Agent Layer"
        O[Orchestrator Agent]
        UE[UI Explorer
Worker]
        DV[Data Validator
Worker]
    end

    subgraph "Memory Layer"
        V[Obsidian Vault
Markdown + YAML]
    end

    U -- HTTP --> D
    D -- HTMX/SSE --> CC
    U -- Chat --> CH
    CH -- LLM --> LLM
    CC -- JSON-RPC --> MCP
    MCP -- Spawn --> UE
    MCP -- Spawn --> DV
    UE -- Read/Write --> V
    DV -- Read/Write --> V
    CC -- Read --> V
    O -- Coordinate --> MCP
```

## Key Principles

### 1. Agent-Centric Design

Instead of writing test scripts, you **deploy agents** with objectives. Each agent:
- Has a unique behavioral DNA (persona)
- Maintains its own memory
- Communicates through the vault (not direct messaging)
- Auto-terminates after mission completion

### 2. Filesystem as Message Bus

Agents don't use HTTP APIs or message queues to communicate. They read/write **Markdown files** in the Obsidian Vault:
- **Frontmatter** (YAML) for structured state
- **Content** for findings and logs
- **Wiki-links** for semantic relationships

### 3. Real-Time Observation

The Command Center doesn't poll. It uses:
- **Watchdog** file system events → instant updates
- **Server-Sent Events** → push to browser
- **HTMX** → partial page updates without full reloads

## Component Breakdown

### Command Center
- **FastAPI** backend with async endpoints
- **HTMX** frontend for hypermedia-driven UI
- **SSE streams** for live data (agents, orchestrator, results)
- **Chatbot engine** with intent classification

### MCP Server
- **Tool registry** exposing spawn/read/write operations
- **Agent spawner** managing subprocess lifecycle
- **JSON-RPC** over HTTP for tool execution
- **SSE transport** for agent updates

### Agent Workers
- **UI Explorer**: Playwright-based browser automation
- **Data Validator**: Network interception and API validation
- **Orchestrator**: Mission planning and coordination (planned)

### Obsidian Vault
- **Global nodes**: System state, logs, chat history
- **Run nodes**: Individual test results
- **Templates**: Agent spawn templates
- **Screenshots**: Visual test evidence

## Data Flow

### Test Execution Flow

```mermaid
sequenceDiagram
    participant U as User
    participant D as Dashboard
    participant CC as Command Center
    participant MCP as MCP Server
    participant A as Agent Worker
    participant V as Obsidian Vault

    U->>D: Submit test request
    D->>CC: POST /api/tests/run
    CC->>MCP: spawn_agent(role, objective)
    MCP->>V: Create memory node
    MCP->>A: Start subprocess
    A->>A: Execute browser tests
    A->>V: Update progress
    V->>CC: File change detected
    CC->>D: SSE: agent_update
    A->>V: Write findings
    A->>V: status=completed
    MCP->>CC: Agent done
    CC->>D: SSE: test_complete
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
| **Backend** | FastAPI, Python 3.11+ |
| **Frontend** | Vanilla HTML/CSS/JS, HTMX |
| **Real-Time** | Server-Sent Events |
| **Browser Automation** | Playwright |
| **Memory** | Obsidian Vault (Markdown + YAML) |
| **LLM Routing** | OpenAI, Anthropic, Google, MiniMax, Kimi, Local |
| **Container** | Docker, Docker Compose |
| **Documentation** | MkDocs Material |

## Resource Efficiency

Unlike traditional testing frameworks that keep browsers open indefinitely:

- **Agents spawn on-demand** — No idle processes
- **Auto-termination** — Workers exit after completion
- **Shared vault** — No database connections to maintain
- **Headless by default** — Minimal resource usage

## Scalability Considerations

Current architecture supports:
- **10+ concurrent agents** per MCP server
- **1000+ test runs** in vault (limited by filesystem)
- **Multiple LLM providers** with fallback

Future improvements:
- Agent pooling for faster startup
- Distributed vault (shared filesystem)
- Horizontal MCP server scaling