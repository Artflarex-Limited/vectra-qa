# Vectra QA Quick Reference Card

## 🚀 Start Everything

```bash
cd vectra-qa
docker compose up --build
# Open: http://localhost:3000
```

## 📝 Test Your App (3 Steps)

### Step 1: Set Your App URL

```bash
# In .env
TARGET_URL=http://localhost:3001
```

### Step 2: Write a Test

```python
from mcp_server.tools import execute_tool

# Spawn an agent to test your UI
execute_tool("spawn_agent", {
    "role": "ui_explorer",
    "objective": "Test /login page: verify form, submit credentials, check redirect",
    "memory_node": "Runs/Login_Test.md"
})

# Spawn an agent to validate your API
execute_tool("spawn_agent", {
    "role": "data_validator", 
    "objective": "Monitor /api/auth/login: verify JWT token, check response codes",
    "memory_node": "Runs/Login_API_Test.md"
})
```

### Step 3: Run It

```bash
python examples/test_real_app.py
```

## 🎯 Common Test Patterns

### Login Flow

```python
{
    "role": "ui_explorer",
    "objective": (
        "Test login: 1) Load /login, 2) Fill credentials, "
        "3) Submit form, 4) Verify dashboard redirect"
    )
}
```

### Form Validation

```python
{
    "role": "ui_explorer",
    "objective": (
        "Test signup form: 1) Submit empty form, 2) Invalid email, "
        "3) Weak password, 4) Valid submission"
    )
}
```

### API Monitoring

```python
{
    "role": "data_validator",
    "objective": (
        "Monitor checkout API: 1) POST /api/orders, "
        "2) Validate request payload, 3) Check response, "
        "4) Verify payment processing"
    )
}
```

### Accessibility

```python
{
    "role": "ui_explorer",
    "objective": (
        "Accessibility audit: 1) Keyboard nav, 2) ARIA labels, "
        "3) Color contrast, 4) Screen reader compatibility"
    )
}
```

## 📊 View Results

| What | Where |
|------|-------|
| Live dashboard | <http://localhost:3000> |
| UI test details | `obsidian_vault/Runs/*_UI.md` |
| API test details | `obsidian_vault/Runs/*_API.md` |
| Summary | `obsidian_vault/Global/Test_Run_Master.md` |
| Visual graph | Open vault in Obsidian app |

## 🐛 Troubleshooting

```bash
# Check if services are running
docker compose ps

# View logs
docker compose logs -f mcp-server
docker compose logs -f command-center

# Restart a service
docker compose restart command-center

# Full reset
docker compose down -v
docker compose up --build
```

## 🎛️ Agent Roles

| Role | Best For | Example |
|------|----------|---------|
| `ui_explorer` | Frontend testing | DOM, accessibility, user flows |
| `data_validator` | Backend testing | APIs, databases, auth tokens |

## 🌍 Environment Variables

```bash
# Required
TARGET_URL=http://your-app.com
OPENAI_API_KEY=sk-...

# Optional
HEADLESS=false           # Show browser
PLAYWRIGHT_SLOW_MO=500   # Slow down (ms)
TEST_USERNAME=...        # Login credentials
TEST_PASSWORD=...
```

## 📚 Documentation

- **Full Guide**: [USER_GUIDE.md](USER_GUIDE.md)
- **Architecture**: [ARCHITECTURE.md](ARCHITECTURE.md)
- **Contributing**: [CONTRIBUTING.md](CONTRIBUTING.md)
- **Example Test**: [examples/test_real_app.py](examples/test_real_app.py)
