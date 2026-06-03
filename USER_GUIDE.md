# User Guide: Testing Your Project with Vectra QA

## Table of Contents

1. [Quick Overview](#quick-overview)
2. [Prerequisites](#prerequisites)
3. [Configuration](#configuration)
4. [Talk to Vectra (Quickstart)](#talk-to-vectra-quickstart)
5. [Writing Your First Test (Advanced)](#writing-your-first-test-advanced)
6. [Run Your Test](#step-3-run-your-test)
7. [Understanding Results](#understanding-results)
8. [Advanced Usage](#advanced-usage)

---

## Quick Overview

Vectra QA tests your web application by deploying autonomous agents that:

1. **Explore your UI** — Click buttons, fill forms, check accessibility
2. **Validate your backend** — Intercept API calls, check responses, verify databases
3. **Report findings** — Write results to Obsidian vault with detailed logs

You don't write test scripts. You describe what to test, and agents figure out how.

The fastest way to start is to **Talk to Vectra** — open the dashboard and have a plain-English conversation with the Live QA Engineer. See [Talk to Vectra (Quickstart)](#talk-to-vectra-quickstart) below.

---

## Prerequisites

### Your Application

- A web application with a URL (local or deployed)
- Common examples: React app, Vue app, Django, Rails, static site

### Vectra QA Setup

```bash
# Clone and start the framework
git clone https://github.com/your-org/vectra-qa.git
cd vectra-qa
cp .env.example .env
# Edit .env with your API keys
docker compose up --build
```

### Verify It's Working

Open <http://localhost:3000> — you should see the dark mode Command Center dashboard.

---

## Configuration

### 1. Tell Agents About Your App

Edit `.env`:

```bash
# Your application's URL
TARGET_URL=http://localhost:3001  # Your dev server
# Or: TARGET_URL=https://staging.myapp.com

# Authentication (if needed)
TEST_USERNAME=test@example.com
TEST_PASSWORD=your-test-password

# What to test
TEST_SCOPE="User login, product search, checkout flow"
```

### 2. Choose Your LLM Provider

```bash
# Option A: OpenAI (fastest, most reliable)
OPENAI_API_KEY=sk-your-key
ORCHESTRATOR_MODEL=openai/gpt-4o

# Option B: MiniMax (good for structured output)
MINIMAX_API_KEY=your-key
ORCHESTRATOR_MODEL=minimax/minimax-text-01

# Option C: Kimi (best for long-context analysis)
KIMI_API_KEY=your-key
DATA_VALIDATOR_MODEL=kimi/kimi-k2
```

### 3. Configure Browser Automation (Optional)

```bash
# Headless mode (default) — runs in background
HEADLESS=true

# Visible mode — watch the browser
HEADLESS=false

# Slow down for debugging
PLAYWRIGHT_SLOW_MO=500  # 500ms delay between actions
```

---

## Talk to Vectra (Quickstart)

The fastest way to test your app is to talk to Vectra. No Python, no test scenario files. Open the dashboard, answer a few plain-English questions, and watch the engineer narrate each test as it runs.

1. Open the dashboard at <http://localhost:3000>.
2. Click the **"Talk to Vectra"** tab in the chat panel.
3. When Vectra asks for a URL, paste the address of the site you want to test.
4. Answer any follow-up questions about your site (does it need login? what should Vectra exercise?).
5. Watch the narration panel — Vectra announces each test as it starts, what it found, and when it finishes.
6. Read the plain-English report Vectra writes when all tests are done. It tells you what works, what's broken, and what to fix first.

### What Vectra Will Ask

Vectra walks through 6 stages. At each one, it tells you what it's doing and what it needs from you.

1. **Greeting** — Vectra introduces itself and asks for the URL you want to test.
2. **Recon** — Vectra inspects your site and decides if it's a landing page, blog, e-commerce store, or SaaS app. It shares its guess and asks you to confirm or correct it.
3. **Context** — Vectra asks the questions it needs before planning tests. For an e-commerce store, that might be "do you have a test account?". For a SaaS app, "which dashboard page should I exercise?".
4. **Plan** — Vectra proposes the tests it intends to run and asks for your approval. You can add, remove, or change any test.
5. **Execute** — Vectra runs each test, narrates what it's doing, and reports findings as it goes. If a test needs a password, Vectra asks for it in a separate masked input — your secret never touches the chat log, the Obsidian vault, or your terminal output.
6. **Report** — Vectra writes a plain-English summary you can read end-to-end. No jargon, no raw JSON. Just what works, what's broken, and what to fix first.

### Credentials Are Handled Safely

If Vectra needs a password, it asks in a masked field. The secret is sent to the engineer, used to inject into the browser session, then cleared from memory. It never appears in chat history, the Obsidian vault, or your logs.

For test scenario files, custom objectives, and CI integration, see [Writing Your First Test (Advanced)](#writing-your-first-test-advanced) below.

---

## Writing Your First Test (Advanced)

> **Note**: This is the advanced path. Most users should start with [Talk to Vectra (Quickstart)](#talk-to-vectra-quickstart) above. The scenario-file path is for CI/CD pipelines, custom test objectives, and power users who want fine-grained control over agent behaviour.

### Step 1: Create a Test Scenario File

Create `examples/my_app_test.py`:

```python
#!/usr/bin/env python3
"""
Test Scenario: My Application
Tests: Login flow, dashboard navigation, profile update
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp_server.tools import execute_tool
import time


def test_login_flow():
    """Test user authentication."""
    print("\n=== Testing Login Flow ===")
    
    # Spawn UI Explorer to test the login page
    result = execute_tool("spawn_agent", {
        "role": "ui_explorer",
        "objective": (
            "Test the login page at /login. "
            "1. Verify email and password fields are visible. "
            "2. Fill in test credentials. "
            "3. Click login button. "
            "4. Verify redirect to dashboard. "
            "5. Check for any error messages or validation issues."
        ),
        "memory_node": "Runs/Login_Test.md"
    })
    
    print(f"UI Explorer spawned: {result['result']['agent_id']}")
    
    # Wait for UI tests to complete
    time.sleep(5)
    
    # Spawn Data Validator to verify API calls
    result = execute_tool("spawn_agent", {
        "role": "data_validator",
        "objective": (
            "Monitor login API calls. "
            "1. Intercept POST /api/auth/login. "
            "2. Validate request payload contains email and password. "
            "3. Verify response contains JWT token. "
            "4. Check token expiration is reasonable. "
            "5. Verify session cookie is set correctly."
        ),
        "memory_node": "Runs/Login_API_Test.md"
    })
    
    print(f"Data Validator spawned: {result['result']['agent_id']}")
    
    # Wait for backend tests
    time.sleep(5)
    
    print("✓ Login flow tests complete. Check Command Center for results.")


def test_critical_user_journey():
    """Test the most important user path."""
    print("\n=== Testing Critical User Journey ===")
    
    result = execute_tool("spawn_agent", {
        "role": "ui_explorer",
        "objective": (
            "Complete end-to-end user journey: "
            "1. Login with test account. "
            "2. Navigate to main feature (e.g., dashboard). "
            "3. Perform primary action (e.g., create item). "
            "4. Verify success state. "
            "5. Logout and verify session cleared."
        ),
        "memory_node": "Runs/Critical_Journey_Test.md"
    })
    
    print(f"Agent spawned: {result['result']['agent_id']}")
    print("✓ Critical journey test initiated.")


if __name__ == "__main__":
    print("=" * 60)
    print("Vectra QA - My Application Test Suite")
    print("=" * 60)
    
    test_login_flow()
    test_critical_user_journey()
    
    print("\n" + "=" * 60)
    print("All tests initiated!")
    print("View results at: http://localhost:3000")
    print("Obsidian vault: obsidian_vault/Runs/")
    print("=" * 60)
```

### Step 2: Customize the Objectives

The key is writing clear **objectives** for each agent. Be specific:

**Good Objective:**

```
"Test the checkout flow: 1) Add item to cart, 2) Click checkout, 
3) Fill shipping form with test data, 4) Select payment method,
5) Confirm order, 6) Verify order confirmation page shows order number"
```

**Bad Objective:**

```
"Test the app"
```

### Step 3: Run Your Test

```bash
# Terminal 1: Start Vectra QA (if not running)
docker compose up

# Terminal 2: Run your test
cd /home/bugra/Documents/projects/vectra-qa
python examples/my_app_test.py
```

### Step 4: Watch Results in Real-Time

Open <http://localhost:3000> and watch:

- **Orchestrator Feed** — See what agents are doing
- **Active Spawns** — Watch agents start and complete
- **Obsidian Nodes** — View detailed findings

---

## Understanding Results

### Where Results Are Stored

1. **Command Center Dashboard** — Live updates
2. **Obsidian Vault Files** — Persistent records
   - `obsidian_vault/Runs/Login_Test.md` — UI test results
   - `obsidian_vault/Runs/Login_API_Test.md` — Backend test results
   - `obsidian_vault/Global/Test_Run_Master.md` — Summary

### Reading Agent Reports

Each agent writes a Markdown file with:

```markdown
---
status: completed
result: pass
confidence_score: 87
selectors_tested:
  - "#login-form"
  - "#email-input"
---

# Test Results

## Findings
- ✅ Login form renders correctly
- ✅ Email validation works
- ⚠️ Password field lacks aria-label

## Wiki-Links
- [[Test_Run_Master]] — Parent run
```

### Interpreting Confidence Scores

- **90-100%** — Excellent, minimal issues
- **70-89%** — Good, minor issues found
- **50-69%** — Fair, significant issues
- **0-49%** — Poor, major problems or test failure

---

## Advanced Usage

### Testing Multiple Pages

```python
# Test multiple features in parallel
execute_tool("spawn_agent", {
    "role": "ui_explorer",
    "objective": "Test /products page: search, filter, sort",
    "memory_node": "Runs/Products_Test.md"
})

execute_tool("spawn_agent", {
    "role": "ui_explorer",
    "objective": "Test /cart page: add items, update quantity, remove",
    "memory_node": "Runs/Cart_Test.md"
})

execute_tool("spawn_agent", {
    "role": "data_validator",
    "objective": "Verify /api/products endpoints",
    "memory_node": "Runs/Products_API_Test.md"
})
```

### Testing with Authentication

```python
# Pre-authenticate before testing protected routes
execute_tool("spawn_agent", {
    "role": "ui_explorer",
    "objective": (
        "1. Login with username='test@example.com' password='test123'. "
        "2. Verify successful login. "
        "3. Navigate to /admin dashboard. "
        "4. Test admin features."
    ),
    "memory_node": "Runs/Admin_Test.md"
})
```

### Regression Testing

```python
# Test after each deploy
execute_tool("spawn_agent", {
    "role": "ui_explorer",
    "objective": (
        "Regression test: Verify all navigation links work. "
        "Test: Home, About, Products, Contact, Login. "
        "Verify no 404 errors."
    ),
    "memory_node": "Runs/Regression_Nav_Test.md"
})
```

### Accessibility Testing

```python
# Focus on accessibility
execute_tool("spawn_agent", {
    "role": "ui_explorer",
    "objective": (
        "Accessibility audit: "
        "1. Test keyboard navigation for all interactive elements. "
        "2. Verify alt text on all images. "
        "3. Check color contrast ratios. "
        "4. Verify ARIA labels. "
        "5. Test with screen reader simulation."
    ),
    "memory_node": "Runs/Accessibility_Test.md"
})
```

---

## Troubleshooting

### Agents Not Spawning

- Check MCP Server is running: `docker compose ps`
- Verify API keys in `.env`
- Check logs: `docker compose logs mcp-server`

### Tests Taking Too Long

- Reduce test scope in objectives
- Set timeout in spawn parameters
- Use `PLAYWRIGHT_SLOW_MO=0` for faster execution

### False Positives/Negatives

- Refine objectives to be more specific
- Add more context about expected behavior
- Check if app requires specific state (e.g., seeded database)

---

## Next Steps

1. **Start Simple** — Test one feature at a time
2. **Iterate** — Refine objectives based on results
3. **Build Library** — Create reusable test scenarios
4. **CI/CD Integration** — Run tests on every deploy

## Example: Complete E-Commerce Test Suite

See `examples/ecommerce_test.py` for a full example testing:

- Product browsing
- Cart management
- Checkout flow
- Order confirmation
- Email validation

---

**Questions?** Open an issue at <https://github.com/your-org/vectra-qa/issues>
