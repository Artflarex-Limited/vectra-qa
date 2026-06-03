# Quick Reference

Quick lookup for common commands, configurations, and patterns.

## Commands

### Docker

```bash
# Start all services
docker compose up --build

# Start in background
docker compose up -d

# View logs
docker compose logs -f

# Stop all
docker compose down

# Clean restart
docker compose down -v && docker compose up --build

# Restart single service
docker compose restart command-center
```

### Testing

```bash
# Run homepage test
curl -X POST http://localhost:3000/api/tests/run \
  -d "url=https://example.com" \
  -d "test_type=homepage"

# Run full suite
curl -X POST http://localhost:3000/api/tests/run \
  -d "url=https://example.com" \
  -d "test_type=full"

# List results
curl http://localhost:3000/api/results

# Get specific result
curl http://localhost:3000/api/results/{agent_id}
```

### Live QA Engineer

```bash
# Start a session (server sets a session_id cookie)
curl -X POST http://localhost:3000/api/engineer/start \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com"}'

# Send a message (use the cookie returned above)
curl -X POST http://localhost:3000/api/engineer/$SID/message \
  -H "Content-Type: application/json" \
  -d '{"message": "Test the contact form"}'

# Stream events (Server-Sent Events)
curl -N http://localhost:3000/api/engineer/$SID/stream

# Get session metrics
curl http://localhost:3000/api/engineer/$SID/metrics

# Resume a session (after page refresh)
curl http://localhost:3000/api/engineer/$SID/resume
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/orchestrator/status` | GET | System status |
| `/api/agents/active` | GET | Active agents |
| `/api/tests/run` | POST | Launch test |
| `/api/tests/types` | GET | Test types |
| `/api/results` | GET | All results |
| `/api/results/{id}` | GET | Specific result |
| `/api/engineer/start` | POST | Start an engineer session |
| `/api/engineer/{sid}/message` | POST | Send a message |
| `/api/engineer/{sid}/stream` | GET | SSE event stream |
| `/api/engineer/{sid}/metrics` | GET | Session metrics |
| `/api/engineer/{sid}/resume` | GET | Rehydrate session |
| `/api/sse/stream` | GET | SSE stream |

## Test Types

| Type | Role | Duration |
|------|------|----------|
| `homepage` | ui_explorer | ~30s |
| `navigation` | ui_explorer | ~60s |
| `contact` | ui_explorer | ~45s |
| `api` | data_validator | ~60s |
| `accessibility` | ui_explorer | ~40s |
| `responsive` | ui_explorer | ~50s |
| `full` | ui_explorer | ~3min |

## File Locations

| File | Path |
|------|------|
| Config | `.env` |
| Vault | `obsidian_vault/` |
| Runs | `obsidian_vault/Runs/` |
| Screenshots | `obsidian_vault/Screenshots/` |
| Agent logs | `obsidian_vault/Runs/*_worker.log` |
| Engineer session node | `obsidian_vault/Runs/EngineerSession_*.md` |

## Status Codes

| Status | Meaning |
|--------|---------|
| `spawned` | Agent created |
| `active` | Agent running |
| `completed` | Tests done |
| `failed` | Error occurred |

| Result | Meaning |
|--------|---------|
| `pass` | All checks passed |
| `fail` | Critical failure |
| `warning` | Non-critical issues |
| `pending` | Still running |

## Severity Levels

| Level | Icon | Action |
|-------|------|--------|
| Critical | 🔴 | Fix immediately |
| High | 🟠 | Fix today |
| Medium | 🟡 | Fix this week |
| Low | 🔵 | Fix when convenient |
| Info | ⚪ | No action |

## Environment Variables Quick Set

```bash
# Minimal setup
export OPENAI_API_KEY=sk-...
export MCP_SERVER_URL=http://localhost:8080

# Development
export HEADLESS=false
export LOG_LEVEL=DEBUG

# Production
export HEADLESS=true
export COMMAND_CENTER_SECRET_KEY=$(openssl rand -hex 32)
```

## Docker Ports

| Service | Port | URL |
|---------|------|-----|
| Command Center | 3000 | http://localhost:3000 |
| MCP Server | 8080 | http://localhost:8080 |

## Common Issues

| Issue | Solution |
|-------|----------|
| Port in use | Change in `.env` |
| Import errors | Activate venv |
| Browser not found | `playwright install` |
| LLM errors | Check API key |
| No data in dashboard | Start vault watcher |

## Keyboard Shortcuts

### Dashboard
- `Enter` in chat input — Send message
- `↑/↓` — Scroll chat history

### Result Page
- `B` — Back to dashboard
- `R` — Refresh results

## Useful URLs

| URL | Description |
|-----|-------------|
| http://localhost:3000 | Dashboard |
| http://localhost:3000/api/docs | API docs (FastAPI) |
| http://localhost:8080/mcp/tools | MCP tools |

## One-Liners

```bash
# Quick test
curl -X POST http://localhost:3000/api/tests/run -d "url=https://example.com" -d "test_type=homepage"

# Check status
curl http://localhost:3000/api/orchestrator/status | jq

# View latest result
curl http://localhost:3000/api/results | jq '.results[0]'

# Chat with Vectra
curl -X POST http://localhost:3000/api/engineer/start \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com"}' \
  -c cookies.txt
curl -X POST http://localhost:3000/api/engineer/$SID/message \
  -H "Content-Type: application/json" \
  -b cookies.txt \
  -d '{"message": "Hello"}'

# Tail logs
tail -f obsidian_vault/Runs/*_worker.log

# Count tests by result
grep -r "result:" obsidian_vault/Runs/ | cut -d: -f3 | sort | uniq -c
```