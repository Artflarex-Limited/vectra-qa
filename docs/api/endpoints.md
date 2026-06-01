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

## Health Checks

### Liveness Probe

```http
GET /health
```

Returns 200 if the server is running.

**Response:**

```json
{
  "status": "ok"
}
```

### Readiness Probe

```http
GET /ready
```

Returns 200 if the server is ready to accept requests (vault accessible).

**Response:**

```json
{
  "status": "ready",
  "vault_accessible": true,
  "timestamp": "2026-06-01T12:00:00Z"
}
```

### Metrics

```http
GET /metrics
```

Returns Prometheus-compatible metrics (if enabled).

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

### Spawn Agent

```http
POST /api/agents/spawn
Content-Type: application/json
```

Spawn a new specialized agent.

**Parameters:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `role` | string | Yes | Agent role: `ui_explorer`, `data_validator`, `auth_tester`, `performance_tester`, `accessibility_tester`, `visual_regression_tester`, `api_contract_tester`, `multi_browser_tester` |
| `objective` | string | Yes | Clear task description |
| `memory_node` | string | Yes | Target vault path (e.g., `Runs/Login_Test.md`) |

**Response:**

```json
{
  "status": "active",
  "agent_id": "auth_tester-20260115-120000-abc123",
  "role": "auth_tester",
  "memory_node": "Runs/Login_Test.md",
  "timestamp": "2026-01-15T12:00:00Z"
}
```

---

## Feature Tests

Feature tests run directly without spawning agents — faster for specific checks.

### Authentication Test

```http
POST /api/tests/auth
Content-Type: application/json
```

Test login/logout flows with security validation.

**Parameters:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `login_url` | string | Yes | Login page URL |
| `username` | string | No | Test username |
| `password` | string | No | Test password |
| `logout_url` | string | No | Logout page URL |

**Response:**

```json
{
  "status": "pass",
  "findings": [
    {
      "title": "Secure Session Cookie",
      "description": "Session cookie uses HttpOnly, Secure, SameSite=Strict",
      "severity": "info"
    }
  ],
  "metrics": {
    "login_duration_ms": 1200,
    "logout_duration_ms": 300
  },
  "duration_seconds": 5.2,
  "timestamp": "2026-01-15T12:00:00Z"
}
```

### Performance Test

```http
POST /api/tests/performance
Content-Type: application/json
```

Measure Core Web Vitals and page performance.

**Parameters:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `url` | string | Yes | URL to test |
| `thresholds` | object | No | Custom thresholds `{lcp_ms, fid_ms, cls, ttfb_ms, fcp_ms, tbt_ms}` |

**Response:**

```json
{
  "status": "pass",
  "findings": [],
  "metrics": {
    "ttfb_ms": 120,
    "fcp_ms": 850,
    "lcp_ms": 1800,
    "cls": 0.05,
    "navigation_time_ms": 2300,
    "total_transfer_size_bytes": 1240000,
    "resource_count": 45
  },
  "duration_seconds": 8.5,
  "timestamp": "2026-01-15T12:00:00Z"
}
```

### Accessibility Test

```http
POST /api/tests/accessibility
Content-Type: application/json
```

Run accessibility checks (axe-core + manual).

**Parameters:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `url` | string | Yes | URL to test |
| `standard` | string | No | WCAG standard: `wcag2a`, `wcag2aa` (default), `wcag21aa` |

**Response:**

```json
{
  "status": "warning",
  "findings": [
    {
      "title": "Missing Alt Text",
      "description": "3 images without alt attributes",
      "severity": "medium"
    }
  ],
  "metrics": {
    "axe_violations": 2,
    "manual_issues": 1
  },
  "duration_seconds": 4.2,
  "timestamp": "2026-01-15T12:00:00Z"
}
```

### Visual Regression Test

```http
POST /api/tests/visual
Content-Type: application/json
```

Compare page screenshot against baseline.

**Parameters:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `url` | string | Yes | URL to capture |
| `name` | string | No | Baseline name identifier |

**Response:**

```json
{
  "status": "pass",
  "findings": [
    {
      "title": "Baseline Created",
      "description": "New baseline saved for 'homepage'",
      "severity": "info"
    }
  ],
  "metrics": {
    "pixel_difference_percent": 0.0,
    "baseline_path": "Baselines/homepage.png"
  },
  "duration_seconds": 3.1,
  "timestamp": "2026-01-15T12:00:00Z"
}
```

### API Contract Test

```http
POST /api/tests/api-contract
Content-Type: application/json
```

Validate API response against OpenAPI schema.

**Parameters:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `base_url` | string | Yes | API base URL |
| `endpoint` | string | Yes | Endpoint path (e.g., `/api/v1/users`) |
| `method` | string | Yes | HTTP method: `GET`, `POST`, `PUT`, `DELETE`, `PATCH` |
| `schema_path` | string | No | Path to OpenAPI schema file |
| `body` | object | No | Request body for POST/PUT |

**Response:**

```json
{
  "status": "pass",
  "findings": [],
  "metrics": {
    "http_status": 200,
    "response_time_ms": 150,
    "schema_valid": true
  },
  "duration_seconds": 2.5,
  "timestamp": "2026-01-15T12:00:00Z"
}
```

### Multi-Browser Test

```http
POST /api/tests/multi-browser
Content-Type: application/json
```

Run smoke tests across Chromium, Firefox, and WebKit.

**Parameters:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `url` | string | Yes | URL to test |

**Response:**

```json
{
  "chromium": {
    "status": "pass",
    "metrics": {"http_status": 200, "load_time_ms": 1200}
  },
  "firefox": {
    "status": "pass",
    "metrics": {"http_status": 200, "load_time_ms": 1500}
  },
  "webkit": {
    "status": "pass",
    "metrics": {"http_status": 200, "load_time_ms": 1300}
  },
  "duration_seconds": 12.5,
  "timestamp": "2026-01-15T12:00:00Z"
}
```

---

## Traditional Tests

### Run Test

```http
POST /api/tests/run
Content-Type: application/x-www-form-urlencoded
```

Launch a traditional agent-based test.

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

---

## Response Format

All feature test responses follow a standardized format:

```json
{
  "status": "pass|warning|fail",
  "findings": [
    {
      "title": "Human-readable title",
      "description": "Detailed explanation",
      "severity": "critical|high|medium|low|info"
    }
  ],
  "metrics": {
    "key": "value"
  },
  "duration_seconds": 5.2,
  "timestamp": "2026-01-15T12:00:00Z"
}
```

### Status Definitions

| Status | Meaning |
|--------|---------|
| `pass` | All checks passed, no critical/high findings |
| `warning` | Some checks exceeded thresholds (high findings) |
| `fail` | Critical failures or test execution errors |

### Severity Levels

| Severity | Action Required |
|----------|----------------|
| `critical` | Immediate attention — security risk or broken functionality |
| `high` | Should fix before release — performance or accessibility issue |
| `medium` | Plan to fix — minor usability or standards compliance |
| `low` | Nice to have — optimization opportunity |
| `info` | No action — informational finding |
