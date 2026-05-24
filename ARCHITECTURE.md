# Architecture Deep Dive

## System Overview

Vectra QA operates on a **distributed agent architecture** where testing is not scripted but **explored**. The system follows a continuous lifecycle: perception, planning, delegation, execution, logging, and visualization.

### The Test Lifecycle

```
User Story + RAG Context
         ↓
[Orchestrator] Analyzes requirements, formulates test plan
         ↓
spawn_agent(role, objective, memory_node)
         ↓
[UI Explorer] ←→ [Data Validator]  (parallel or sequential)
         ↓                    ↓
Obsidian Memory Nodes     Obsidian Memory Nodes
         ↓                    ↓
[Orchestrator] Reads results, compiles report
         ↓
[Test_Run_Master.md] + [Command Center Dashboard]
```

### Phase 1: Perception

The Orchestrator receives a user story or pulls context from a vector store (RAG). It understands the feature under test, the expected user flows, and the critical data paths.

### Phase 2: Planning

The Orchestrator decomposes the test into discrete, atomic tasks:

- **UI Tasks**: "Verify the login form renders correctly and is keyboard accessible"
- **Data Tasks**: "Intercept the login API and validate the JWT payload structure"
- **Integration Tasks**: "Verify the session cookie is set after successful login"

Each task is assigned a **memory node** in the Obsidian Vault.

### Phase 3: Delegation

The Orchestrator calls `spawn_agent(role, objective, memory_node)` via the MCP Tool Server. This:

1. Generates a unique agent ID
2. Creates an agent memory node from a template
3. Launches an isolated process with the agent's `soul.md` and `agents.md` context
4. Updates `[[Test_Run_Master]]` frontmatter to track the active agent

### Phase 4: Execution

Agents execute their objectives using MCP tools:

- **UI Explorer**: `query_selector()`, `simulate_interaction()`, `capture_dom_snapshot()`
- **Data Validator**: `intercept_network_request()`, `validate_schema()`, `decode_jwt()`

Agents write their findings directly to their assigned Obsidian memory nodes.

### Phase 5: Logging

Agents update their memory nodes with:

- **YAML frontmatter**: Structured metrics (selectors tested, payloads validated, anomalies found)
- **Markdown content**: Human-readable findings with wiki-links to related nodes
- **Wiki-links**: Semantic connections to parent runs and sibling agents

### Phase 6: Visualization

The Command Center backend watches the Obsidian Vault for file changes. It:

1. Parses YAML frontmatter for status updates
2. Extracts agent activity from Markdown content
3. Streams updates via Server-Sent Events (SSE) to the HTMX frontend
4. Renders a live-updating dark mode dashboard

## System Architecture Diagram

```mermaid
graph TB
    subgraph User_Layer["👤 User Layer"]
        User[User / CI Pipeline]
        Dashboard[🎛️ Command Center UI<br/>HTMX + Tailwind + SSE]
    end

    subgraph Agent_Layer["🤖 Agent Layer"]
        Orchestrator[🧠 Orchestrator<br/>Test Manager Agent]
        Spawner[⚡ Agent Spawner<br/>Process Manager]
        
        subgraph Active_Agents["Active Agents"]
            UI[🔍 UI Explorer<br/>Frontend Specialist]
            Data[🔬 Data Validator<br/>Backend Specialist]
            Custom[➕ Custom Agents...]
        end
    end

    subgraph MCP_Layer["🛠️ MCP Tool Layer"]
        MCPServer[MCP Server<br/>stdio / SSE Transport]
        
        subgraph Tools["Available Tools"]
            Spawn[spawn_agent]
            Terminate[terminate_agent]
            ReadNode[read_obsidian_node]
            WriteNode[write_obsidian_node]
            UpdateFM[update_frontmatter]
            QueryDOM[query_selector]
            Simulate[simulate_interaction]
            Intercept[intercept_network_request]
        end
    end

    subgraph Memory_Layer["📊 Memory Layer"]
        Vault[(Obsidian Vault<br/>Local Filesystem)]
        
        subgraph Global_Nodes["Global Nodes"]
            Master[[Test_Run_Master.md]]
            UIState[[UI_State_Log.md]]
            DataLog[[Data_Validation_Log.md]]
        end
        
        subgraph Run_Nodes["Run-Specific Nodes"]
            Run1[Runs/Login_Flow_UI.md]
            Run2[Runs/Login_API_Validation.md]
        end
    end

    subgraph Infra_Layer["⚙️ Infrastructure"]
        VaultWatcher[Vault File Watcher<br/>watchdog]
        SSEBroker[SSE Broker<br/>FastAPI StreamingResponse]
        Browser[Browser Automation<br/>Playwright / Puppeteer]
    end

    User -->|Submit Test Request| Orchestrator
    Dashboard -->|Poll /api/sse/stream| SSEBroker
    
    Orchestrator -->|spawn_agent()| MCPServer
    Orchestrator -->|read_node()| Vault
    Orchestrator -->|write report| Master
    
    MCPServer -->|execute| Tools
    Spawner -->|launch process| UI
    Spawner -->|launch process| Data
    
    UI -->|query_selector()| Browser
    UI -->|write findings| Run1
    Data -->|intercept_network_request()| Browser
    Data -->|write findings| Run2
    
    VaultWatcher -->|detect changes| SSEBroker
    Vault -->|serve files| VaultWatcher
    
    Master -.->|wiki-links| Run1
    Master -.->|wiki-links| Run2
    Run1 -.->|cross-reference| Run2
    
    style Orchestrator fill:#4c1d95,stroke:#8b5cf6,color:#fff
    style UI fill:#065f46,stroke:#10b981,color:#fff
    style Data fill:#1e3a8a,stroke:#3b82f6,color:#fff
    style Vault fill:#78350f,stroke:#f59e0b,color:#fff
    style Dashboard fill:#7c2d12,stroke:#f97316,color:#fff
```

## The Memory Layer

### Why Obsidian?

We chose Obsidian (Markdown files on a local filesystem) over traditional databases for several reasons:

1. **LLM Native**: Markdown is the primary training format for most large language models. Agents read and write it naturally.
2. **Human Readable**: Test results are documents, not database rows. You can open them in any text editor.
3. **Relational**: Wiki-links (`[[ ]]`) create a semantic graph of test findings. "The login button click (in [[UI_State_Log]]) triggered the API call (in [[Data_Validation_Log]])."
4. **Version Control**: Markdown files diff beautifully in git. Track how your test coverage evolves.
5. **Visual Graph**: Open the vault in Obsidian to see a visual network of your test suite.

### YAML Frontmatter Schema

Every memory node uses YAML frontmatter for structured state. Here's the schema for `[[UI_State_Log.md]]`:

```yaml
---
# Agent Identity
agent_role: ui_explorer
agent_id: ui-explorer-20250524144500-a1b2c3
parent_run: test-run-001

# Lifecycle
status: active          # spawned | active | completed | failed | terminated
last_action: query_selector
objective: Verify login form rendering and accessibility
spawned_at: 2025-05-24T14:45:00Z
terminated_at: null

# Results
result: pending         # pending | pass | fail
confidence_score: 87    # 0-100

# Metrics
selectors_tested:
  - "#login-form"
  - "#username"
  - "#password"
  - "#login-btn"
interactions_logged: 4
anomalies_found: 2

# Relational Memory
related_nodes:
  - "[[Test_Run_Master]]"
  - "[[Data_Validation_Log]]"
  - "[[Runs/Login_Flow_Validation.md]]"
---
```

### Wiki-Link Protocol

Agents use wiki-links to create a semantic graph:

```markdown
## Interaction: Login Button Click

- **Selector**: `#login-btn`
- **Triggered by**: User action logged in [[UI_State_Log]]
- **Backend Correlation**: API call intercepted in [[Data_Validation_Log]]
- **Parent Run**: Part of [[Test_Run_Master]] test suite
- **Related Issue**: Similar to [[Bugs/Modal_Focus_Trap_2024-05-20]]
```

This creates a navigable web of test knowledge that both agents and humans can explore.

## Agent Communication Protocol (A2A)

Agents communicate indirectly via the Obsidian Vault. This is **async, decoupled, and fault-tolerant**:

1. **Orchestrator → Agent**: Writes the task objective to the agent's memory node frontmatter
2. **Agent → Orchestrator**: Updates `status: completed` and writes findings
3. **Agent → Agent**: Cross-references findings via wiki-links in Markdown content
4. **Orchestrator → Dashboard**: Updates `[[Test_Run_Master]]`, which the file watcher detects

There are no direct HTTP calls between agents. The filesystem is the message bus.

## MCP Tool Server

The MCP Server exposes tools via stdio or SSE transport:

```python
# Example: Spawn a UI Explorer agent
execute_tool("spawn_agent", {
    "role": "ui_explorer",
    "objective": "Verify checkout flow accessibility",
    "memory_node": "Runs/Checkout_UI.md"
})

# Example: Update a node's frontmatter
execute_tool("update_frontmatter", {
    "node_path": "Runs/Checkout_UI.md",
    "updates": {
        "status": "completed",
        "result": "pass",
        "confidence_score": 92
    }
})
```

Tools are registered in `mcp_server/tools.py` and automatically exposed via the MCP protocol.

## Command Center Dashboard

The dashboard is intentionally lightweight:

- **Backend**: FastAPI with Server-Sent Events (`/api/sse/stream`)
- **Frontend**: Vanilla HTML with HTMX for dynamic updates
- **Styling**: Tailwind CSS with a strict dark mode palette (`bg-gray-900`, `text-gray-100`)
- **Real-time**: File watcher detects Obsidian vault changes and pushes updates via SSE

This architecture avoids the complexity of React/Vue while providing a rich, live-updating experience.
