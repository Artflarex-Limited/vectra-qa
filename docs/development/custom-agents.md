# Custom Agents

This guide explains how to create custom agents for specialized testing scenarios.

## Agent Architecture

An agent consists of:

1. **Worker Script** — Main execution logic
2. **Soul File** — Behavioral DNA and personality
3. **Agents File** — Operational constraints
4. **Registration** — Integration with the system

## Quick Start

### 1. Create Agent Directory

```bash
mkdir agents/my_custom_agent
touch agents/my_custom_agent/{worker.py,soul.md,agents.md,__init__.py}
```

### 2. Write Worker Script

```python
# agents/my_custom_agent/worker.py
#!/usr/bin/env python3
"""
My Custom Agent - Performance Testing Specialist

This agent measures page load performance and identifies bottlenecks.
"""

import sys
import asyncio
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from mcp_server.tools import vault
from mcp_server.browser_tools import BrowserAutomation


async def update_progress(agent_id, memory_node, step, progress, findings=""):
    """Update agent progress in memory node."""
    try:
        from datetime import datetime
        updates = {
            "status": "active",
            "last_action": step,
            "progress_percent": progress,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
        
        if findings:
            node = vault.read_node(memory_node)
            current_content = node["content"]
            new_content = current_content + f"\n\n## [{datetime.utcnow().strftime('%H:%M:%S')}] {step}\n{findings}"
            vault.write_node(memory_node, new_content, node["frontmatter"])
        
        vault.update_frontmatter(memory_node, updates)
    except Exception as e:
        print(f"[ERROR] Failed to update progress: {e}", file=sys.stderr)


async def test_performance(browser, url, agent_id, memory_node):
    """Test page performance."""
    await update_progress(agent_id, memory_node, "Starting performance test", 10)
    
    # Visit page and measure load time
    start_time = asyncio.get_event_loop().time()
    result = await browser.visit(url)
    load_time = asyncio.get_event_loop().time() - start_time
    
    if not result["success"]:
        await update_progress(agent_id, memory_node, "Failed to load page", 0,
            f"**ERROR**: {result.get('error', 'Unknown')}")
        return False
    
    findings = f"""
- **URL**: {result['url']}
- **Load Time**: {load_time:.2f}s
- **Status**: {result['status']}
"""
    await update_progress(agent_id, memory_node, "Page loaded", 30, findings)
    
    # Additional performance checks...
    
    return True


async def run_agent(agent_id, memory_node):
    """Main agent execution loop."""
    print(f"[CUSTOM AGENT {agent_id}] Starting...")
    
    # Read objective
    try:
        node = vault.read_node(memory_node)
        objective = node["frontmatter"].get("objective", "")
        print(f"[CUSTOM AGENT {agent_id}] Objective: {objective[:100]}...")
    except Exception as e:
        print(f"[CUSTOM AGENT {agent_id}] ERROR reading memory node: {e}")
        return
    
    # Extract URL
    url = None
    if "http" in objective:
        words = objective.split()
        for word in words:
            if word.startswith("http"):
                url = word.strip("./,;")
                break
    
    if not url:
        await update_progress(agent_id, memory_node, "No URL found", 0,
            "**ERROR**: Could not extract URL from objective.")
        return
    
    # Start browser
    browser = BrowserAutomation(headless=True)
    
    try:
        await browser.start()
        success = await test_performance(browser, url, agent_id, memory_node)
        
        if success:
            vault.update_frontmatter(memory_node, {
                "status": "completed",
                "result": "pass",
                "progress_percent": 100
            })
        else:
            vault.update_frontmatter(memory_node, {
                "status": "failed",
                "result": "fail"
            })
            
    except Exception as e:
        print(f"[CUSTOM AGENT {agent_id}] CRITICAL ERROR: {e}")
        vault.update_frontmatter(memory_node, {
            "status": "failed",
            "result": "fail",
            "error": str(e)
        })
    finally:
        await browser.close()


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python worker.py <agent_id> <memory_node_path>")
        sys.exit(1)
    
    agent_id = sys.argv[1]
    memory_node = sys.argv[2]
    asyncio.run(run_agent(agent_id, memory_node))
```

### 3. Create Soul File

```markdown
# My Custom Agent Soul

## Identity
Performance Testing Specialist

## Personality
- Methodical and data-driven
- Obsessed with load times and metrics
- Speaks in milliseconds and percentages
- Treats every millisecond of latency as a bug

## Philosophy
- Performance is a feature, not an optimization
- User experience is directly tied to speed
- Measure everything, optimize what matters

## Decision Making
When encountering slow pages:
1. Measure exact load time
2. Identify blocking resources
3. Check for unnecessary requests
4. Report findings with specific metrics
5. Suggest concrete optimizations

## Communication Style
- Precise and metric-focused
- Uses benchmarks and comparisons
- Highlights performance regressions
- Celebrates speed improvements
```

### 4. Create Agents File

```markdown
# My Custom Agent Operational Constraints

## Resource Limits
- Max test duration: 2 minutes
- Max concurrent requests: 10
- Screenshot capture: Optional

## Browser Configuration
- Headless mode: Required
- Viewport: 1920x1080 (default)
- Cache: Disabled for consistent results

## Test Scope
- Page load performance
- Resource loading times
- JavaScript execution time
- Network request analysis

## Output Format
- Load time in milliseconds
- Resource breakdown
- Performance score (0-100)
- Optimization recommendations

## Error Handling
- Timeout after 30s per page
- Retry failed requests once
- Log all errors with stack traces
```

### 5. Register Agent

Update `mcp_server/tools.py`:

```python
# In AgentSpawner.spawn_agent()
worker_scripts = {
    "ui_explorer": "agents/ui_explorer/worker.py",
    "data_validator": "agents/data_validator/worker.py",
    "my_custom_agent": "agents/my_custom_agent/worker.py"
}
```

Update `command_center/chatbot.py`:

```python
TEST_TYPES = {
    # ... existing types ...
    "performance": {
        "name": "Performance Test",
        "description": "Page load speed and resource optimization",
        "role": "my_custom_agent",
        "keywords": ["performance", "speed", "load time", "optimization", "fast"]
    }
}
```

Update `command_center/static/index.html`:

```html
<select name="test_type" required class="field-input">
    <!-- existing options -->
    <option value="performance">Performance Test</option>
</select>
```

## Agent Patterns

### Pattern 1: Simple Checker

For agents that perform a single check:

```python
async def run_agent(agent_id, memory_node):
    # Read objective
    # Perform check
    # Write result
    # Exit
```

### Pattern 2: Multi-Step Worker

For agents with multiple phases:

```python
async def run_agent(agent_id, memory_node):
    phases = [
        ("Phase 1: Setup", 10, setup_phase),
        ("Phase 2: Execution", 50, execution_phase),
        ("Phase 3: Validation", 90, validation_phase)
    ]
    
    for name, progress, func in phases:
        await update_progress(agent_id, memory_node, name, progress)
        await func(browser, url, agent_id, memory_node)
```

### Pattern 3: External Service

For agents that call external APIs:

```python
import aiohttp

async def check_external_service(url):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            return {
                "status": response.status,
                "latency": response.elapsed.total_seconds()
            }
```

## Advanced Features

### Custom Metrics

Track custom metrics in frontmatter:

```python
vault.update_frontmatter(memory_node, {
    "custom_metrics": {
        "load_time_ms": 1200,
        "resource_count": 45,
        "performance_score": 85
    }
})
```

### Custom Screenshots

Capture specific elements:

```python
# Screenshot specific element
await browser.page.screenshot(
    path="obsidian_vault/Screenshots/element.png",
    element="#hero-section"
)
```

### Inter-Agent Communication

Read other agents' results:

```python
# Find related test
for node_file in Path("obsidian_vault/Runs").glob("*.md"):
    node = vault.read_node(str(node_file))
    if "homepage" in node["frontmatter"].get("objective", ""):
        # Use homepage results
        pass
```

## Testing Your Agent

### Manual Test

```bash
# Create test memory node
cat > obsidian_vault/Runs/Test_Custom.md << 'EOF'
---
agent_role: my_custom_agent
agent_id: test-agent
status: spawned
objective: Test performance of https://example.com
---

# Test Log
EOF

# Run agent directly
python agents/my_custom_agent/worker.py test-agent Runs/Test_Custom.md
```

### Integration Test

```python
# tests/test_custom_agent.py
import pytest
from agents.my_custom_agent.worker import test_performance

@pytest.mark.asyncio
async def test_performance_check():
    from mcp_server.browser_tools import BrowserAutomation
    browser = BrowserAutomation(headless=True)
    await browser.start()
    
    # Mock memory node
    # ... test logic ...
    
    await browser.close()
```

## Common Pitfalls

### 1. Missing Error Handling

```python
# Bad
result = await browser.visit(url)
# No error check

# Good
result = await browser.visit(url)
if not result["success"]:
    await handle_error(result.get("error"))
    return False
```

### 2. Not Updating Progress

```python
# Bad
# Silent execution

# Good
await update_progress(agent_id, memory_node, "Step 1", 25)
# Do work
await update_progress(agent_id, memory_node, "Step 2", 50)
```

### 3. Hardcoded Values

```python
# Bad
url = "https://example.com"  # Should come from objective

# Good
url = extract_url(objective)
```

### 4. Resource Leaks

```python
# Bad
browser = BrowserAutomation()
await browser.start()
# No close()

# Good
browser = BrowserAutomation()
try:
    await browser.start()
    # Do work
finally:
    await browser.close()
```

## Examples

### Security Scanner Agent

```python
async def test_security(browser, url, agent_id, memory_node):
    """Check for common security issues."""
    findings = []
    
    # Check HTTPS
    if not url.startswith("https://"):
        findings.append("❌ Site does not use HTTPS")
    
    # Check for mixed content
    # Check for exposed headers
    # Check for CSRF tokens
    
    return findings
```

### SEO Audit Agent

```python
async def test_seo(browser, url, agent_id, memory_node):
    """Check SEO best practices."""
    result = await browser.visit(url)
    
    # Check meta tags
    # Check heading structure
    # Check alt text
    # Check sitemap
    
    return seo_score
```

## Next Steps

1. Test your agent locally
2. Add tests to `tests/` directory
3. Update documentation
4. Submit PR with agent description
5. Share your agent in GitHub Discussions
