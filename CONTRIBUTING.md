# Contributing to Vectra QA

Thank you for your interest in making Vectra QA better! This guide covers how to add new MCP skills, tune agent personas, and set up your local development environment.

## Table of Contents

- [Adding New MCP Skills](#adding-new-mcp-skills)
- [Tuning Agent Personas](#tuning-agent-personas)
- [Local Development](#local-development)
- [Pull Request Process](#pull-request-process)

## Adding New MCP Skills

MCP (Model Context Protocol) skills are the tools that agents use to interact with the world. Adding a new skill makes it available to all agents via the MCP Tool Server.

### Step 1: Implement the Tool Handler

Create your tool logic in `mcp_server/tools.py`:

```python
# Example: Add a screenshot comparison tool
from PIL import Image
import io

def compare_screenshots(baseline_path: str, current_path: str) -> dict:
    """Compare two screenshots and return pixel diff metrics."""
    baseline = Image.open(baseline_path)
    current = Image.open(current_path)
    
    # Calculate diff
    diff = 0
    pixels = 0
    for i in range(baseline.width):
        for j in range(baseline.height):
            if baseline.getpixel((i, j)) != current.getpixel((i, j)):
                diff += 1
            pixels += 1
    
    return {
        "pixel_diff_count": diff,
        "pixel_diff_percent": (diff / pixels) * 100,
        "match": diff == 0
    }
```

### Step 2: Register the Tool

Add your tool to the `TOOLS` dictionary with a JSON Schema definition:

```python
TOOLS = {
    # ... existing tools ...
    
    "compare_screenshots": {
        "description": "Compare two screenshots pixel-by-pixel for visual regression testing",
        "parameters": {
            "baseline_path": {
                "type": "string",
                "description": "Path to the baseline screenshot"
            },
            "current_path": {
                "type": "string", 
                "description": "Path to the current screenshot"
            }
        },
        "handler": lambda params: compare_screenshots(
            params["baseline_path"],
            params["current_path"]
        )
    }
}
```

### Step 3: Document the Tool

Update the agent configuration files to inform agents about the new tool. Add to `agents/ui_explorer/agents.md`:

```markdown
### New: Visual Regression Testing
- **`compare_screenshots(baseline_path, current_path)`**
  - Compare current UI state against baseline screenshots
  - Returns pixel diff count and percentage
  - Use after DOM changes to detect unintended visual shifts
```

### Step 4: Test

Run the MCP server and verify your tool appears in the tools list:

```bash
python mcp_server/server.py --transport sse

# In another terminal
curl http://localhost:8080/mcp/tools
```

Your new tool should appear in the JSON response.

### Best Practices for Tool Design

- **Idempotent**: Calling a tool twice with the same inputs should yield the same result
- **Pure**: Tools should not have side effects (unless explicitly documented)
- **Typed**: Use strict JSON Schema types for all parameters
- **Documented**: Every tool must have a clear description and example usage
- **Atomic**: A tool should do one thing well

## Tuning Agent Personas

Agent behavior is defined by two files: `soul.md` and `agents.md`. Understanding the distinction is key to effective tuning.

### Philosophy: Soul vs. Agents

**`soul.md`** — The Behavioral DNA

The soul defines WHO the agent is. It's the agent's personality, instincts, and core philosophy. This is where you inject passion, obsession, and behavioral quirks.

```markdown
# UI Explorer - Agent Soul

## Persona
You are a meticulous, obsessive frontend specialist who lives and breathes user interfaces. 
You are paranoid about broken flows, hidden elements, and accessibility failures.

## Core Identity
- **Name**: UI Explorer
- **Role**: Frontend E2E Testing Specialist
- **Obsession**: Every pixel, every transition, every hidden state

## Behavioral Directives
1. User Flow Fanaticism: NEVER assume a UI element is visible
2. Hidden Element Detection: Actively hunt for display:none, visibility:hidden
3. Accessibility Vigilance: Verify alt text, contrast ratios, keyboard nav
```

**`agents.md`** — The Operational Constraints

The agents file defines WHAT the agent can do. It's the rulebook, tool list, and execution protocol.

```markdown
# UI Explorer Agent Configuration

## Role
Frontend DOM Manipulation and UI State Verification Specialist

## MCP Tools - UI Testing Suite
1. `read_obsidian_node(node_path)` — Read memory context
2. `query_selector(selector)` — Execute CSS selector against DOM
3. `simulate_interaction(selector, action, params)` — Simulate user actions

## Execution Flow
1. Initialize: Read assigned memory node
2. Execute: Run all required UI tests
3. Log: Write findings with wiki-links
4. Complete: Update status and terminate
```

### Tuning Examples

#### Making an Agent More Aggressive at Finding Bugs

Edit `agents/ui_explorer/soul.md`:

```markdown
## Behavioral Directives (Aggressive Mode)

### 1. Destructive Testing Mindset
- Your job is to BREAK things, not confirm they work
- If a form accepts text, try SQL injection, XSS payloads, emoji floods
- If a button exists, click it 100 times rapidly
- If a page loads, try resizing to 1x1 pixel

### 2. Zero Trust Philosophy
- Assume every developer is lying about their code
- Verify EVERY claim in the user story
- "It should validate email" → Try 50 invalid email formats
- "It should handle errors gracefully" → Disconnect network mid-request

### 3. Severity Escalation
- Any unexpected behavior is a bug until proven otherwise
- Report everything: [CRITICAL] for crashes, [WARNING] for UX issues, [INFO] for suggestions
```

#### Making an Agent Focused on Accessibility

Edit `agents/ui_explorer/soul.md`:

```markdown
## Behavioral Directives (Accessibility First)

### 1. Screen Reader Priority
- Test EVERY interactive element with keyboard-only navigation
- Verify ARIA labels, roles, and live regions
- Ensure focus management works in modals and dropdowns

### 2. WCAG 2.1 AA Compliance
- Check color contrast ratios (4.5:1 for normal text, 3:1 for large)
- Verify text can be resized to 200% without loss of function
- Ensure touch targets are at least 44x44 pixels

### 3. Inclusive Design Verification
- Test with keyboard, screen reader, and voice control
- Verify content is accessible without CSS
- Check for seizure-inducing flashes (max 3 per second)
```

#### Adjusting Agent Tool Access

Edit `agents/ui_explorer/agents.md`:

```markdown
## MCP Tools - Accessibility Testing Suite
### Required Tools
1. `query_selector(selector)` — For finding elements
2. `simulate_interaction(selector, "keyboard")` — Test keyboard navigation
3. `check_contrast(selector)` — Verify color contrast ratios
4. `aria_audit(selector)` — Check ARIA attributes
5. `screen_reader_preview(selector)` — Preview screen reader output

## Constraints
- MUST test keyboard navigation for ALL interactive elements
- MUST verify ARIA labels before reporting element as "accessible"
- NEVER skip contrast checks for text elements
```

### Testing Persona Changes

After tuning a persona, run a targeted test:

```bash
# Run a specific scenario that exercises the tuned behavior
python examples/test_scenario.py --agent ui_explorer --focus accessibility

# Check the agent's memory node for behavioral compliance
cat obsidian_vault/Runs/Login_Flow_UI.md
```

## Local Development

### Prerequisites

- Python 3.11+
- Node.js 18+ (for frontend development, optional)
- Obsidian (optional, for visual vault browsing)

### Setup

```bash
# Clone and enter repository
git clone https://github.com/your-org/vectra-qa.git
cd vectra-qa

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install development dependencies
pip install pytest pytest-asyncio black ruff mypy

# Install Playwright browsers
playwright install chromium
```

### Running the FastAPI Backend (with auto-reload)

```bash
cd command_center

# Development mode with auto-reload on file changes
uvicorn main:app --reload --host 0.0.0.0 --port 3000

# The dashboard will be available at http://localhost:3000
# API docs at http://localhost:3000/docs
```

### Running the MCP Server

```bash
# stdio transport (for integration with MCP clients)
python mcp_server/server.py --transport stdio

# SSE transport (for web-based tools)
python mcp_server/server.py --transport sse --port 8080
```

### Obsidian Vault Development

The vault is a plain directory of Markdown files. You can:

1. **Open in Obsidian**: Point Obsidian to `obsidian_vault/` for the full graph experience
2. **Edit manually**: Use any text editor to modify `.md` files
3. **Watch changes**: The file watcher (`obsidian_reader.py`) detects changes automatically

```bash
# Watch vault changes in real-time (for debugging)
python -c "
from command_center.obsidian_reader import reader
import time
while True:
    nodes = reader.get_global_nodes()
    for name, node in nodes.items():
        if node:
            print(f'{name}: {node.frontmatter.get(\"status\", \"unknown\")}')
    time.sleep(2)
"
```

### Frontend Development

The frontend is vanilla HTML with HTMX and Tailwind CSS (via CDN). No build step required!

```bash
# Edit command_center/static/index.html directly
# Refresh browser to see changes

# For Tailwind customization, edit the config in the HTML head
# <script>
#   tailwind.config = { theme: { extend: { colors: { ... } } } }
# </script>
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=mcp_server --cov=command_center

# Run specific test file
pytest tests/test_tools.py

# Run in watch mode (for development)
pytest -f
```

### Code Quality

```bash
# Format code
black mcp_server/ command_center/ examples/ tests/

# Lint
ruff check mcp_server/ command_center/ examples/ tests/

# Type check
mypy mcp_server/ command_center/
```

## Pull Request Process

1. **Fork and Branch**: `git checkout -b feature/my-new-feature`
2. **Write Tests**: Add tests for new tools and agent behaviors
3. **Update Docs**: If you change architecture, update `ARCHITECTURE.md`
4. **Run Quality Checks**: Ensure `black`, `ruff`, and `pytest` pass
5. **Submit PR**: Include a clear description of changes and motivation

### PR Checklist

- [ ] Tests pass (`pytest`)
- [ ] Code is formatted (`black`)
- [ ] No lint errors (`ruff`)
- [ ] Documentation updated
- [ ] Example usage provided for new tools
- [ ] Agent configs updated if adding new capabilities

## Questions?

Open an issue or reach out in our [Discussions](https://github.com/your-org/vectra-qa/discussions) forum.

Happy testing! 🚀
