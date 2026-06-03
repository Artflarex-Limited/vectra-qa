# Environment Variables

Complete reference of all environment variables used by Vectra QA.

## Required Variables

At least one LLM provider API key is required for the Live QA Engineer
and the orchestrator features.

### LLM Providers

| Variable | Description | Example |
|----------|-------------|---------|
| `OPENAI_API_KEY` | OpenAI API key | `sk-proj-...` |
| `ANTHROPIC_API_KEY` | Anthropic/Claude API key | `sk-ant-...` |
| `GOOGLE_API_KEY` | Google Gemini API key | `AIza...` |
| `MINIMAX_API_KEY` | MiniMax API key | `...` |
| `KIMI_API_KEY` | Kimi/Moonshot API key | `...` |

**Note**: You only need to set one. The system will use the first available.

## Core Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `MCP_SERVER_URL` | `http://mcp-server:8080` | URL of MCP tool server |
| `OBSIDIAN_VAULT_PATH` | `/app/obsidian_vault` | Path to Obsidian vault |
| `COMMAND_CENTER_PORT` | `3000` | Dashboard HTTP port |
| `MCP_SERVER_PORT` | `8080` | MCP server HTTP port |
| `MCP_TRANSPORT` | `sse` | MCP transport: `sse` or `stdio` |
| `COMMAND_CENTER_HOST` | `0.0.0.0` | Dashboard bind address |

## Database

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql://vectra:vectra_dev_password_change_in_production@localhost:5432/vectra_qa` | PostgreSQL connection string |
| `VECTRA_BACKEND` | `dual` | Storage mode: `markdown`, `postgresql`, or `dual` |

**Note**: If `DATABASE_URL` is not set and `VECTRA_BACKEND` is `postgresql` or `dual`, the framework will use the default connection string.

## Model Selection

| Variable | Default | Description |
|----------|---------|-------------|
| `ORCHESTRATOR_MODEL` | `minimax/MiniMax-M2.7` | LLM for test planning |
| `UI_EXPLORER_MODEL` | `minimax/MiniMax-M2.7` | LLM for UI exploration |
| `ENGINEER_MODEL` | `minimax/MiniMax-M2.7` | LLM for the Live QA Engineer |
| `DATA_VALIDATOR_MODEL` | `minimax/MiniMax-M2.7` | LLM for data validation |

### Supported Models

Format: `provider/model-name`

| Provider | Model | Use Case |
|----------|-------|----------|
| `anthropic` | `claude-3-5-sonnet-20241022` | Best reasoning |
| `openai` | `gpt-4o` | Fast and reliable |
| `openai` | `gpt-4o-mini` | Cost-effective |
| `google` | `gemini-1.5-pro` | Long context |
| `minimax` | `MiniMax-M2.7` | Budget option |
| `kimi` | `kimi-k2` | Chinese-optimized |
| `local` | `llama3.1:70b` | Privacy-first |

## Embeddings

| Variable | Default | Description |
|----------|---------|-------------|
| `EMBEDDING_PROVIDER` | `openai` | Provider: `openai`, `local`, `ollama` |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | OpenAI embedding model (when provider is `openai`) |

## Worker Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `VECTRA_LLM_WORKERS` | `true` | Use LLM-driven workers (true) or legacy keyword matching (false) |
| `UI_EXPLORER_MAX_STEPS` | `50` | Max steps per UI explorer agent |
| `UI_EXPLORER_MAX_DURATION` | `600` | Max duration in seconds per agent |

## LLM Cache (Phase 5)

| Variable | Default | Description |
|----------|---------|-------------|
| `VECTRA_LLM_CACHE` | `true` | Enable LLM response caching |
| `VECTRA_LLM_CACHE_TTL` | `3600` | Cache TTL in seconds |
| `VECTRA_LLM_CACHE_PATH` | `/app/obsidian_vault/.llm_cache.json` | Cache persistence path |

**Cache Benefits:**
- Reduces API costs by 60-80% for repeated queries
- Faster response times for cached requests
- Persistent across restarts

## Task Queue (Phase 5)

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_URL` | (none) | Redis connection URL for distributed workers |
| `REDIS_HOST` | `localhost` | Redis host (fallback) |
| `REDIS_PORT` | `6379` | Redis port (fallback) |
| `REDIS_DB` | `0` | Redis database number |

**Note**: If `REDIS_URL` is not set, uses in-memory queue (single-node only).

## Obsidian Vault

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENT_TEMPLATE_DIR` | `{OBSIDIAN_VAULT_PATH}/Templates` | Template directory for agent memory nodes |
| `GLOBAL_NODES_DIR` | `{OBSIDIAN_VAULT_PATH}/Global` | Global memory nodes directory |

## Live QA Engineer Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `ENGINEER_MAX_HISTORY` | `50` | Max conversation history held in the session store |
| `ENGINEER_ENABLE_STREAMING` | `true` | Enable SSE streaming on `/api/engineer/{sid}/stream` |

## Browser Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `HEADLESS` | `true` | Run browsers headlessly |
| `PLAYWRIGHT_BROWSER` | `chromium` | Default browser engine |
| `PLAYWRIGHT_SLOW_MO` | `0` | Slow down operations by N milliseconds |
| `PLAYWRIGHT_VIEWPORT_WIDTH` | `1920` | Browser viewport width |
| `PLAYWRIGHT_VIEWPORT_HEIGHT` | `1080` | Browser viewport height |

## Feature Test Configuration

### Performance Thresholds

| Variable | Default | Description |
|----------|---------|-------------|
| `PERFORMANCE_LCP_MS` | `2500` | Largest Contentful Paint threshold |
| `PERFORMANCE_FID_MS` | `100` | First Input Delay threshold |
| `PERFORMANCE_CLS` | `0.1` | Cumulative Layout Shift threshold |
| `PERFORMANCE_TTFB_MS` | `600` | Time to First Byte threshold |
| `PERFORMANCE_FCP_MS` | `1800` | First Contentful Paint threshold |
| `PERFORMANCE_TBT_MS` | `200` | Total Blocking Time threshold |

### Accessibility

| Variable | Default | Description |
|----------|---------|-------------|
| `ACCESSIBILITY_STANDARD` | `wcag2aa` | Default WCAG standard: `wcag2a`, `wcag2aa`, `wcag21aa` |

### Visual Regression

| Variable | Default | Description |
|----------|---------|-------------|
| `VISUAL_REGRESSION_THRESHOLD` | `0.1` | Pixel difference threshold (10%) |
| `VISUAL_BASELINE_DIR` | `Baselines` | Baseline screenshot directory |

## Security

| Variable | Default | Description |
|----------|---------|-------------|
| `COMMAND_CENTER_SECRET_KEY` | `dev-secret-key` | JWT/secret key |
| `MCP_API_KEY` | (none) | MCP server API key |
| `CORS_ORIGINS` | `*` | Allowed CORS origins |

## Logging

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_LEVEL` | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `PYTHONUNBUFFERED` | `1` | Unbuffered output |
| `STRUCTLOG_FORMAT` | `json` | Log format: `json` or `console` |

## Docker-Specific

| Variable | Default | Description |
|----------|---------|-------------|
| `PYTHONPATH` | `/app` | Python module path |
| `DOCKER_BUILDKIT` | `1` | BuildKit enabled |

## Provider-Specific

### OpenAI
```bash
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.openai.com/v1  # Optional: for proxies
```

### Anthropic
```bash
ANTHROPIC_API_KEY=sk-ant-...
```

### Google
```bash
GOOGLE_API_KEY=...
```

### MiniMax
```bash
MINIMAX_API_KEY=...
MINIMAX_BASE_URL=https://api.minimax.io/v1
MINIMAX_MODEL=minimax/MiniMax-M2.7
```

### Kimi/Moonshot
```bash
KIMI_API_KEY=...
KIMI_BASE_URL=https://api.moonshot.cn/v1
KIMI_MODEL=kimi-k2.6
```

### Local (Ollama)
```bash
LOCAL_LLM_BASE_URL=http://localhost:11434/v1
LOCAL_LLM_MODEL=llama3.1:70b
```

## Example Configurations

### Development
```bash
# .env.development
HEADLESS=false
LOG_LEVEL=DEBUG
ENGINEER_ENABLE_STREAMING=true
ENGINEER_MAX_HISTORY=50
VECTRA_LLM_CACHE=true
VECTRA_LLM_CACHE_TTL=1800
```

### Production
```bash
# .env.production
HEADLESS=true
LOG_LEVEL=INFO
COMMAND_CENTER_SECRET_KEY=your-strong-secret
MCP_API_KEY=your-mcp-api-key
CORS_ORIGINS=https://yourdomain.com
ENGINEER_MODEL=openai/gpt-4o-mini
VECTRA_LLM_CACHE=true
VECTRA_LLM_CACHE_TTL=7200
REDIS_URL=redis://redis:6379/0
```

### CI/CD
```bash
# .env.ci
HEADLESS=true
LOG_LEVEL=WARNING
ENGINEER_MODEL=openai/gpt-4o-mini
ENGINEER_MAX_HISTORY=20
VECTRA_LLM_WORKERS=true
```

### Minimal (Local Testing)
```bash
# .env.minimal
OPENAI_API_KEY=sk-...
MCP_SERVER_URL=http://localhost:8080
OBSIDIAN_VAULT_PATH=/home/$(whoami)/Documents/obsidian_vault
```

### Full Feature Testing
```bash
# .env.full-test
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
OBSIDIAN_VAULT_PATH=/app/obsidian_vault

# LLM Configuration
ORCHESTRATOR_MODEL=openai/gpt-4o
UI_EXPLORER_MODEL=anthropic/claude-3-5-sonnet-20241022
VECTRA_LLM_WORKERS=true

# Performance Thresholds
PERFORMANCE_LCP_MS=2000
PERFORMANCE_TTFB_MS=400
PERFORMANCE_FCP_MS=1500

# Accessibility
ACCESSIBILITY_STANDARD=wcag21aa

# Visual Regression
VISUAL_REGRESSION_THRESHOLD=0.05

# Caching
VECTRA_LLM_CACHE=true
VECTRA_LLM_CACHE_TTL=3600

# Distributed Workers
REDIS_URL=redis://localhost:6379/0
```

## Deprecated / Removed

The following variables are no longer used by the current codebase. They are listed here for migration purposes only.

| Variable | Status | Replacement |
|----------|--------|-------------|
| `PLAYWRIGHT_TIMEOUT` | **Removed** | Not implemented; use `PLAYWRIGHT_SLOW_MO` for debugging |
| `BROWSER_POOL_MAX` | **Removed** | Not implemented |
| `CHROMA_PERSIST_DIR` | **Removed** | Use PostgreSQL + pgvector via `DATABASE_URL` |
| `CHROMA_COLLECTION_NAME` | **Removed** | Use PostgreSQL + pgvector via `DATABASE_URL` |
| `PINECONE_API_KEY` | **Removed** | Use PostgreSQL + pgvector via `DATABASE_URL` |
| `PINECONE_ENVIRONMENT` | **Removed** | Use PostgreSQL + pgvector via `DATABASE_URL` |
| `PINECONE_INDEX_NAME` | **Removed** | Use PostgreSQL + pgvector via `DATABASE_URL` |
| `VECTOR_DB_PROVIDER` | **Removed** | Use `VECTRA_BACKEND` |

## Docker Compose Environment

Override in `docker-compose.yml`:

```yaml
services:
  mcp-server:
    environment:
      - VECTRA_LLM_CACHE=true
      - VECTRA_LLM_CACHE_TTL=7200
      - REDIS_URL=redis://redis:6379/0
      - PERFORMANCE_LCP_MS=2000

  command-center:
    environment:
      - ENGINEER_MODEL=openai/gpt-4o
      - ENGINEER_MAX_HISTORY=100
      - HEADLESS=false
```

Or use `.env` file:

```bash
# .env
docker compose up
```

## Validation

Verify configuration:

```bash
# Using built-in validator
python scripts/validate_env.py
```

Expected output:
```
✅ Environment validation passed
✅ Required packages installed
✅ Playwright browsers installed
✅ LLM connectivity verified
✅ Vault path accessible
✅ Redis available (optional)
```

## Security Best Practices

1. **Never commit `.env`** — It's in `.gitignore` for a reason
2. **Rotate API keys** — Change keys quarterly
3. **Use secrets manager** — In production, use Docker secrets or cloud KMS
4. **Limit CORS** — Set specific origins, not `*`
5. **Strong secrets** — Use 32+ character random strings
6. **Redis security** — Use Redis AUTH in production

```bash
# Generate strong secret
openssl rand -hex 32

# Use in production
COMMAND_CENTER_SECRET_KEY=$(openssl rand -hex 32)
```
