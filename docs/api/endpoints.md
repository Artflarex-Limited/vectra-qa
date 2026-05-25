# API Endpoints

The Command Center exposes a REST API for all operations. All endpoints return JSON unless otherwise specified.

## Base URL

```
http://localhost:3000/api
```

## Authentication

Currently, the API is open (no authentication required for local development). For production, set `MCP_API_KEY` and include it in the `X-API-Key` header.

## Content Types

- **Request**: `application/x-www-form-urlencoded` (forms) or `application/json`
- **Response**: `application/json`

---

## Orchestrator

### Get Status

```http
GET /api/orchestrator/status
```

Returns the current orchestrator status from `Global/Test_Run_Master.md`.

**Response:**
```json
{
  "status": "active",
  "phase": "testing",
  "overall_result": "pending",
  "metrics": {
    "pass": 12,
    "fail": 3,
    "skip": 0
  },
  "active_agents": ["ui_explorer-..."],
  "completed_agents": ["data_validator-..."],
  "thoughts": ["System ready", "Agent spawned"]
}
```

---

## Agents

### List Active Agents

```http
GET /api/agents/active
```

Returns all currently active agents.

**Response:**
```json
{
  "agents": [
    {
      "agent_id": "ui_explorer-20260115-120000-abc123",
      "role": "ui_explorer",
      "status": "active",
      "objective": "Test homepage at https://example.com",
      "progress_percent": 75,
      "last_action": "Checking navigation links"
    }
  ]
}
```

---

## Tests

### Run Test

```http
POST /api/tests/run
Content-Type: application/x-www-form-urlencoded
```

Launch a new test.

**Parameters:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `url` | string | Yes | Target URL to test |
| `test_type` | string | Yes | Test type (homepage, navigation, contact, api, accessibility, responsive, full) |

**Response:**
```json
{
  "status": "success",
  "message": "Test 'homepage' initiated for https://example.com",
  "agent_id": "ui_explorer-20260115-120000-abc123",
  "memory_node": "Runs/Homepage_Test_20260115.md",
  "timestamp": "2026-01-15T12:00:00Z"
}
```

### List Test Types

```http
GET /api/tests/types
```

Returns available test types.

**Response:**
```json
{
  "types": [
    {"id": "homepage", "name": "Homepage", "description": "..."},
    {"id": "navigation", "name": "Navigation", "description": "..."}
  ]
}
```

---

## Results

### List All Results

```http
GET /api/results
```

Returns all test runs sorted by date (newest first).

**Response:**
```json
{
  "results": [
    {
      "agent_id": "ui_explorer-...",
      "role": "ui_explorer",
      "status": "completed",
      "result": "pass",
      "objective": "Test homepage at https://example.com",
      "progress_percent": 100,
      "screenshots": ["..."]
    }
  ],
  "count": 42
}
```

### Get Result

```http
GET /api/results/{agent_id}
```

Returns detailed result for a specific agent.

**Response:**
```json
{
  "agent_id": "ui_explorer-...",
  "role": "ui_explorer",
  "status": "completed",
  "result": "pass",
  "objective": "...",
  "sections": [
    {
      "title": "Page Information",
      "status": "pass",
      "findings": [...],
      "metrics": {"URL": "...", "Status": "200"}
    }
  ],
  "recommendations": ["Add meta description"],
  "summary": {
    "pass": 5,
    "fail": 0,
    "warning": 1,
    "total": 6
  }
}
```

---

## Chatbot

### Send Message

```http
POST /api/chat/message
Content-Type: application/x-www-form-urlencoded
```

Process a chat message and get Vectra's response.

**Parameters:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `message` | string | Yes | User message |
| `stream` | boolean | No | Enable SSE streaming (default: false) |

**Response (plan):**
```json
{
  "type": "plan",
  "intent": "plan_tests",
  "plan": {
    "url": "https://example.com",
    "tests": ["contact"],
    "test_configs": [...]
  },
  "message": "I'll run the following tests..."
}
```

**Response (chat):**
```json
{
  "type": "chat",
  "intent": "chat",
  "message": "I can help you with that!"
}
```

### Get History

```http
GET /api/chat/history?limit=50
```

Returns conversation history.

**Response:**
```json
{
  "messages": [
    {"role": "user", "content": "Test homepage", "timestamp": "..."},
    {"role": "assistant", "content": "I'll help you...", "timestamp": "..."}
  ],
  "count": 42
}
```

### Execute Plan

```http
POST /api/chat/execute
Content-Type: application/x-www-form-urlencoded
```

Execute a confirmed test plan.

**Parameters:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `url` | string | Yes | Target URL |
| `tests` | string | Yes | Comma-separated test types |

**Response:**
```json
{
  "status": "success",
  "message": "Launched 2 test(s)",
  "agent_ids": ["ui_explorer-...", "data_validator-..."],
  "tests": ["homepage", "api"],
  "url": "https://example.com"
}
```

### Interpret Results

```http
GET /api/chat/interpret/{agent_id}
```

Get LLM-interpreted results for a specific test.

**Response:**
```json
{
  "agent_id": "ui_explorer-...",
  "interpretation": "The test found 2 critical issues...",
  "result_data": {...}
}
```

---

## Server-Sent Events

### Main Stream

```http
GET /api/sse/stream
Content-Type: text/event-stream
```

Primary SSE endpoint streaming orchestrator + agents + nodes updates every 2 seconds.

**Event format:**
```
data: {"orchestrator": {...}, "agents": [...], "nodes": {...}}
```

### Agent Stream

```http
GET /api/sse/agents
Content-Type: text/event-stream
```

Agent-only updates every 3 seconds.

### Result Stream

```http
GET /api/sse/results/{agent_id}
Content-Type: text/event-stream
```

Agent-specific updates for a single test run.

**Event format:**
```
data: {
  "agent_id": "...",
  "status": "active",
  "progress_percent": 75,
  "last_action": "...",
  "screenshots": [...]
}
```

---

## Nodes

### List Global Nodes

```http
GET /api/nodes/global
```

Returns all global memory nodes.

### Get Node

```http
GET /api/nodes/{node_path}
```

Returns a specific node by path (e.g., `Global/Test_Run_Master.md`).

---

## Error Responses

All errors return JSON with an `error` field:

```json
{
  "error": "Test result not found"
}
```

Common status codes:

| Code | Meaning |
|------|---------|
| 400 | Bad request (invalid parameters) |
| 404 | Not found (agent/node missing) |
| 500 | Server error (spawn failed, LLM error) |

---

## Rate Limits

No rate limiting is currently implemented. For production use, consider adding:
- Per-IP rate limiting
- Concurrent agent limits
- LLM API quota management