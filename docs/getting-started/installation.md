# Installation

## Prerequisites

- Python 3.11 or higher
- Docker and Docker Compose (recommended)
- Chrome/Chromium browser (for Playwright automation)
- Git

## Method 1: Docker Compose (Recommended)

The fastest way to get started with Vectra QA:

```bash
# Clone the repository
git clone https://github.com/Artflarex-Limited/vectra-qa.git
cd vectra-qa

# Copy environment template
cp .env.example .env

# Edit .env and add your API keys
# At minimum, you need:
# - OPENAI_API_KEY or ANTHROPIC_API_KEY (for LLM features)

# Start all services
docker compose up --build
```

This will start three services:
- **MCP Server** (port 8080) — Tool server for agent spawning
- **Command Center** (port 3000) — Dashboard and API
- **Vault Watcher** — File system watcher for real-time updates

## Method 2: Local Installation

For development or customization:

```bash
# Clone the repository
git clone https://github.com/Artflarex-Limited/vectra-qa.git
cd vectra-qa

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install chromium

# Set environment variables
cp .env.example .env
# Edit .env with your API keys

# Start services (in separate terminals)
# Terminal 1: MCP Server
python -m mcp_server.server

# Terminal 2: Command Center
python -m uvicorn command_center.main:app --host 0.0.0.0 --port 3000

# Terminal 3: Vault Watcher
python -m command_center.obsidian_reader
```

## Verifying Installation

Once running, verify the installation:

```bash
# Check MCP Server
curl http://localhost:8080/mcp/tools

# Check Command Center
curl http://localhost:3000/api/orchestrator/status

# Open dashboard
open http://localhost:3000
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | Yes* | OpenAI API key for LLM features |
| `ANTHROPIC_API_KEY` | Alternative | Anthropic API key (Claude) |
| `MCP_SERVER_URL` | Yes | URL for MCP server (default: http://mcp-server:8080) |
| `OBSIDIAN_VAULT_PATH` | No | Path to Obsidian vault (default: /app/obsidian_vault) |
| `CHATBOT_MODEL` | No | LLM model for chatbot (default: anthropic/claude-3-5-sonnet) |

*At least one LLM provider API key is required for chatbot and intent classification features.

## Troubleshooting

**Issue**: Docker containers fail to start
- **Solution**: Ensure Docker daemon is running and ports 3000/8080 are available

**Issue**: Playwright browser not found
- **Solution**: Run `playwright install chromium` inside the container or locally

**Issue**: LLM features not working
- **Solution**: Check that API keys are set correctly in `.env`

**Issue**: Dashboard shows no data
- **Solution**: Ensure Vault Watcher is running and `obsidian_vault/` directory exists