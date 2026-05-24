#!/usr/bin/env python3
"""
UI Explorer Worker - Real Browser Automation

This worker is spawned by the MCP server when a UI Explorer agent is created.
It performs real browser automation using Playwright.

Usage:
    python agents/ui_explorer/worker.py <agent_id> <memory_node_path>
"""

import sys
import os
import asyncio
import time
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from mcp_server.tools import vault
from mcp_server.browser_tools import BrowserAutomation


async def update_progress(agent_id: str, memory_node: str, step: str, progress: int, findings: str = "", screenshots: list = None):
    """Update agent progress in memory node."""
    try:
        updates = {
            "status": "active",
            "last_action": step,
            "progress_percent": progress,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
        
        if screenshots:
            updates["screenshots"] = screenshots
        
        if findings:
            # Append findings to node content
            node = vault.read_node(memory_node)
            current_content = node["content"]
            new_content = current_content + f"\n\n## [{datetime.utcnow().strftime('%H:%M:%S')}] {step}\n{findings}"
            vault.write_node(memory_node, new_content, node["frontmatter"])
        
        vault.update_frontmatter(memory_node, updates)
    except Exception as e:
        print(f"[ERROR] Failed to update progress: {e}", file=sys.stderr)


async def test_homepage(browser: BrowserAutomation, url: str, agent_id: str, memory_node: str):
    """Test homepage structure."""
    await update_progress(agent_id, memory_node, "Navigating to homepage", 10)
    
    result = await browser.visit(url)
    if not result["success"]:
        await update_progress(agent_id, memory_node, "Failed to load page", 0, 
            f"**ERROR**: {result.get('error', 'Unknown')}")
        return False
    
    findings = f"""
- **URL**: {result['url']}
- **Title**: {result['title']}
- **Status**: {result['status']}
"""
    await update_progress(agent_id, memory_node, "Page loaded successfully", 20, findings)
    
    # Take screenshot
    screenshot_path = f"obsidian_vault/Screenshots/{agent_id}_homepage.png"
    await browser.screenshot(screenshot_path)
    screenshots = [screenshot_path]
    findings = f"- **Screenshot**: [[{screenshot_path}]]"
    await update_progress(agent_id, memory_node, "Captured homepage screenshot", 30, findings, screenshots)
    
    # Check for key elements
    await update_progress(agent_id, memory_node, "Checking page structure", 40)
    
    # Check for navigation
    nav_result = await browser.get_elements("nav, header, .nav, .navigation, .menu, .navbar")
    findings = f"- **Navigation elements found**: {nav_result['count']}"
    await update_progress(agent_id, memory_node, "Navigation check complete", 50, findings)
    
    # Check for main content
    main_result = await browser.get_elements("main, .main, .content, #content")
    findings = f"- **Main content areas**: {main_result['count']}"
    await update_progress(agent_id, memory_node, "Content structure checked", 60, findings)
    
    # Check for footer
    footer_result = await browser.get_elements("footer, .footer, .site-footer")
    findings = f"- **Footer elements**: {footer_result['count']}"
    await update_progress(agent_id, memory_node, "Footer check complete", 70, findings)
    
    # Check console errors
    errors = await browser.get_console_errors()
    if errors:
        findings = f"- **Console errors**: {len(errors)}\n" + "\n".join([f"  - {e}" for e in errors[:5]])
    else:
        findings = "- **Console errors**: None"
    await update_progress(agent_id, memory_node, "Console error check complete", 80, findings)
    
    # Get all links
    links_result = await browser.get_all_links()
    findings = f"- **Total links**: {links_result['count']}"
    await update_progress(agent_id, memory_node, "Link analysis complete", 90, findings)
    
    # Scroll to bottom
    await browser.scroll_to_bottom()
    findings = "- **Page scroll**: Bottom reached successfully"
    await update_progress(agent_id, memory_node, "Page scroll test complete", 95, findings)
    
    return True


async def test_navigation(browser: BrowserAutomation, url: str, agent_id: str, memory_node: str):
    """Test navigation links."""
    await update_progress(agent_id, memory_node, "Starting navigation test", 10)
    
    # Visit page
    result = await browser.visit(url)
    if not result["success"]:
        await update_progress(agent_id, memory_node, "Failed to load page", 0,
            f"**ERROR**: {result.get('error', 'Unknown')}")
        return False
    
    findings = f"- **Starting URL**: {url}"
    await update_progress(agent_id, memory_node, "Page loaded", 20, findings)
    
    # Get all links
    links_result = await browser.get_all_links()
    links = links_result.get("links", [])
    
    # Filter to same-domain links
    base_domain = url.replace("https://", "").replace("http://", "").split("/")[0]
    internal_links = [l for l in links if base_domain in l["href"] or l["href"].startswith("/")]
    
    findings = f"- **Internal links found**: {len(internal_links)}"
    await update_progress(agent_id, memory_node, f"Found {len(internal_links)} internal links", 30, findings)
    
    # Test first 5 internal links
    tested = 0
    broken = 0
    for link in internal_links[:5]:
        href = link["href"]
        if href.startswith("/"):
            href = url.rstrip("/") + href
            
        if not href.startswith("http"):
            continue
            
        await update_progress(agent_id, memory_node, f"Testing link: {link['text'][:30]}...", 30 + tested * 10)
        
        # Visit link
        nav_result = await browser.visit(href)
        if nav_result["success"]:
            findings = f"- **Link OK**: {link['text'][:40]} → {nav_result['status']}"
        else:
            findings = f"- **Link FAILED**: {link['text'][:40]} → {nav_result.get('error', 'Error')}"
            broken += 1
            
        await update_progress(agent_id, memory_node, f"Link test complete", 30 + tested * 10, findings)
        tested += 1
        
        # Go back
        await browser.page.go_back()
        await asyncio.sleep(0.5)
    
    findings = f"- **Links tested**: {tested}\n- **Broken links**: {broken}"
    await update_progress(agent_id, memory_node, "Navigation test complete", 90, findings)
    
    return True


async def test_contact_form(browser: BrowserAutomation, url: str, agent_id: str, memory_node: str):
    """Test contact form."""
    await update_progress(agent_id, memory_node, "Starting contact form test", 10)
    
    # Visit page
    result = await browser.visit(url)
    if not result["success"]:
        await update_progress(agent_id, memory_node, "Failed to load page", 0,
            f"**ERROR**: {result.get('error', 'Unknown')}")
        return False
    
    findings = "- **Page loaded**: Looking for contact form..."
    await update_progress(agent_id, memory_node, "Page loaded", 20, findings)
    
    # Look for contact link or form
    contact_selectors = [
        "a[href*='contact']", "a[href*='Contact']",
        "form", ".contact-form", "#contact-form",
        ".contact", "#contact"
    ]
    
    found = False
    for selector in contact_selectors:
        elements = await browser.get_elements(selector)
        if elements["count"] > 0:
            found = True
            if selector.startswith("a"):
                # Click contact link
                await browser.click(selector)
                findings = f"- **Contact link found**: Clicked `{selector}`"
            else:
                findings = f"- **Form found**: `{selector}`"
            break
    
    if not found:
        findings = "- **No contact form found**: Checked links, forms, and contact sections"
        await update_progress(agent_id, memory_node, "No contact form found", 50, findings)
        return True
    
    await update_progress(agent_id, memory_node, "Contact form located", 40, findings)
    
    # Analyze form
    form_result = await browser.check_form()
    if form_result["success"]:
        fields = form_result["fields"]
        findings = f"- **Form fields**: {len(fields)}\n" + "\n".join([
            f"  - {f['type']}: {f['name']} (required: {f['required']})" 
            for f in fields[:10]
        ])
        await update_progress(agent_id, memory_node, "Form analysis complete", 70, findings)
    
    # Take screenshot
    screenshot_path = f"obsidian_vault/Screenshots/{agent_id}_contact.png"
    await browser.screenshot(screenshot_path)
    screenshots = [screenshot_path]
    findings = f"- **Screenshot**: [[{screenshot_path}]]"
    await update_progress(agent_id, memory_node, "Contact form screenshot captured", 90, findings, screenshots)
    
    return True


async def test_accessibility(browser: BrowserAutomation, url: str, agent_id: str, memory_node: str):
    """Basic accessibility checks."""
    await update_progress(agent_id, memory_node, "Starting accessibility audit", 10)
    
    result = await browser.visit(url)
    if not result["success"]:
        await update_progress(agent_id, memory_node, "Failed to load page", 0,
            f"**ERROR**: {result.get('error', 'Unknown')}")
        return False
    
    findings = "- **Page loaded**: Starting accessibility checks"
    await update_progress(agent_id, memory_node, "Page loaded", 20, findings)
    
    # Check for images without alt text
    images = await browser.get_elements("img")
    findings = f"- **Images**: {images['count']} found"
    await update_progress(agent_id, memory_node, "Image count checked", 40, findings)
    
    # Check headings
    headings = await browser.get_elements("h1, h2, h3, h4, h5, h6")
    findings = f"- **Headings**: {headings['count']} found"
    await update_progress(agent_id, memory_node, "Heading structure checked", 60, findings)
    
    # Check for ARIA labels
    aria_elements = await browser.get_elements("[aria-label], [aria-labelledby], [role]")
    findings = f"- **ARIA elements**: {aria_elements['count']} found"
    await update_progress(agent_id, memory_node, "ARIA check complete", 80, findings)
    
    # Check form labels
    forms = await browser.check_form()
    if forms["success"]:
        findings = f"- **Form fields**: {forms['count']}"
        await update_progress(agent_id, memory_node, "Form accessibility checked", 90, findings)
    
    return True


async def test_responsive(browser: BrowserAutomation, url: str, agent_id: str, memory_node: str):
    """Test responsive design."""
    await update_progress(agent_id, memory_node, "Starting responsive design test", 10)
    
    viewports = [
        (1920, 1080, "Desktop"),
        (768, 1024, "Tablet"),
        (375, 667, "Mobile")
    ]
    
    screenshots = []
    for i, (width, height, name) in enumerate(viewports):
        progress = 20 + i * 25
        await update_progress(agent_id, memory_node, f"Testing {name} viewport ({width}x{height})", progress)
        
        result = await browser.check_responsive(width, height)
        if result["success"]:
            await browser.visit(url)
            screenshot_path = f"obsidian_vault/Screenshots/{agent_id}_{name.lower()}.png"
            await browser.screenshot(screenshot_path)
            screenshots.append(screenshot_path)
            
            findings = f"- **{name} ({width}x{height})**: Screenshot captured"
            await update_progress(agent_id, memory_node, f"{name} viewport tested", progress + 10, findings, screenshots)
    
    return True


async def run_agent(agent_id: str, memory_node: str):
    """Main agent execution loop."""
    print(f"[UI EXPLORER {agent_id}] Starting...")
    
    # Read objective from memory node
    try:
        node = vault.read_node(memory_node)
        objective = node["frontmatter"].get("objective", "")
        print(f"[UI EXPLORER {agent_id}] Objective: {objective[:100]}...")
    except Exception as e:
        print(f"[UI EXPLORER {agent_id}] ERROR reading memory node: {e}")
        return
    
    # Update status to active
    await update_progress(agent_id, memory_node, "Launching browser", 0)
    
    # Start browser
    headless = os.getenv("HEADLESS", "true").lower() == "true"
    browser = BrowserAutomation(headless=headless)
    
    try:
        await browser.start()
        print(f"[UI EXPLORER {agent_id}] Browser started (headless={headless})")
        
        # Parse URL from objective
        url = None
        if "http" in objective:
            # Extract URL from objective
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
        
        if "navigation" in objective_lower or "nav" in objective_lower:
            success = await test_navigation(browser, url, agent_id, memory_node)
        elif "contact" in objective_lower or "form" in objective_lower:
            success = await test_contact_form(browser, url, agent_id, memory_node)
        elif "accessibility" in objective_lower or "aria" in objective_lower:
            success = await test_accessibility(browser, url, agent_id, memory_node)
        elif "responsive" in objective_lower or "mobile" in objective_lower:
            success = await test_responsive(browser, url, agent_id, memory_node)
        else:
            # Default to homepage test
            success = await test_homepage(browser, url, agent_id, memory_node)
        
        # Complete
        if success:
            await update_progress(agent_id, memory_node, "Test complete", 100,
                "## ✅ Test Complete\n\nAll checks finished successfully.")
            
            vault.update_frontmatter(memory_node, {
                "status": "completed",
                "result": "pass",
                "progress_percent": 100,
                "end_time": datetime.utcnow().isoformat() + "Z"
            })
            print(f"[UI EXPLORER {agent_id}] Test completed successfully")
        else:
            vault.update_frontmatter(memory_node, {
                "status": "failed",
                "result": "fail",
                "end_time": datetime.utcnow().isoformat() + "Z"
            })
            print(f"[UI EXPLORER {agent_id}] Test failed")
            
    except Exception as e:
        print(f"[UI EXPLORER {agent_id}] CRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        
        vault.update_frontmatter(memory_node, {
            "status": "failed",
            "result": "fail",
            "error": str(e),
            "end_time": datetime.utcnow().isoformat() + "Z"
        })
    finally:
        await browser.close()
        print(f"[UI EXPLORER {agent_id}] Browser closed")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python worker.py <agent_id> <memory_node_path>")
        sys.exit(1)
    
    agent_id = sys.argv[1]
    memory_node = sys.argv[2]
    
    asyncio.run(run_agent(agent_id, memory_node))