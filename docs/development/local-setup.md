# Local Development Setup

Complete guide for setting up Vectra QA on your local machine for development and testing.

## Prerequisites

### Required

- **Python 3.11+**: [Download](https://www.python.org/downloads/)
- **Git**: [Download](https://git-scm.com/downloads)
- **Docker**: [Download](https://docs.docker.com/get-docker/)
- **Docker Compose**: Usually included with Docker Desktop

### Optional

- **Obsidian**: [Download](https://obsidian.md/) — For visual vault browsing
- **VS Code**: [Download](https://code.visualstudio.com/) — Recommended editor
- **Make**: For using Makefile commands

## Step-by-Step Setup

### 1. Clone Repository

```bash
git clone https://github.com/Artflarex-Limited/vectra-qa.git
cd vectra-qa
```

### 2. Create Virtual Environment

```bash
# Using venv
python3 -m venv venv

# Activate
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate  # Windows
```

### 3. Install Dependencies

```bash
# Core dependencies
pip install -r requirements.txt

# Development dependencies (optional)
pip install -e ".[dev]"

# Documentation dependencies (optional)
pip install -e ".[docs]"

# All extras
pip install -e ".[dev,docs]"
```

### 4. Install Playwright Browsers

```bash
# Install Chromium (primary browser)
playwright install chromium

# Or install all browsers
playwright install
```

### 5. Configure Environment

```bash
# Copy template
cp .env.example .env

# Edit with your API keys
# At minimum, set one LLM provider:
# - OPENAI_API_KEY=sk-your-key
# - ANTHROPIC_API_KEY=sk-ant-your-key
```

### 6. Create Obsidian Vault

```bash
# Create vault directory
mkdir -p obsidian_vault/{Global,Runs,Screenshots,Templates}

# Create initial files
cat > obsidian_vault/Global/Test_Run_Master.md << 'EOF'
---
status: initialized
phase: idle
---

# Test Run Master

System initialization complete.
EOF

cat > obsidian_vault/Templates/Agent_Spawn_Template.md << 'EOF'
---
agent_role: "{{ROLE}}"
agent_id: "{{AGENT_ID}}"
status: spawned
---

# Agent Log

## Objective
{{OBJECTIVE}}

## Progress

## Findings
EOF
```

### 7. Verify Setup

```bash
# Test imports
python test_imports.py

# Expected output:
# ✅ Vault tools import successful
# ✅ Agent spawner import successful
# ✅ LLM router import successful
# ✅ Browser tools import successful
# ✅ All core imports working
```

## Running Services

### Option 1: Docker Compose (Recommended)

```bash
# Start all services
docker compose up --build

# Services available at:
# - Dashboard: http://localhost:3000
# - MCP Server: http://localhost:8080
# - API Docs: http://localhost:3000/docs
```

### Option 2: Manual Start

For development with hot reload:

```bash
# Terminal 1: MCP Server
python -m mcp_server.server

# Terminal 2: Command Center
python -m uvicorn command_center.main:app --host 0.0.0.0 --port 3000 --reload

# Terminal 3: Vault Watcher
python -m command_center.obsidian_reader
```

### Option 3: Individual Components

```bash
# Test agent spawning only
python -c "from mcp_server.tools import spawner; print('Spawner ready')"

# Test browser automation
python -c "
import asyncio
from mcp_server.browser_tools import BrowserAutomation
async def test():
    b = BrowserAutomation()
    await b.start()
    r = await b.visit('https://example.com')
    print(f'Status: {r[\"status\"]}')
    await b.close()
asyncio.run(test())
"
```

## Development Workflow

### Making Changes

```bash
# 1. Create feature branch
git checkout -b feature/my-feature

# 2. Make code changes
# Edit files...

# 3. Run tests
pytest

# 4. Check code quality
black .
ruff check .
mypy mcp_server command_center agents

# 5. Test manually
python -m uvicorn command_center.main:app --reload

# 6. Commit changes
git add .
git commit -m "feat: add new feature"
```

### Testing Changes

```bash
# Run specific test
pytest tests/unit/test_live_engineer.py -v

# Run with coverage
pytest --cov=vectra_qa --cov-report=html

# Open coverage report
open htmlcov/index.html

# Run linting
ruff check . --fix
black . --check
```

### Debugging

```bash
# Enable debug mode
export LOG_LEVEL=DEBUG
export HEADLESS=false

# Run with verbose output
python -m uvicorn command_center.main:app --log-level debug

# Watch agent logs
tail -f obsidian_vault/Runs/*_worker.log

# Inspect vault state
ls -lt obsidian_vault/Runs/
cat obsidian_vault/Runs/Latest_Test.md
```

## IDE Setup

### VS Code

Create `.vscode/settings.json`:

```json
{
    "python.defaultInterpreterPath": "./venv/bin/python",
    "python.formatting.provider": "black",
    "python.linting.enabled": true,
    "python.linting.ruffEnabled": true,
    "python.testing.pytestEnabled": true,
    "python.testing.pytestArgs": ["tests"],
    "editor.formatOnSave": true,
    "editor.rulers": [100]
}
```

Create `.vscode/launch.json`:

```json
{
    "version": "0.2.0",
    "configurations": [
        {
            "name": "Command Center",
            "type": "python",
            "request": "launch",
            "module": "uvicorn",
            "args": ["command_center.main:app", "--reload"],
            "console": "integratedTerminal"
        },
        {
            "name": "MCP Server",
            "type": "python",
            "request": "launch",
            "module": "mcp_server.server",
            "console": "integratedTerminal"
        }
    ]
}
```

### PyCharm

1. Open project in PyCharm
2. Set Python interpreter to `./venv/bin/python`
3. Configure run configurations for `command_center.main:app`
4. Enable Black formatter in settings

## Troubleshooting

### Import Errors

```bash
# Problem: ModuleNotFoundError
# Solution: Ensure virtual environment is activated
source venv/bin/activate

# Problem: Relative import errors
# Solution: Run with python -m
python -m command_center.main
```

### Playwright Issues

```bash
# Problem: Browser not found
# Solution: Reinstall browsers
playwright install --force chromium

# Problem: Missing system dependencies
# Solution: Install dependencies
playwright install-deps chromium
```

### Port Conflicts

```bash
# Problem: Port 3000 in use
# Solution: Change port in .env
COMMAND_CENTER_PORT=3001

# Problem: Port 8080 in use
# Solution: Change port in .env
MCP_SERVER_PORT=8081
```

### Docker Issues

```bash
# Problem: Containers won't start
# Solution: Check logs
docker compose logs

# Problem: Volume permissions
# Solution: Fix permissions
sudo chown -R $USER:$USER obsidian_vault/

# Problem: Build cache issues
# Solution: Clean build
docker compose down -v
docker compose build --no-cache
```

### LLM Errors

```bash
# Problem: API key errors
# Solution: Check .env file
cat .env | grep API_KEY

# Problem: Rate limiting
# Solution: Switch provider or add rate limiting
ENGINEER_MODEL=openai/gpt-4o-mini  # Cheaper option
```

The model for the Live QA Engineer is currently hardcoded in
`command_center/engineer/conversation.py`. To use a cheaper model
across the board, update the `model` constant there or set the
`ENGINEER_MODEL` environment variable (planned, not yet wired).

## Advanced Configuration

### Custom Python Path

```bash
# If using conda
conda create -n vectra python=3.11
conda activate vectra
pip install -e ".[dev]"
```

### Remote Development

```bash
# Using VS Code Remote-SSH
# 1. Connect to remote server
# 2. Clone repository
# 3. Install dependencies
# 4. Forward ports 3000 and 8080
```

### Database Alternative

While Obsidian Vault is the default, you can use other storage:

```python
# Custom vault backend
class CustomVault:
    def read_node(self, path):
        # Read from database
        pass
    
    def write_node(self, path, content, frontmatter):
        # Write to database
        pass
```

## Performance Tips

### Faster Testing

```bash
# Use lighter LLM model
ENGINEER_MODEL=openai/gpt-4o-mini

# Reduce history
ENGINEER_MAX_HISTORY=20

# Disable streaming
ENGINEER_ENABLE_STREAMING=false
```

These environment variables are advisory; the Live QA Engineer reads
its model from `command_center/engineer/conversation.py` directly. Use
them as a reminder of the recommended setting for faster local runs.

### Resource Monitoring

```bash
# Monitor Docker resources
docker stats

# Monitor Python processes
ps aux | grep python

# Check disk usage
du -sh obsidian_vault/
```

## Next Steps

After setup:

1. **Run first test**: Use the dashboard or the Live QA Engineer chat panel
2. **Explore codebase**: Read `ARCHITECTURE.md`
3. **Add feature**: See `CONTRIBUTING.md`
4. **Create agent**: See `custom-agents.md`
5. **Write docs**: Edit files in `docs/`

## Getting Help

- **GitHub Issues**: Bug reports and feature requests
- **GitHub Discussions**: Questions and ideas
- **Documentation**: <https://vectra-qa.artflarex.com>
- **Wiki**: <https://github.com/Artflarex-Limited/vectra-qa/wiki>

## Verification Checklist

- [ ] Python 3.11+ installed
- [ ] Virtual environment created and activated
- [ ] Dependencies installed successfully
- [ ] Playwright browsers installed
- [ ] `.env` file configured with API keys
- [ ] Obsidian vault directory created
- [ ] Test imports pass
- [ ] Dashboard loads at `http://localhost:3000`
- [ ] Can spawn test agent
- [ ] Can view test results
