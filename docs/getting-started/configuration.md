# Configuration

Vectra QA is configured through environment variables. You can set them in:
- `.env` file (recommended)
- Docker Compose environment section
- Shell exports

## Required Configuration

### LLM Provider (Choose at least one)

| Variable | Description | Example |
|----------|-------------|---------|
| `OPENAI_API_KEY` | OpenAI API key | `sk-...` |
| `ANTHROPIC_API_KEY` | Anthropic/Claude API key | `sk-ant-...` |
| `GOOGLE_API_KEY` | Google Gemini API key | `...` |
| `MINIMAX_API_KEY` | MiniMax API key | `...` |
| `KIMI_API_KEY` | Kimi/Moonshot API key | `...` |

## Core Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `MCP_SERVER_URL` | `http://mcp-server:8080` | URL of the MCP tool server |
| `OBSIDIAN_VAULT_PATH` | `/app/obsidian_vault` | Path to Obsidian vault directory |
| `COMMAND_CENTER_PORT` | `3000` | Dashboard HTTP port |
| `MCP_SERVER_PORT` | `8080` | MCP server HTTP port |

## Chatbot Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `CHATBOT_MODEL` | `anthropic/claude-3-5-sonnet-20241022` | LLM model for chatbot |
| `CHATBOT_MAX_HISTORY` | `50` | Maximum conversation history messages |
| `CHATBOT_ENABLE_STREAMING` | `true` | Enable SSE streaming responses |

## Browser Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `HEADLESS` | `true` | Run Playwright in headless mode |
| `PLAYWRIGHT_BROWSER` | `chromium` | Browser engine (chromium, firefox, webkit) |

## Security

| Variable | Default | Description |
|----------|---------|-------------|
| `COMMAND_CENTER_SECRET_KEY` | `dev-secret-key` | JWT/secret key (change in production) |
| `MCP_API_KEY` | (none) | API key for MCP server authentication |
| `CORS_ORIGINS` | `*` | Allowed CORS origins |

## Example .env File

```bash
# LLM Provider (OpenAI example)
OPENAI_API_KEY=sk-your-key-here

# Core Services
MCP_SERVER_URL=http://mcp-server:8080
COMMAND_CENTER_PORT=3000
MCP_SERVER_PORT=8080

# Chatbot
CHATBOT_MODEL=openai/gpt-4o
CHATBOT_MAX_HISTORY=50

# Browser
HEADLESS=true

# Security
COMMAND_CENTER_SECRET_KEY=your-secure-secret-key-change-this
```

## Multiple LLM Providers

You can configure multiple providers simultaneously. The system will use them in this priority:

1. **Anthropic** (Claude) — Best for complex reasoning
2. **OpenAI** (GPT-4o) — Fast and reliable
3. **Google** (Gemini) — Good for long context
4. **MiniMax** — Cost-effective
5. **Kimi** — Chinese-optimized
6. **Local** (Ollama) — Privacy-first

Example with multiple providers:
```bash
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=...
LOCAL_LLM_BASE_URL=http://localhost:11434/v1
```

## Docker Compose Configuration

Override defaults in `docker-compose.yml`:

```yaml
services:
  command-center:
    environment:
      - CHATBOT_MODEL=openai/gpt-4o
      - CHATBOT_MAX_HISTORY=100
      - HEADLESS=false  # For debugging
```

## Environment-Specific Configurations

### Development
```bash
HEADLESS=false  # See browser windows
LOG_LEVEL=DEBUG
CHATBOT_ENABLE_STREAMING=true
```

### Production
```bash
HEADLESS=true
LOG_LEVEL=INFO
COMMAND_CENTER_SECRET_KEY=your-strong-secret
MCP_API_KEY=your-mcp-api-key
CORS_ORIGINS=https://yourdomain.com
```

### CI/CD
```bash
HEADLESS=true
LOG_LEVEL=WARNING
CHATBOT_MODEL=openai/gpt-4o-mini  # Faster, cheaper
```