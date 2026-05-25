# Environment Variables

Complete reference of all environment variables used by Vectra QA.

## Required Variables

At least one LLM provider API key is required for chatbot features.

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
| `COMMAND_CENTER_HOST` | `0.0.0.0` | Dashboard bind address |

## Chatbot Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `CHATBOT_MODEL` | `anthropic/claude-3-5-sonnet-20241022` | LLM model for chatbot |
| `CHATBOT_MAX_HISTORY` | `50` | Max conversation history |
| `CHATBOT_ENABLE_STREAMING` | `true` | Enable SSE streaming |

### Supported Models

Format: `provider/model-name`

| Provider | Model | Use Case |
|----------|-------|----------|
| `anthropic` | `claude-3-5-sonnet-20241022` | Best reasoning |
| `openai` | `gpt-4o` | Fast and reliable |
| `openai` | `gpt-4o-mini` | Cost-effective |
| `google` | `gemini-1.5-pro` | Long context |
| `minimax` | `minimax-text-01` | Budget option |
| `kimi` | `kimi-k2` | Chinese-optimized |
| `local` | `llama3.1:70b` | Privacy-first |

## Browser Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `HEADLESS` | `true` | Run browsers headlessly |
| `PLAYWRIGHT_BROWSER` | `chromium` | Browser engine |
| `PLAYWRIGHT_TIMEOUT` | `30000` | Page load timeout (ms) |

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
MINIMAX_BASE_URL=https://api.minimax.chat/v1
```

### Kimi/Moonshot
```bash
KIMI_API_KEY=...
KIMI_BASE_URL=https://api.moonshot.cn/v1
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
CHATBOT_ENABLE_STREAMING=true
CHATBOT_MAX_HISTORY=50
```

### Production
```bash
# .env.production
HEADLESS=true
LOG_LEVEL=INFO
COMMAND_CENTER_SECRET_KEY=your-strong-secret
MCP_API_KEY=your-mcp-key
CORS_ORIGINS=https://yourdomain.com
CHATBOT_MODEL=openai/gpt-4o-mini
```

### CI/CD
```bash
# .env.ci
HEADLESS=true
LOG_LEVEL=WARNING
CHATBOT_MODEL=openai/gpt-4o-mini
CHATBOT_MAX_HISTORY=20
```

### Minimal (Local Testing)
```bash
# .env.minimal
OPENAI_API_KEY=sk-...
MCP_SERVER_URL=http://localhost:8080
```

## Docker Compose Environment

Override in `docker-compose.yml`:

```yaml
services:
  command-center:
    environment:
      - CHATBOT_MODEL=openai/gpt-4o
      - CHATBOT_MAX_HISTORY=100
      - HEADLESS=false
```

Or use `.env` file:

```bash
# .env
docker compose up
```

## Validation

Verify configuration:

```python
# config_check.py
import os

required = ['OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'GOOGLE_API_KEY']
set_providers = [p for p in required if os.getenv(p)]

if not set_providers:
    print("❌ No LLM provider configured")
else:
    print(f"✅ Providers: {', '.join(set_providers)}")

# Check core config
if not os.getenv('MCP_SERVER_URL'):
    print("❌ MCP_SERVER_URL not set")
else:
    print("✅ MCP_SERVER_URL configured")
```

## Security Best Practices

1. **Never commit `.env`** — It's in `.gitignore` for a reason
2. **Rotate API keys** — Change keys quarterly
3. **Use secrets manager** — In production, use Docker secrets or cloud KMS
4. **Limit CORS** — Set specific origins, not `*`
5. **Strong secrets** — Use 32+ character random strings

```bash
# Generate strong secret
openssl rand -hex 32

# Use in production
COMMAND_CENTER_SECRET_KEY=$(openssl rand -hex 32)
```