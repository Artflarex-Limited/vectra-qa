# Installation Guide

## Quick Install (Docker)

```bash
git clone https://github.com/Artflarex-Limited/vectra-qa.git
cd vectra-qa
cp .env.example .env
# Edit .env with your API keys
docker compose up --build
```

Visit `http://localhost:3000`

## Requirements

- Python 3.11+ (for local install)
- Docker & Docker Compose (recommended)
- Chrome/Chromium (for browser automation)

## Step-by-Step

### 1. Clone Repository

```bash
git clone https://github.com/Artflarex-Limited/vectra-qa.git
cd vectra-qa
```

### 2. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` and add at least one LLM API key:
```bash
OPENAI_API_KEY=sk-your-key-here
# or
ANTHROPIC_API_KEY=sk-ant-your-key-here
```

### 3. Start Services

```bash
docker compose up --build
```

### 4. Verify Installation

```bash
# Check MCP Server
curl http://localhost:8080/mcp/tools

# Check Dashboard
curl http://localhost:3000/api/orchestrator/status

# Open browser
open http://localhost:3000
```

## Local Install (Without Docker)

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
playwright install chromium

# Start services (in separate terminals)
python -m mcp_server.server
python -m uvicorn command_center.main:app --host 0.0.0.0 --port 3000
python -m command_center.obsidian_reader
```

## Troubleshooting

See [Troubleshooting](Troubleshooting) for common issues.