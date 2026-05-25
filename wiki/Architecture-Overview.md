# Architecture Overview

Vectra QA uses a distributed multi-agent architecture with an Obsidian Vault as the shared memory layer.

## Components

### 1. Command Center
- FastAPI backend with HTMX frontend
- Real-time updates via Server-Sent Events
- Chatbot interface for natural language testing

### 2. MCP Server
- Tool registry for agent management
- Spawns and monitors agent processes
- JSON-RPC over HTTP

### 3. Agent Workers
- **UI Explorer**: Playwright-based browser automation
- **Data Validator**: API monitoring and validation
- Custom agents can be added

### 4. Obsidian Vault
- Markdown files with YAML frontmatter
- Shared memory for all agents
- Human-readable and LLM-compatible

## Data Flow

```
User → Dashboard → Command Center → MCP Server → Agent Worker
                                           ↓
User ← Dashboard ← SSE Stream ← Obsidian Vault ← Agent Worker
```

## Communication

Agents communicate through the vault (not direct messaging):
1. Agent writes findings to vault
2. Vault Watcher detects change
3. Command Center broadcasts via SSE
4. Dashboard updates in real-time

## Why Obsidian?

- **Human Readable**: Markdown is easy to read and edit
- **LLM Native**: Large language models understand Markdown
- **No Dependencies**: Just the filesystem
- **Version Control**: Git-friendly format
- **Knowledge Graph**: Wiki-links create semantic connections

## Learn More

- [Full Architecture Docs](https://vectra-qa.artflarex.com/architecture/overview/)
- [System Components](https://vectra-qa.artflarex.com/architecture/components/)
- [Memory Layer](https://vectra-qa.artflarex.com/architecture/memory-layer/)