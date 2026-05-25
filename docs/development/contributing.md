# Contributing to Vectra QA

Thank you for your interest in contributing! This guide covers how to set up your development environment, submit changes, and follow our coding standards.

## Development Setup

### Prerequisites

- Python 3.11+
- Docker and Docker Compose
- Git
- Make (optional)

### Local Development

```bash
# Clone repository
git clone https://github.com/Artflarex-Limited/vectra-qa.git
cd vectra-qa

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -e ".[dev,docs]"

# Install Playwright browsers
playwright install chromium

# Set environment
cp .env.example .env
# Edit .env with your API keys
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=vectra_qa --cov-report=html

# Run specific test file
pytest tests/test_chatbot.py

# Run in watch mode
pytest -f
```

### Code Quality

```bash
# Format code
black .

# Lint
ruff check .

# Type check
mypy mcp_server command_center agents

# Run all checks
make check
```

## Project Structure

```
vectra-qa/
├── mcp_server/          # MCP Tool Server
│   ├── server.py        # Protocol server
│   ├── tools.py         # Tool definitions
│   ├── llm_router.py    # LLM routing
│   └── browser_tools.py # Playwright wrapper
├── command_center/      # Dashboard backend
│   ├── main.py          # FastAPI app
│   ├── chatbot.py       # Chat engine
│   ├── obsidian_reader.py # Vault watcher
│   └── static/          # HTMX frontend
├── agents/              # Agent workers
│   ├── ui_explorer/     # Browser automation
│   └── data_validator/  # API validation
├── docs/                # Documentation
├── tests/               # Test suite
└── docker/              # Docker configs
```

## Adding Features

### 1. New MCP Tool

Add a tool to `mcp_server/tools.py`:

```python
@tool_registry.register
def my_tool(param1: str, param2: int) -> dict:
    """
    Description of what the tool does.
    
    Args:
        param1: Description of param1
        param2: Description of param2
    
    Returns:
        Dictionary with results
    """
    result = do_something(param1, param2)
    return {"status": "success", "result": result}
```

### 2. New API Endpoint

Add to `command_center/main.py`:

```python
@app.post("/api/my-feature")
async def my_feature(data: str = Form(...)):
    """
    Description of the endpoint.
    
    Args:
        data: Input data
    
    Returns:
        JSON response
    """
    try:
        result = process_data(data)
        return {"status": "success", "data": result}
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )
```

### 3. New Agent Type

Create in `agents/my_agent/`:

```python
# worker.py
import asyncio
import sys

async def run_agent(agent_id: str, memory_node: str):
    """Main agent execution loop."""
    # Read objective
    # Execute tests
    # Update vault
    pass

if __name__ == "__main__":
    agent_id = sys.argv[1]
    memory_node = sys.argv[2]
    asyncio.run(run_agent(agent_id, memory_node))
```

```markdown
# soul.md
## Personality
Describe the agent's behavior and decision-making.

## Capabilities
- What can this agent do?
- What tools does it use?

## Constraints
- Resource limits
- Timeout settings
```

## Coding Standards

### Python Style

Follow PEP 8 with these specifics:

```python
# Line length: 100 characters
# Use type hints
def process_data(data: str) -> dict[str, Any]:
    """Docstring with description."""
    result = {}
    # Use meaningful variable names
    for item in data_items:
        result[item.id] = item.value
    return result
```

### Documentation

- All public functions must have docstrings
- Use Google-style docstrings
- Include type hints
- Document exceptions

```python
def classify_intent(message: str) -> str:
    """
    Classify user message intent.
    
    Args:
        message: User's natural language message
        
    Returns:
        Intent classification: "chat", "plan_tests", or "interpret_results"
        
    Raises:
        ValueError: If message is empty
    """
    if not message:
        raise ValueError("Message cannot be empty")
    # ...
```

### Testing

```python
# tests/test_chatbot.py
import pytest
from command_center.chatbot import ChatEngine

class TestChatEngine:
    def test_extract_url(self):
        engine = ChatEngine()
        url = engine._extract_url("Test https://example.com")
        assert url == "https://example.com"
    
    def test_classify_intent(self):
        engine = ChatEngine()
        intent = engine._classify_intent("Test the homepage")
        assert intent == "plan_tests"
```

## Submitting Changes

### 1. Create Branch

```bash
git checkout -b feature/my-feature
# or
git checkout -b fix/bug-description
```

### 2. Make Changes

- Write code
- Add tests
- Update documentation
- Run checks

### 3. Commit

Follow conventional commits:

```bash
# Format: type(scope): description
git commit -m "feat(chatbot): add sentiment analysis

- Analyze user sentiment in messages
- Adjust response tone accordingly
- Add tests for sentiment detection"
```

Types:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation
- `style`: Formatting
- `refactor`: Code restructuring
- `test`: Tests
- `chore`: Maintenance

### 4. Push and PR

```bash
git push origin feature/my-feature
```

Create Pull Request with:
- Clear title
- Description of changes
- Testing instructions
- Screenshots (if UI changes)

## Review Process

### PR Checklist

- [ ] Code follows style guide
- [ ] Tests added/updated
- [ ] Documentation updated
- [ ] All tests pass
- [ ] No breaking changes (or documented)
- [ ] Commit messages follow convention

### Review Criteria

- **Code Quality**: Clean, readable, maintainable
- **Tests**: Adequate coverage, passing
- **Documentation**: Updated and accurate
- **Performance**: No unnecessary overhead
- **Security**: No vulnerabilities introduced

## Release Process

### Versioning

We follow semantic versioning:
- `0.1.0` — Initial release
- `0.2.0` — New features
- `0.2.1` — Bug fixes
- `1.0.0` — Stable release

### Creating a Release

1. Update `VERSION` file
2. Update `CHANGELOG.md`
3. Create git tag
4. Push tag
5. GitHub Actions builds and deploys

```bash
# Bump version
echo "0.2.0" > VERSION

# Update changelog
# Edit CHANGELOG.md

# Commit
git add VERSION CHANGELOG.md
git commit -m "chore(release): bump version to 0.2.0"

# Tag
git tag -a v0.2.0 -m "Release v0.2.0"
git push origin v0.2.0
```

## Community

### Getting Help

- GitHub Issues: Bug reports and feature requests
- GitHub Discussions: Questions and ideas
- Wiki: Community guides

### Code of Conduct

- Be respectful and inclusive
- Focus on constructive feedback
- Help others learn
- Credit original authors

## Development Tips

### Debug Mode

```bash
# Enable debug logging
LOG_LEVEL=DEBUG HEADLESS=false docker compose up
```

### Hot Reload

```bash
# Watch for file changes and restart
watchmedo auto-restart --directory=. --pattern="*.py" -- python -m command_center.main
```

### Testing Agents

```bash
# Run agent directly for debugging
python agents/ui_explorer/worker.py test-agent-id Runs/Test_Debug.md
```

### Database Inspection

```bash
# Read vault directly
cat obsidian_vault/Runs/Test_20260115.md

# Search across all tests
grep -r "result: fail" obsidian_vault/Runs/
```

## Common Tasks

### Add New Test Type

1. Update `TEST_TYPES` in `command_center/chatbot.py`
2. Add test function in `agents/ui_explorer/worker.py`
3. Update test type dropdown in `command_center/static/index.html`
4. Add documentation in `docs/user-guide/writing-tests.md`

### Add New LLM Provider

1. Update `LLMRouter._init_clients()` in `mcp_server/llm_router.py`
2. Add environment variable to `.env.example`
3. Update `docs/getting-started/configuration.md`
4. Test with provider's API

### Update Documentation

1. Edit files in `docs/` directory
2. Test locally: `mkdocs serve`
3. Build: `mkdocs build`
4. Deploy: Trigger GitHub Actions workflow

## License

By contributing, you agree that your contributions will be licensed under the MIT License.