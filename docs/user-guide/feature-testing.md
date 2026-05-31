# Feature Testing Guide

Vectra QA includes 6 specialized feature testing modules that can be used directly via MCP tools or spawned as dedicated agents.

## Authentication Testing (`test_auth_flow`)

Test login/logout flows with security validation.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `login_url` | string | ✅ | URL of the login page |
| `username` | string | ❌ | Username for login test |
| `password` | string | ❌ | Password for login test |
| `logout_url` | string | ❌ | URL of the logout page |

### Security Checks

- **HTTPS Enforcement**: Flags login pages served over HTTP
- **Password Field Detection**: Verifies password inputs use `type="password"`
- **Autocomplete Prevention**: Checks for `autocomplete="current-password"`
- **Session Cookie Security**: Validates `HttpOnly`, `Secure`, `SameSite` attributes
- **Token Storage**: Detects authentication tokens in `localStorage`

### Example

```python
from mcp_server.tools import execute_tool

result = execute_tool("test_auth_flow", {
    "login_url": "https://example.com/login",
    "username": "test@example.com",
    "password": "password123",
    "logout_url": "https://example.com/logout"
})

print(f"Status: {result['status']}")
print(f"Findings: {len(result['findings'])}")
for finding in result['findings']:
    print(f"  [{finding['severity']}] {finding['title']}: {finding['description']}")
```

### Agent Usage

```python
result = execute_tool("spawn_agent", {
    "role": "auth_tester",
    "objective": "Test login flow at https://example.com/login with username 'test@example.com' and password 'password123'",
    "memory_node": "Runs/Auth_Test.md"
})
```

---

## Visual Regression Testing (`test_visual_regression`)

Compare current page screenshots against baselines.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `url` | string | ✅ | URL to capture and compare |
| `name` | string | ❌ | Name for baseline identification |

### How It Works

1. **First Run**: Captures baseline screenshot and saves to `obsidian_vault/Baselines/`
2. **Subsequent Runs**: Compares current screenshot against baseline
3. **Pixel Difference**: Calculates percentage of changed pixels
4. **Threshold**: Fails if difference exceeds configurable threshold

### Example

```python
result = execute_tool("test_visual_regression", {
    "url": "https://example.com",
    "name": "homepage"
})

if result["status"] == "pass":
    print("✅ No visual changes detected")
elif result["status"] == "warning":
    print(f"⚠️ Visual difference: {result['metrics']['pixel_difference_percent']:.2f}%")
else:
    print(f"❌ Baseline not found - created new baseline")
```

### Agent Usage

```python
result = execute_tool("spawn_agent", {
    "role": "visual_regression_tester",
    "objective": "Compare https://example.com against baseline 'homepage'",
    "memory_node": "Runs/Visual_Test.md"
})
```

---

## Performance Testing (`test_performance`)

Measure Core Web Vitals and page performance metrics.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `url` | string | ✅ | URL to test |
| `thresholds` | object | ❌ | Custom thresholds (see below) |

### Default Thresholds (Core Web Vitals)

| Metric | Threshold | Description |
|--------|-----------|-------------|
| `lcp_ms` | 2500ms | Largest Contentful Paint |
| `fid_ms` | 100ms | First Input Delay |
| `cls` | 0.1 | Cumulative Layout Shift |
| `ttfb_ms` | 600ms | Time to First Byte |
| `fcp_ms` | 1800ms | First Contentful Paint |
| `tbt_ms` | 200ms | Total Blocking Time |

### Metrics Collected

- **Navigation Timing**: `responseStart`, `requestStart`, `domComplete`
- **Paint Metrics**: First Contentful Paint (FCP), Largest Contentful Paint (LCP)
- **Layout Stability**: Cumulative Layout Shift (CLS)
- **Resource Loading**: Total transfer size, resource count
- **Page Size**: Flag if total size exceeds 5MB

### Example

```python
result = execute_tool("test_performance", {
    "url": "https://example.com",
    "thresholds": {
        "lcp_ms": 2000,      # Stricter LCP
        "ttfb_ms": 400       # Stricter TTFB
    }
})

print(f"TTFB: {result['metrics']['ttfb_ms']}ms")
print(f"FCP: {result['metrics']['fcp_ms']}ms")
print(f"Total Size: {result['metrics']['total_transfer_size_bytes'] / 1024:.1f}KB")

if result['status'] == 'pass':
    print("✅ All metrics within thresholds")
else:
    for finding in result['findings']:
        print(f"❌ {finding['title']}: {finding['description']}")
```

### Lighthouse CI Integration

If `lighthouse` is installed globally, performance tests automatically include Lighthouse scores:

```bash
npm install -g lighthouse
```

### Agent Usage

```python
result = execute_tool("spawn_agent", {
    "role": "performance_tester",
    "objective": "Test performance of https://example.com with strict thresholds: lcp_ms=2000, ttfb_ms=400",
    "memory_node": "Runs/Performance_Test.md"
})
```

---

## API Contract Testing (`test_api_contract`)

Validate API responses against OpenAPI schemas.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `base_url` | string | ✅ | Base URL of the API |
| `endpoint` | string | ✅ | API endpoint path (e.g., `/api/v1/users`) |
| `method` | string | ✅ | HTTP method (`GET`, `POST`, `PUT`, `DELETE`, `PATCH`) |
| `schema_path` | string | ❌ | Path to OpenAPI schema file |
| `body` | object | ❌ | Request body for POST/PUT |

### Validation Checks

- **Status Code**: Validates HTTP status matches schema
- **Content-Type**: Checks `application/json` header
- **Response Body**: Validates JSON structure against schema
- **Required Fields**: Ensures all required fields present
- **Type Checking**: Validates field types (string, integer, boolean, etc.)

### Example

```python
result = execute_tool("test_api_contract", {
    "base_url": "https://api.example.com",
    "endpoint": "/api/v1/users",
    "method": "GET",
    "schema_path": "./openapi.json"
})

print(f"Status: {result['status']}")
print(f"HTTP Status: {result['metrics']['http_status']}")

if result['status'] == 'pass':
    print("✅ API contract validated")
else:
    for finding in result['findings']:
        print(f"❌ {finding['title']}: {finding['description']}")
```

### Agent Usage

```python
result = execute_tool("spawn_agent", {
    "role": "api_contract_tester",
    "objective": "Validate GET /api/v1/users against schema at ./openapi.json",
    "memory_node": "Runs/API_Test.md"
})
```

---

## Accessibility Testing (`test_accessibility`)

Run accessibility checks using axe-core with manual fallback.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `url` | string | ✅ | URL to test |
| `standard` | string | ❌ | WCAG standard: `wcag2a`, `wcag2aa` (default), `wcag21aa` |

### Checks Performed

#### Automated (axe-core)
- Color contrast ratios
- ARIA usage and validity
- Form label associations
- Focus management
- Heading hierarchy

#### Manual Fallback
- Images without `alt` text
- Form inputs without labels
- Missing `lang` attribute
- Missing `<h1>` heading

### Example

```python
result = execute_tool("test_accessibility", {
    "url": "https://example.com",
    "standard": "wcag2aa"
})

print(f"Status: {result['status']}")
print(f"Findings: {len(result['findings'])}")

for finding in result['findings']:
    severity = finding['severity']
    icon = "🔴" if severity == "critical" else "🟠" if severity == "high" else "🟡"
    print(f"{icon} [{severity.upper()}] {finding['title']}")
    print(f"   {finding['description']}")
```

### Agent Usage

```python
result = execute_tool("spawn_agent", {
    "role": "accessibility_tester",
    "objective": "Test accessibility of https://example.com against WCAG 2.1 AA",
    "memory_node": "Runs/Accessibility_Test.md"
})
```

---

## Multi-Browser Testing (`test_multi_browser`)

Run smoke tests across Chromium, Firefox, and WebKit.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `url` | string | ✅ | URL to test |

### How It Works

1. Launches each browser (Chromium, Firefox, WebKit)
2. Navigates to the URL
3. Verifies page loads successfully
4. Collects basic metrics (HTTP status, load time)
5. Closes browser and reports results

### Results Format

```json
{
  "chromium": {
    "status": "pass",
    "metrics": {"http_status": 200},
    "findings": []
  },
  "firefox": {
    "status": "pass",
    "metrics": {"http_status": 200},
    "findings": []
  },
  "webkit": {
    "status": "pass",
    "metrics": {"http_status": 200},
    "findings": []
  }
}
```

### Example

```python
result = execute_tool("test_multi_browser", {
    "url": "https://example.com"
})

for browser, data in result.items():
    status_icon = "✅" if data["status"] == "pass" else "❌"
    print(f"{status_icon} {browser.title()}: {data['status']}")
```

### Agent Usage

```python
result = execute_tool("spawn_agent", {
    "role": "multi_browser_tester",
    "objective": "Test https://example.com across all supported browsers",
    "memory_node": "Runs/Multi_Browser_Test.md"
})
```

---

## Complete Test Suite Example

Run all feature tests in sequence:

```python
from mcp_server.tools import execute_tool

url = "https://example.com"

# 1. Auth Test
auth_result = execute_tool("test_auth_flow", {
    "login_url": f"{url}/login",
    "username": "test@example.com",
    "password": "password123"
})

# 2. Performance Test
perf_result = execute_tool("test_performance", {
    "url": url,
    "thresholds": {"lcp_ms": 2500, "ttfb_ms": 600}
})

# 3. Accessibility Test
a11y_result = execute_tool("test_accessibility", {
    "url": url,
    "standard": "wcag2aa"
})

# 4. Visual Regression
visual_result = execute_tool("test_visual_regression", {
    "url": url,
    "name": "homepage"
})

# 5. Multi-Browser
browser_result = execute_tool("test_multi_browser", {
    "url": url
})

# Compile results
results = {
    "auth": auth_result,
    "performance": perf_result,
    "accessibility": a11y_result,
    "visual": visual_result,
    "browsers": browser_result
}

# Save to vault
from mcp_server.tools import get_vault
vault = get_vault()
vault.write_node(
    "Runs/Full_Test_Suite.md",
    content=f"# Full Test Suite Results\n\n```json\n{json.dumps(results, indent=2)}\n```",
    frontmatter={"status": "completed", "url": url}
)
```

## Environment Variables

Configure feature testers via environment variables:

```bash
# Browser settings
HEADLESS=true                    # Run browsers headless

# Performance thresholds (override defaults)
PERFORMANCE_LCP_MS=2500
PERFORMANCE_TTFB_MS=600
PERFORMANCE_FCP_MS=1800

# Accessibility standard
ACCESSIBILITY_STANDARD=wcag2aa

# Visual regression
VISUAL_REGRESSION_THRESHOLD=0.1  # 10% pixel difference threshold
```
