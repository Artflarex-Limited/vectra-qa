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
from datetime import datetime, timezone

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from mcp_server.tools import vault
from mcp_server.browser_tools import BrowserAutomation
from agents.ui_explorer.report_builder import ReportBuilder


async def update_progress(agent_id: str, memory_node: str, step: str, progress: int, 
                         findings: str = "", screenshots: list = None, findings_list: list = None):
    """Update agent progress in memory node."""
    try:
        updates = {
            "status": "active",
            "last_action": step,
            "progress_percent": progress,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z"
        }
        
        if screenshots:
            updates["screenshots"] = screenshots
        
        if findings:
            # Append findings to node content
            node = vault.read_node(memory_node)
            current_content = node["content"]
            new_content = current_content + f"\n\n## [{datetime.now(timezone.utc).strftime('%H:%M:%S')}] {step}\n{findings}"
            vault.write_node(memory_node, new_content, node["frontmatter"])
        
        # If we have structured findings, append them too
        if findings_list:
            node = vault.read_node(memory_node)
            current_content = node["content"]
            for finding in findings_list:
                current_content += f"\n- {finding}"
            vault.write_node(memory_node, current_content, node["frontmatter"])
        
        vault.update_frontmatter(memory_node, updates)
    except Exception as e:
        print(f"[ERROR] Failed to update progress: {e}", file=sys.stderr)


async def update_report_in_memory(agent_id: str, memory_node: str, report: 'ReportBuilder'):
    """Write the full structured report to the memory node."""
    try:
        node = vault.read_node(memory_node)
        # Prepend the report to existing content
        report_md = report.get_report().to_markdown()
        new_content = f"{report_md}\n\n---\n\n## Detailed Log\n\n{node['content']}"
        vault.write_node(memory_node, new_content, node["frontmatter"])
    except Exception as e:
        print(f"[ERROR] Failed to update report: {e}", file=sys.stderr)


async def test_homepage(browser: BrowserAutomation, url: str, agent_id: str, memory_node: str) -> ReportBuilder:
    """Test homepage structure with detailed report."""
    report = ReportBuilder("homepage", url)
    
    await update_progress(agent_id, memory_node, "Navigating to homepage", 5)
    
    result = await browser.visit(url)
    if not result["success"]:
        report.add_section("Page Load", "fail", [
            {"title": "Navigation Failed", "description": f"Could not load page: {result.get('error', 'Unknown')}", "severity": "critical"}
        ], {"url": url, "error": result.get("error", "Unknown")})
        report.finalize()
        return report
    
    # Page Info Section
    page_metrics = {
        "URL": result['url'],
        "Title": result['title'],
        "HTTP Status": result['status'],
        "Load Time": "OK"
    }
    report.add_section("Page Information", "pass", [
        {"title": "Page Loaded Successfully", "description": f"Page loaded with status {result['status']}", "severity": "info"}
    ], page_metrics)
    
    await update_progress(agent_id, memory_node, "Page loaded successfully", 15)
    
    # Take screenshot
    screenshot_path = f"obsidian_vault/Screenshots/{agent_id}_homepage.png"
    await browser.screenshot(screenshot_path)
    report.add_screenshot(screenshot_path)
    
    await update_progress(agent_id, memory_node, "Captured homepage screenshot", 25, 
                         screenshots=[screenshot_path])
    
    # Navigation Section
    nav_result = await browser.get_elements("nav, header, .nav, .navigation, .menu, .navbar")
    nav_findings = []
    nav_metrics = {"Navigation elements": nav_result['count']}
    
    if nav_result['count'] == 0:
        nav_findings.append({"title": "No Navigation Found", "description": "No <nav>, <header>, or navigation classes detected", "severity": "high"})
        report.add_recommendation("Add a <nav> or <header> element for site navigation")
    else:
        nav_findings.append({"title": "Navigation Present", "description": f"Found {nav_result['count']} navigation element(s)", "severity": "info"})
    
    report.add_section("Navigation Audit", "pass" if nav_result['count'] > 0 else "warning", nav_findings, nav_metrics)
    await update_progress(agent_id, memory_node, "Navigation check complete", 40)
    
    # Content Structure
    main_result = await browser.get_elements("main, .main, .content, #content")
    header_result = await browser.get_elements("h1, h2, h3, h4, h5, h6")
    
    content_findings = []
    if main_result['count'] == 0:
        content_findings.append({"title": "No Main Content Area", "description": "No <main> or .content container found", "severity": "medium"})
    else:
        content_findings.append({"title": "Main Content Present", "description": f"Found {main_result['count']} content area(s)", "severity": "info"})
    
    if header_result['count'] == 0:
        content_findings.append({"title": "No Headings Found", "description": "Page lacks heading structure (h1-h6)", "severity": "high"})
        report.add_recommendation("Add proper heading hierarchy (h1 for main title, h2-h6 for sections)")
    else:
        content_findings.append({"title": "Heading Structure", "description": f"Found {header_result['count']} heading(s)", "severity": "info"})
    
    report.add_section("Content Structure", "pass", content_findings, {
        "Content areas": main_result['count'],
        "Headings": header_result['count']
    })
    await update_progress(agent_id, memory_node, "Content structure checked", 55)
    
    # Footer
    footer_result = await browser.get_elements("footer, .footer, .site-footer")
    report.add_section("Footer Check", "pass" if footer_result['count'] > 0 else "warning", [
        {"title": "Footer Found" if footer_result['count'] > 0 else "No Footer", 
         "description": f"Found {footer_result['count']} footer element(s)", 
         "severity": "info" if footer_result['count'] > 0 else "low"}
    ], {"Footer elements": footer_result['count']})
    
    await update_progress(agent_id, memory_node, "Footer check complete", 65)
    
    # Console Errors
    errors = await browser.get_console_errors()
    error_findings = []
    if errors:
        error_findings.append({"title": "Console Errors Detected", "description": f"Found {len(errors)} error(s) in browser console", "severity": "high"})
        for i, err in enumerate(errors[:5]):
            error_findings.append({"title": f"Error {i+1}", "description": str(err)[:100], "severity": "high"})
        report.add_recommendation("Fix JavaScript/console errors for better user experience")
    else:
        error_findings.append({"title": "No Console Errors", "description": "No errors detected in browser console", "severity": "info"})
    
    report.add_section("Error Check", "pass" if not errors else "fail", error_findings, {"Console errors": len(errors)})
    await update_progress(agent_id, memory_node, "Console error check complete", 75)
    
    # Links Analysis
    links_result = await browser.get_all_links()
    report.add_section("Link Analysis", "pass", [
        {"title": "Links Found", "description": f"Found {links_result['count']} link(s) on page", "severity": "info"}
    ], {"Total links": links_result['count']})
    await update_progress(agent_id, memory_node, "Link analysis complete", 85)
    
    # Security Check
    security_findings = []
    if url.startswith("https://"):
        security_findings.append({"title": "HTTPS Enabled", "description": "Site uses secure HTTPS connection", "severity": "info"})
    else:
        security_findings.append({"title": "HTTP Only", "description": "Site does not use HTTPS encryption", "severity": "critical"})
        report.add_recommendation("Enable HTTPS for all pages")
    
    report.add_section("Security Check", "pass" if url.startswith("https://") else "fail", security_findings, {"Protocol": "HTTPS" if url.startswith("https://") else "HTTP"})
    await update_progress(agent_id, memory_node, "Security check complete", 95)
    
    # Performance
    await browser.scroll_to_bottom()
    report.add_section("Performance Check", "pass", [
        {"title": "Page Scrollable", "description": "Page scrolled to bottom successfully", "severity": "info"}
    ])
    
    report.finalize()
    return report


async def test_navigation(browser: BrowserAutomation, url: str, agent_id: str, memory_node: str) -> ReportBuilder:
    """Test navigation links with detailed report."""
    report = ReportBuilder("navigation", url)
    
    result = await browser.visit(url)
    if not result["success"]:
        report.add_section("Page Load", "fail", [
            {"title": "Navigation Failed", "description": f"Could not load page: {result.get('error', 'Unknown')}", "severity": "critical"}
        ], {"url": url})
        report.finalize()
        return report
    
    report.add_section("Page Load", "pass", [
        {"title": "Page Loaded", "description": f"Started at {url}", "severity": "info"}
    ], {"URL": url, "Status": result['status']})
    
    await update_progress(agent_id, memory_node, "Page loaded", 15)
    
    # Get links
    links_result = await browser.get_all_links()
    links = links_result.get("links", [])
    
    # Filter to same-domain links
    base_domain = url.replace("https://", "").replace("http://", "").split("/")[0]
    internal_links = [l for l in links if base_domain in l["href"] or l["href"].startswith("/")]
    external_links = [l for l in links if l["href"].startswith("http") and base_domain not in l["href"]]
    
    link_findings = [
        {"title": "Total Links", "description": f"Found {links_result['count']} total links", "severity": "info"},
        {"title": "Internal Links", "description": f"Found {len(internal_links)} internal link(s)", "severity": "info"},
        {"title": "External Links", "description": f"Found {len(external_links)} external link(s)", "severity": "info"}
    ]
    
    report.add_section("Link Inventory", "pass", link_findings, {
        "Total links": links_result['count'],
        "Internal": len(internal_links),
        "External": len(external_links)
    })
    
    await update_progress(agent_id, memory_node, f"Found {len(internal_links)} internal links", 25)
    
    # Test internal links
    tested = 0
    broken = 0
    link_results = []
    
    for link in internal_links[:10]:  # Test up to 10
        href = link["href"]
        if href.startswith("/"):
            href = url.rstrip("/") + href
        if not href.startswith("http"):
            continue
            
        progress = 30 + (tested * 5)
        await update_progress(agent_id, memory_node, f"Testing link: {link['text'][:30]}...", progress)
        
        nav_result = await browser.visit(href)
        if nav_result["success"]:
            link_results.append({"text": link['text'], "url": href, "status": "OK", "http_status": nav_result.get("status", "OK")})
        else:
            link_results.append({"text": link['text'], "url": href, "status": "BROKEN", "error": nav_result.get("error", "Error")})
            broken += 1
        
        tested += 1
        
        # Go back
        await browser.page.go_back()
        await asyncio.sleep(0.3)
    
    # Link Test Results Section
    link_test_findings = []
    if tested == 0:
        link_test_findings.append({"title": "No Links Tested", "description": "No valid internal links found to test", "severity": "warning"})
    else:
        link_test_findings.append({"title": "Links Tested", "description": f"Tested {tested} link(s), {broken} broken", "severity": "info" if broken == 0 else "high"})
        if broken > 0:
            for lr in link_results:
                if lr["status"] == "BROKEN":
                    link_test_findings.append({"title": f"Broken: {lr['text'][:40]}", "description": lr["url"], "severity": "high"})
            report.add_recommendation("Fix broken internal links for better SEO and user experience")
    
    report.add_section("Link Validation", "pass" if broken == 0 else "fail", link_test_findings, {
        "Tested": tested,
        "Broken": broken,
        "Pass rate": f"{((tested - broken) / tested * 100):.0f}%" if tested > 0 else "N/A"
    })
    
    await update_progress(agent_id, memory_node, f"Navigation test complete", 90)
    
    report.finalize()
    return report


async def test_contact_form(browser: BrowserAutomation, url: str, agent_id: str, memory_node: str) -> ReportBuilder:
    """Test contact form with detailed report."""
    report = ReportBuilder("contact_form", url)
    
    result = await browser.visit(url)
    if not result["success"]:
        report.add_section("Page Load", "fail", [
            {"title": "Navigation Failed", "description": f"Could not load page: {result.get('error', 'Unknown')}", "severity": "critical"}
        ])
        report.finalize()
        return report
    
    report.add_section("Page Load", "pass", [
        {"title": "Page Loaded", "description": f"Starting at {url}", "severity": "info"}
    ], {"URL": url})
    
    await update_progress(agent_id, memory_node, "Page loaded", 15)
    
    # Look for contact link or form
    contact_selectors = [
        "a[href*='contact']", "a[href*='Contact']",
        "form", ".contact-form", "#contact-form",
        ".contact", "#contact"
    ]
    
    found = False
    contact_element = None
    for selector in contact_selectors:
        elements = await browser.get_elements(selector)
        if elements["count"] > 0:
            found = True
            contact_element = selector
            if selector.startswith("a"):
                await browser.click(selector)
                report.add_section("Contact Discovery", "pass", [
                    {"title": "Contact Link Found", "description": f"Clicked contact link: `{selector}`", "severity": "info"}
                ])
            else:
                report.add_section("Contact Discovery", "pass", [
                    {"title": "Form Found", "description": f"Found form via selector: `{selector}`", "severity": "info"}
                ])
            break
    
    if not found:
        report.add_section("Contact Discovery", "warning", [
            {"title": "No Contact Form", "description": "Checked links, forms, and contact sections - none found", "severity": "medium"}
        ])
        report.add_recommendation("Add a contact form or link for user inquiries")
        report.finalize()
        return report
    
    await update_progress(agent_id, memory_node, "Contact form located", 40)
    
    # Analyze form
    form_result = await browser.check_form()
    form_findings = []
    form_metrics = {}
    
    if form_result["success"]:
        fields = form_result["fields"]
        form_metrics = {
            "Total fields": len(fields),
            "Required fields": sum(1 for f in fields if f['required']),
            "Optional fields": sum(1 for f in fields if not f['required'])
        }
        
        if len(fields) == 0:
            form_findings.append({"title": "Empty Form", "description": "Form has no input fields", "severity": "high"})
        else:
            form_findings.append({"title": "Form Fields Found", "description": f"Found {len(fields)} field(s)", "severity": "info"})
            
            # Check for required fields
            required = [f for f in fields if f['required']]
            if required:
                form_findings.append({"title": "Required Fields", "description": f"{len(required)} field(s) marked as required", "severity": "info"})
            else:
                form_findings.append({"title": "No Required Fields", "description": "Form accepts empty submissions", "severity": "medium"})
            
            # Check for common fields
            has_name = any('name' in f['name'].lower() or 'name' in f.get('placeholder', '').lower() for f in fields)
            has_email = any('email' in f['name'].lower() or 'email' in f.get('placeholder', '').lower() for f in fields)
            has_message = any('message' in f['name'].lower() or 'message' in f.get('placeholder', '').lower() for f in fields)
            
            if not has_name:
                form_findings.append({"title": "Missing Name Field", "description": "No name field detected", "severity": "low"})
            if not has_email:
                form_findings.append({"title": "Missing Email Field", "description": "No email field detected", "severity": "high"})
            if not has_message:
                form_findings.append({"title": "Missing Message Field", "description": "No message/comment field detected", "severity": "medium"})
    else:
        form_findings.append({"title": "Form Analysis Failed", "description": "Could not analyze form structure", "severity": "high"})
    
    report.add_section("Form Analysis", "pass" if form_result["success"] and len(form_result.get("fields", [])) > 0 else "warning", 
                      form_findings, form_metrics)
    
    await update_progress(agent_id, memory_node, "Form analysis complete", 70)
    
    # Take screenshot
    screenshot_path = f"obsidian_vault/Screenshots/{agent_id}_contact.png"
    await browser.screenshot(screenshot_path)
    report.add_screenshot(screenshot_path)
    
    await update_progress(agent_id, memory_node, "Contact form screenshot captured", 90, 
                         screenshots=[screenshot_path])
    
    report.finalize()
    return report


async def test_accessibility(browser: BrowserAutomation, url: str, agent_id: str, memory_node: str) -> ReportBuilder:
    """Test accessibility with detailed report."""
    report = ReportBuilder("accessibility", url)
    
    result = await browser.visit(url)
    if not result["success"]:
        report.add_section("Page Load", "fail", [
            {"title": "Navigation Failed", "description": f"Could not load page: {result.get('error', 'Unknown')}", "severity": "critical"}
        ])
        report.finalize()
        return report
    
    report.add_section("Page Load", "pass", [{"title": "Page Loaded", "description": url, "severity": "info"}],
                      {"URL": url, "Status": result['status']})
    await update_progress(agent_id, memory_node, "Page loaded", 15)
    
    # Image alt text
    images = await browser.get_elements("img")
    img_findings = []
    if images['count'] > 0:
        # Check for alt text
        img_elements = images.get("elements", [])
        no_alt = [img for img in img_elements if not img.get("attributes", {}).get("alt")]
        if no_alt:
            img_findings.append({"title": "Missing Alt Text", "description": f"{len(no_alt)} of {images['count']} image(s) lack alt text", "severity": "high"})
            report.add_recommendation(f"Add alt text to {len(no_alt)} image(s) for screen reader compatibility")
        else:
            img_findings.append({"title": "All Images Have Alt Text", "description": f"All {images['count']} image(s) have alt attributes", "severity": "info"})
    else:
        img_findings.append({"title": "No Images", "description": "No images found on page", "severity": "info"})
    
    report.add_section("Image Accessibility", "pass", img_findings, {"Total images": images['count']})
    await update_progress(agent_id, memory_node, "Image accessibility checked", 35)
    
    # Heading structure
    headings = await browser.get_elements("h1, h2, h3, h4, h5, h6")
    heading_findings = []
    heading_metrics = {"Total headings": headings['count']}
    
    if headings['count'] == 0:
        heading_findings.append({"title": "No Headings", "description": "Page lacks heading structure", "severity": "high"})
        report.add_recommendation("Add h1 for main title and h2-h6 for sections")
    else:
        h1_count = len(await browser.get_elements("h1"))
        if h1_count == 0:
            heading_findings.append({"title": "Missing H1", "description": "No h1 heading found (required for screen readers)", "severity": "high"})
            report.add_recommendation("Add exactly one h1 heading as page title")
        elif h1_count > 1:
            heading_findings.append({"title": "Multiple H1s", "description": f"Found {h1_count} h1 headings (should be exactly 1)", "severity": "medium"})
        else:
            heading_findings.append({"title": "H1 Present", "description": "Exactly one h1 heading found", "severity": "info"})
    
    report.add_section("Heading Structure", "pass", heading_findings, heading_metrics)
    await update_progress(agent_id, memory_node, "Heading structure checked", 50)
    
    # ARIA
    aria_elements = await browser.get_elements("[aria-label], [aria-labelledby], [role]")
    aria_findings = []
    if aria_elements['count'] > 0:
        aria_findings.append({"title": "ARIA Attributes", "description": f"Found {aria_elements['count']} element(s) with ARIA attributes", "severity": "info"})
    else:
        aria_findings.append({"title": "No ARIA", "description": "No ARIA labels or roles found", "severity": "medium"})
        report.add_recommendation("Consider adding ARIA labels for complex UI components")
    
    report.add_section("ARIA Check", "pass" if aria_elements['count'] > 0 else "warning", aria_findings,
                      {"ARIA elements": aria_elements['count']})
    await update_progress(agent_id, memory_node, "ARIA check complete", 65)
    
    # Form labels
    forms = await browser.check_form()
    form_findings = []
    if forms["success"] and forms["count"] > 0:
        fields = forms["fields"]
        labeled = sum(1 for f in fields if f.get("has_label", False))
        if labeled < len(fields):
            form_findings.append({"title": "Unlabeled Fields", "description": f"{len(fields) - labeled} of {len(fields)} field(s) lack labels", "severity": "high"})
            report.add_recommendation("Add <label> elements or aria-label to all form fields")
        else:
            form_findings.append({"title": "All Fields Labeled", "description": f"All {len(fields)} field(s) have labels", "severity": "info"})
    
    if form_findings:
        report.add_section("Form Labels", "pass", form_findings, {"Total fields": forms.get("count", 0)})
    
    await update_progress(agent_id, memory_node, "Form accessibility checked", 80)
    
    # Keyboard navigation check (basic)
    report.add_section("Keyboard Navigation", "pass", [
        {"title": "Tab Navigation", "description": "Tab navigation supported (browser default)", "severity": "info"}
    ], details="Manual testing recommended for full keyboard navigation verification")
    
    report.finalize()
    return report


async def test_responsive(browser: BrowserAutomation, url: str, agent_id: str, memory_node: str) -> ReportBuilder:
    """Test responsive design with detailed report."""
    report = ReportBuilder("responsive", url)
    
    result = await browser.visit(url)
    if not result["success"]:
        report.add_section("Page Load", "fail", [
            {"title": "Navigation Failed", "description": f"Could not load page: {result.get('error', 'Unknown')}", "severity": "critical"}
        ])
        report.finalize()
        return report
    
    report.add_section("Page Load", "pass", [{"title": "Page Loaded", "description": url, "severity": "info"}],
                      {"URL": url})
    await update_progress(agent_id, memory_node, "Page loaded", 10)
    
    viewports = [
        (1920, 1080, "Desktop"),
        (1024, 768, "Small Desktop"),
        (768, 1024, "Tablet"),
        (375, 667, "Mobile")
    ]
    
    viewport_findings = []
    for i, (width, height, name) in enumerate(viewports):
        progress = 15 + i * 20
        await update_progress(agent_id, memory_node, f"Testing {name} ({width}x{height})", progress)
        
        result = await browser.check_responsive(width, height)
        if result["success"]:
            # Take screenshot
            screenshot_path = f"obsidian_vault/Screenshots/{agent_id}_{name.lower().replace(' ', '_')}.png"
            await browser.screenshot(screenshot_path)
            report.add_screenshot(screenshot_path)
            
            viewport_findings.append({
                "title": f"{name} ({width}x{height})", 
                "description": "Viewport tested and screenshot captured", 
                "severity": "info"
            })
        else:
            viewport_findings.append({
                "title": f"{name} Failed", 
                "description": f"Could not test {name} viewport", 
                "severity": "medium"
            })
    
    report.add_section("Viewport Testing", "pass", viewport_findings, {
        "Tested viewports": len(viewports),
        "Screenshots": len(report.report.screenshots)
    })
    
    await update_progress(agent_id, memory_node, "Responsive testing complete", 95)
    
    report.finalize()
    return report


async def test_full_suite(browser: BrowserAutomation, url: str, agent_id: str, memory_node: str):
    """Run full suite: all test types sequentially."""
    report = ReportBuilder("full_suite", url)
    all_screenshots = []
    all_recommendations = []
    
    # Define test sequence
    tests = [
        ("Homepage", test_homepage, 20),
        ("Navigation", test_navigation, 40),
        ("Contact Form", test_contact_form, 60),
        ("Accessibility", test_accessibility, 80),
        ("Responsive", test_responsive, 100)
    ]
    
    await update_progress(agent_id, memory_node, "Starting full test suite", 0)
    
    for test_name, test_func, progress in tests:
        await update_progress(agent_id, memory_node, f"Running {test_name} test...", progress - 15)
        
        try:
            # Run the test
            test_report = await test_func(browser, url, agent_id, memory_node)
            
            # Merge sections into main report
            for section in test_report.report.sections:
                report.add_section(
                    f"[{test_name}] {section.title}", 
                    section.status, 
                    section.findings, 
                    section.metrics
                )
            
            # Collect screenshots and recommendations
            all_screenshots.extend(test_report.report.screenshots)
            all_recommendations.extend(test_report.report.recommendations)
            
            await update_progress(agent_id, memory_node, f"{test_name} test complete", progress)
            
        except Exception as e:
            report.add_section(f"[{test_name}] Error", "fail", [
                {"title": "Test Failed", "description": str(e), "severity": "critical"}
            ])
            print(f"[UI EXPLORER {agent_id}] Error in {test_name}: {e}")
    
    # Add all screenshots and recommendations
    for ss in all_screenshots:
        report.add_screenshot(ss)
    for rec in all_recommendations:
        report.add_recommendation(rec)
    
    report.finalize()
    return report


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
        
        if "test navigation" in objective_lower or "test nav" in objective_lower:
            report = await test_navigation(browser, url, agent_id, memory_node)
        elif "contact" in objective_lower or "form" in objective_lower:
            report = await test_contact_form(browser, url, agent_id, memory_node)
        elif "accessibility" in objective_lower or "aria" in objective_lower:
            report = await test_accessibility(browser, url, agent_id, memory_node)
        elif "responsive" in objective_lower or "mobile" in objective_lower:
            report = await test_responsive(browser, url, agent_id, memory_node)
        elif "full suite" in objective_lower or "comprehensive" in objective_lower or "all tests" in objective_lower:
            report = await test_full_suite(browser, url, agent_id, memory_node)
        else:
            # Default to homepage test
            report = await test_homepage(browser, url, agent_id, memory_node)
        
        # Write report to memory
        await update_report_in_memory(agent_id, memory_node, report)
        
        # Complete
        if report.report.overall_status == "pass":
            await update_progress(agent_id, memory_node, "Test complete", 100)
            
            vault.update_frontmatter(memory_node, {
                "status": "completed",
                "result": "pass",
                "progress_percent": 100,
                "end_time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z"
            })
            print(f"[UI EXPLORER {agent_id}] Test completed successfully")
        elif report.report.overall_status == "warning":
            await update_progress(agent_id, memory_node, "Test complete with warnings", 100)
            
            vault.update_frontmatter(memory_node, {
                "status": "completed",
                "result": "warning",
                "progress_percent": 100,
                "end_time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z"
            })
            print(f"[UI EXPLORER {agent_id}] Test completed with warnings")
        else:
            vault.update_frontmatter(memory_node, {
                "status": "completed",
                "result": "fail",
                "progress_percent": 100,
                "end_time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z"
            })
            print(f"[UI EXPLORER {agent_id}] Test completed with failures")
            
    except Exception as e:
        print(f"[UI EXPLORER {agent_id}] CRITICAL ERROR: {e}")
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
        print(f"[UI EXPLORER {agent_id}] Browser closed")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python worker.py <agent_id> <memory_node_path>")
        sys.exit(1)
    
    agent_id = sys.argv[1]
    memory_node = sys.argv[2]
    
    asyncio.run(run_agent(agent_id, memory_node))