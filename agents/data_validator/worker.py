#!/usr/bin/env python3
"""
Data Validator Worker - Real API Validation

This worker is spawned by the MCP server when a Data Validator agent is created.
It performs real HTTP request interception and validation using Playwright.

Usage:
    python agents/data_validator/worker.py <agent_id> <memory_node_path>
"""

import sys
import os
import asyncio
import json
from pathlib import Path
from datetime import datetime, timezone

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from mcp_server.tools import vault
from mcp_server.browser_tools import BrowserAutomation


async def update_progress(agent_id: str, memory_node: str, step: str, progress: int, findings: str = ""):
    """Update agent progress in memory node."""
    try:
        updates = {
            "status": "active",
            "last_action": step,
            "progress_percent": progress,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z"
        }
        
        if findings:
            node = vault.read_node(memory_node)
            current_content = node["content"]
            new_content = current_content + f"\n\n## [{datetime.now(timezone.utc).strftime('%H:%M:%S')}] {step}\n{findings}"
            vault.write_node(memory_node, new_content, node["frontmatter"])
        
        vault.update_frontmatter(memory_node, updates)
    except Exception as e:
        print(f"[ERROR] Failed to update progress: {e}", file=sys.stderr)


async def monitor_api_calls(browser: BrowserAutomation, url: str, agent_id: str, memory_node: str):
    """Monitor and validate API calls during page navigation."""
    await update_progress(agent_id, memory_node, "Setting up API monitoring", 10)
    
    # Set up request interception
    intercepted_requests = []
    
    async def handle_route(route, request):
        """Intercept and log requests."""
        intercepted_requests.append({
            "url": request.url,
            "method": request.method,
            "headers": dict(request.headers),
            "time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z"
        })
        await route.continue_()
    
    # Intercept all requests
    await browser.page.route("**/*", handle_route)
    
    await update_progress(agent_id, memory_node, "Starting page navigation", 20)
    
    # Visit page
    result = await browser.visit(url)
    if not result["success"]:
        await update_progress(agent_id, memory_node, "Failed to load page", 0,
            f"**ERROR**: {result.get('error', 'Unknown')}")
        return False
    
    findings = f"""
- **URL**: {url}
- **Page Status**: {result['status']}
- **Page Title**: {result['title']}
"""
    await update_progress(agent_id, memory_node, "Page loaded", 30, findings)
    
    # Wait a bit for all requests to complete
    await asyncio.sleep(3)
    
    # Analyze intercepted requests
    await update_progress(agent_id, memory_node, f"Analyzing {len(intercepted_requests)} requests", 50)
    
    # Categorize requests
    api_requests = [r for r in intercepted_requests if "/api/" in r["url"] or "/graphql" in r["url"]]
    static_requests = [r for r in intercepted_requests if any(ext in r["url"] for ext in [".js", ".css", ".png", ".jpg", ".svg", ".woff"])]
    other_requests = [r for r in intercepted_requests if r not in api_requests and r not in static_requests]
    
    findings = f"""
### Request Breakdown
- **Total requests**: {len(intercepted_requests)}
- **API requests**: {len(api_requests)}
- **Static assets**: {len(static_requests)}
- **Other**: {len(other_requests)}
"""
    await update_progress(agent_id, memory_node, "Request analysis complete", 60, findings)
    
    # Analyze API requests in detail
    if api_requests:
        api_findings = "### API Request Details\n"
        for req in api_requests[:10]:  # Show first 10
            api_findings += f"- `{req['method']}` {req['url'][:80]}\n"
        
        await update_progress(agent_id, memory_node, "API requests analyzed", 70, api_findings)
    
    # Check for HTTPS usage
    https_count = sum(1 for r in intercepted_requests if r["url"].startswith("https"))
    http_count = sum(1 for r in intercepted_requests if r["url"].startswith("http:"))
    
    security_findings = f"""
### Security Analysis
- **HTTPS requests**: {https_count}
- **HTTP requests**: {http_count}
- **Security grade**: {'A' if http_count == 0 else 'C' if http_count < 3 else 'F'}
"""
    await update_progress(agent_id, memory_node, "Security analysis complete", 80, security_findings)
    
    # Check response statuses from browser logs
    if browser.network_logs:
        statuses = {}
        for log in browser.network_logs:
            status = log.get("status", 0)
            statuses[status] = statuses.get(status, 0) + 1
        
        status_findings = "### Response Status Codes\n"
        for status, count in sorted(statuses.items()):
            status_findings += f"- **{status}**: {count} requests\n"
        
        await update_progress(agent_id, memory_node, "Response status analysis", 90, status_findings)
    
    # Check console errors
    errors = await browser.get_console_errors()
    if errors:
        error_findings = f"### Console Errors\n- **Count**: {len(errors)}\n"
        for error in errors[:5]:
            error_findings += f"- `{error[:100]}`\n"
        await update_progress(agent_id, memory_node, "Console error check", 95, error_findings)
    else:
        await update_progress(agent_id, memory_node, "No console errors found", 95, "- **Console errors**: None")
    
    return True


async def validate_api_endpoint(browser: BrowserAutomation, url: str, agent_id: str, memory_node: str):
    """Validate specific API endpoint."""
    await update_progress(agent_id, memory_node, "Starting API endpoint validation", 10)
    
    # Visit page to trigger API calls
    result = await browser.visit(url)
    if not result["success"]:
        await update_progress(agent_id, memory_node, "Failed to load page", 0,
            f"**ERROR**: {result.get('error', 'Unknown')}")
        return False
    
    await update_progress(agent_id, memory_node, "Page loaded, monitoring API calls", 30)
    
    # Wait for API calls
    await asyncio.sleep(5)
    
    # Analyze API responses
    api_logs = [log for log in browser.network_logs if "/api/" in log["url"]]
    
    findings = f"### API Monitoring Results\n- **API calls intercepted**: {len(api_logs)}\n"
    
    if api_logs:
        # Check for common issues
        error_responses = [log for log in api_logs if log.get("status", 200) >= 400]
        slow_responses = [log for log in api_logs if False]  # Would need timing data
        
        findings += f"- **Error responses**: {len(error_responses)}\n"
        
        for log in error_responses[:5]:
            findings += f"  - {log['status']}: {log['url'][:60]}\n"
    
    await update_progress(agent_id, memory_node, "API validation complete", 90, findings)
    
    return True


async def run_agent(agent_id: str, memory_node: str):
    """Main agent execution loop."""
    print(f"[DATA VALIDATOR {agent_id}] Starting...")
    
    # Read objective from memory node
    try:
        node = vault.read_node(memory_node)
        objective = node["frontmatter"].get("objective", "")
        print(f"[DATA VALIDATOR {agent_id}] Objective: {objective[:100]}...")
    except Exception as e:
        print(f"[DATA VALIDATOR {agent_id}] ERROR reading memory node: {e}")
        return
    
    # Update status to active
    await update_progress(agent_id, memory_node, "Launching browser", 0)
    
    # Start browser
    headless = os.getenv("HEADLESS", "true").lower() == "true"
    browser = BrowserAutomation(headless=headless)
    
    try:
        await browser.start()
        print(f"[DATA VALIDATOR {agent_id}] Browser started (headless={headless})")
        
        # Parse URL from objective
        url = None
        if "http" in objective:
            words = objective.split()
            for word in words:
                if word.startswith("http"):
                    url = word.strip("./,;")
                    break
        
        if not url:
            await update_progress(agent_id, memory_node, "No URL found in objective", 0,
                "**ERROR**: Could not extract URL from objective. Please include a valid URL.")
            return
        
        # Determine test type from objective
        objective_lower = objective.lower()
        
        if "endpoint" in objective_lower or "api" in objective_lower:
            success = await validate_api_endpoint(browser, url, agent_id, memory_node)
        else:
            # Default to API monitoring
            success = await monitor_api_calls(browser, url, agent_id, memory_node)
        
        # Complete
        if success:
            await update_progress(agent_id, memory_node, "Test complete", 100,
                "## ✅ Test Complete\n\nAll API validation checks finished successfully.")
            
            vault.update_frontmatter(memory_node, {
                "status": "completed",
                "result": "pass",
                "progress_percent": 100,
                "requests_intercepted": len(browser.network_logs),
                "end_time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z"
            })
            print(f"[DATA VALIDATOR {agent_id}] Test completed successfully")
        else:
            vault.update_frontmatter(memory_node, {
                "status": "failed",
                "result": "fail",
                "end_time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z"
            })
            print(f"[DATA VALIDATOR {agent_id}] Test failed")
            
    except Exception as e:
        print(f"[DATA VALIDATOR {agent_id}] CRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        
        vault.update_frontmatter(memory_node, {
            "status": "failed",
            "result": "fail",
            "error": str(e),
            "end_time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z"
        })
    finally:
        await browser.close()
        print(f"[DATA VALIDATOR {agent_id}] Browser closed")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python worker.py <agent_id> <memory_node_path>")
        sys.exit(1)
    
    agent_id = sys.argv[1]
    memory_node = sys.argv[2]
    
    asyncio.run(run_agent(agent_id, memory_node))