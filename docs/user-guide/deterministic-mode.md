# Deterministic Mode

Deterministic mode replaces LLM-driven browser agents with scripted YAML playbooks. No API calls, no flakiness — the same playbook always produces the same result.

Use deterministic mode for:

- CI/CD smoke tests
- Regression testing
- Reproducing bugs
- Bypassing LLM rate limits

## How It Works

A playbook is a YAML file that declares a sequence of browser actions. Each action maps to a Playwright operation executed in order. If a required step fails, execution stops.

```yaml
name: Login smoke test
url: https://example.com
steps:
  - action: visit
    url: https://example.com/login
  - action: fill
    selector: "#email"
    value: "test@example.com"
  - action: click
    selector: "#submit"
  - action: assert
    selector: ".dashboard"
    expected_text: "Welcome"
```

## Actions Reference

### 1. `visit`

Navigate to a URL.

```yaml
- action: visit
  url: https://example.com
```

| Field | Required | Description |
|-------|----------|-------------|
| `url` | Yes | Target URL |

### 2. `click`

Click an element by CSS selector.

```yaml
- action: click
  selector: "#submit-btn"
```

| Field | Required | Description |
|-------|----------|-------------|
| `selector` | Yes | CSS selector |

### 3. `fill`

Type text into an input field.

```yaml
- action: fill
  selector: "#email"
  value: "user@example.com"
```

| Field | Required | Description |
|-------|----------|-------------|
| `selector` | Yes | CSS selector |
| `value` | Yes | Text to type |

### 4. `assert`

Verify an element exists, contains expected text, or matches a count.

```yaml
# Element exists
- action: assert
  selector: ".success-message"

# Element contains text
- action: assert
  selector: "h1"
  expected_text: "Dashboard"

# Exact count match
- action: assert
  selector: ".item"
  expected_count: 3
```

| Field | Required | Description |
|-------|----------|-------------|
| `selector` | Yes | CSS selector |
| `expected_text` | No | Substring the element text must contain |
| `expected_count` | No | Exact number of elements expected |

### 5. `screenshot`

Save a screenshot.

```yaml
- action: screenshot
  path: results/homepage.png
  full_page: true
```

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `path` | No | `screenshot.png` | File path to save |
| `full_page` | No | `true` | Capture full page or viewport |

### 6. `wait`

Pause execution for a number of milliseconds.

```yaml
- action: wait
  ms: 2000
```

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `ms` | No | `1000` | Milliseconds to wait |

### 7. `scroll`

Scroll the page.

```yaml
- action: scroll
  direction: bottom
```

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `direction` | No | `bottom` | `bottom` (more directions may be added) |

### 8. `hover`

Hover over an element.

```yaml
- action: hover
  selector: "#dropdown-menu"
```

| Field | Required | Description |
|-------|----------|-------------|
| `selector` | Yes | CSS selector |

## Optional Step Fields

Every action supports:

| Field | Default | Description |
|-------|---------|-------------|
| `required` | `true` | If `false`, failure does not stop the playbook |

```yaml
- action: click
  selector: ".optional-banner-close"
  required: false
```

## Running Playbooks

### Python API

```python
import asyncio
from mcp_server.deterministic import DeterministicTester, load_playbook
from mcp_server.browser_tools import BrowserAutomation

async def main():
    playbook = load_playbook("tests/playbooks/login.yaml")
    browser = BrowserAutomation()
    await browser.start()

    tester = DeterministicTester()
    results = await tester.execute_playbook(playbook, browser)

    for r in results:
        status = "PASS" if r.success else "FAIL"
        print(f"  [{status}] {r.action}: {r.message}")

    await browser.stop()

asyncio.run(main())
```

### Utility Functions

```python
from mcp_server.deterministic import load_playbook, save_playbook

# Load
playbook = load_playbook("playbook.yaml")

# Save
save_playbook(playbook, "output.yaml")
```

## Example: Complete Playbook

```yaml
name: E-commerce checkout smoke test
url: https://shop.example.com
steps:
  - action: visit
    url: https://shop.example.com

  - action: assert
    selector: "h1"
    expected_text: "Shop"

  - action: click
    selector: ".product:first-child .add-to-cart"

  - action: wait
    ms: 500

  - action: click
    selector: "#cart-icon"

  - action: assert
    selector: ".cart-item"
    expected_count: 1

  - action: click
    selector: "#checkout-btn"

  - action: fill
    selector: "#email"
    value: "test@example.com"

  - action: fill
    selector: "#address"
    value: "123 Test Street"

  - action: click
    selector: "#place-order"

  - action: wait
    ms: 1500

  - action: assert
    selector: ".order-confirmation"
    expected_text: "Thank you"

  - action: screenshot
    path: results/order_confirmation.png
    full_page: false
```

## Best Practices

1. **Use `assert` after every interaction** — Verify the page reacted as expected.
2. **Add `wait` after navigation** — Give dynamic content time to load.
3. **Set `required: false` for soft checks** — Cookie banners, optional modals.
4. **Name playbooks descriptively** — Makes CI logs readable.
5. **Store screenshots on failure** — Combine with `assert` steps for debugging.
