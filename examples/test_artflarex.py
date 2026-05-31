#!/usr/bin/env python3
"""
Test Scenario: Artflarex Solutions Website
URL: https://www.artflarex.com/

Tests comprehensive E2E validation including:
- Homepage structure and content
- Navigation flow across all pages
- Contact form functionality
- Service pages content
- Mobile responsiveness
- Performance checks
- SEO meta tags
- Accessibility

Usage:
    python examples/test_artflarex.py
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp_server.tools import execute_tool

# Configuration
TARGET_URL = "https://www.artflarex.com/"
APP_NAME = "Artflarex Solutions"


def test_homepage():
    """Test homepage structure, content, and first impressions."""
    print("\n🏠 Testing Homepage...")

    result = execute_tool(
        "spawn_agent",
        {
            "role": "ui_explorer",
            "objective": (
                f"Test the homepage at {TARGET_URL}. "
                "Perform these comprehensive checks: "
                "1. Verify page loads without errors (check console). "
                "2. Identify and verify main headline/hero section. "
                "3. Check company logo is visible and clickable. "
                "4. Verify navigation menu items (Home, Services, About, Contact, etc.). "
                "5. Check for call-to-action buttons (CTAs). "
                "6. Verify footer contains company info, links, copyright. "
                "7. Check for loading states or skeleton screens. "
                "8. Verify images load correctly (no broken images). "
                "9. Test scroll behavior (smooth scroll, sticky header). "
                "10. Check for any console errors or warnings."
            ),
            "memory_node": "Runs/Artflarex_Homepage_Test.md",
        },
    )

    if result["status"] == "success":
        print(f"  UI Explorer: {result['result']['agent_id']}")
        return [result["result"]["agent_id"]]
    else:
        print(f"  ✗ Error: {result.get('error', 'Unknown error')}")
        return []


def test_navigation():
    """Test all navigation links and page transitions."""
    print("\n🧭 Testing Navigation...")

    result = execute_tool(
        "spawn_agent",
        {
            "role": "ui_explorer",
            "objective": (
                f"Test navigation across {TARGET_URL}. "
                "Perform these checks: "
                "1. Click each navigation menu item. "
                "2. Verify each page loads successfully (no 404s). "
                "3. Check page titles update correctly. "
                "4. Test browser back/forward buttons work. "
                "5. Verify active state on current menu item. "
                "6. Check for dropdown menus if present. "
                "7. Test mobile hamburger menu if present (resize to 375px). "
                "8. Verify external links open in new tab. "
                "9. Check for broken links. "
                "10. Test footer navigation links."
            ),
            "memory_node": "Runs/Artflarex_Navigation_Test.md",
        },
    )

    if result["status"] == "success":
        print(f"  UI Explorer: {result['result']['agent_id']}")
        return [result["result"]["agent_id"]]
    else:
        print(f"  ✗ Error: {result.get('error', 'Unknown error')}")
        return []


def test_services_pages():
    """Test services/offerings pages."""
    print("\n💼 Testing Services Pages...")

    result = execute_tool(
        "spawn_agent",
        {
            "role": "ui_explorer",
            "objective": (
                f"Test services pages on {TARGET_URL}. "
                "Perform these checks: "
                "1. Navigate to Services or Solutions page. "
                "2. Verify service cards/items are displayed. "
                "3. Check each service has title, description, icon/image. "
                "4. Test clicking on service items (if clickable). "
                "5. Verify detailed service pages load (if applicable). "
                "6. Check for pricing information (if present). "
                "7. Verify CTA buttons on service pages. "
                "8. Test filtering or categorization (if present). "
                "9. Check for testimonials or case studies. "
                "10. Verify content is readable and well-formatted."
            ),
            "memory_node": "Runs/Artflarex_Services_Test.md",
        },
    )

    if result["status"] == "success":
        print(f"  UI Explorer: {result['result']['agent_id']}")
        return [result["result"]["agent_id"]]
    else:
        print(f"  ✗ Error: {result.get('error', 'Unknown error')}")
        return []


def test_contact_form():
    """Test contact form functionality."""
    print("\n📧 Testing Contact Form...")

    # UI Explorer tests the form
    ui_result = execute_tool(
        "spawn_agent",
        {
            "role": "ui_explorer",
            "objective": (
                f"Test contact form on {TARGET_URL}. "
                "Perform these checks: "
                "1. Navigate to Contact page. "
                "2. Verify form fields: name, email, subject, message. "
                "3. Test form validation: submit empty form. "
                "4. Test invalid email format. "
                "5. Fill form with test data (use fake data). "
                "6. Submit form and verify success message. "
                "7. Check for spam protection (CAPTCHA, honeypot). "
                "8. Verify contact information (address, phone, email) is displayed. "
                "9. Test social media links. "
                "10. Check form accessibility (labels, focus, ARIA)."
            ),
            "memory_node": "Runs/Artflarex_Contact_UI_Test.md",
        },
    )

    if ui_result["status"] == "success":
        print(f"  UI Explorer: {ui_result['result']['agent_id']}")
        ui_id = ui_result["result"]["agent_id"]
    else:
        print(f"  ✗ UI Error: {ui_result.get('error', 'Unknown')}")
        ui_id = None

    time.sleep(3)

    # Data Validator monitors form submission
    api_result = execute_tool(
        "spawn_agent",
        {
            "role": "data_validator",
            "objective": (
                f"Monitor contact form API on {TARGET_URL}. "
                "Perform these checks: "
                "1. Intercept form submission requests. "
                "2. Verify request method (POST) and endpoint. "
                "3. Check request payload contains form data. "
                "4. Verify response status (200 success, 400 validation error). "
                "5. Check response time (< 3 seconds). "
                "6. Verify CORS headers if applicable. "
                "7. Check for CSRF tokens. "
                "8. Verify no sensitive data leaks in response. "
                "9. Test rate limiting (multiple submissions)."
            ),
            "memory_node": "Runs/Artflarex_Contact_API_Test.md",
        },
    )

    if api_result["status"] == "success":
        print(f"  Data Validator: {api_result['result']['agent_id']}")
        api_id = api_result["result"]["agent_id"]
    else:
        print(f"  ✗ API Error: {api_result.get('error', 'Unknown')}")
        api_id = None

    return [id for id in [ui_id, api_id] if id]


def test_responsive_design():
    """Test responsive design on multiple viewports."""
    print("\n📱 Testing Responsive Design...")

    result = execute_tool(
        "spawn_agent",
        {
            "role": "ui_explorer",
            "objective": (
                f"Test responsive design of {TARGET_URL}. "
                "Perform these checks on multiple viewports: "
                "1. Desktop (1920x1080): Verify full layout, sidebar, navigation. "
                "2. Tablet (768x1024): Check layout adjustments, touch targets. "
                "3. Mobile (375x667): Test hamburger menu, stacked layout. "
                "4. Verify text is readable on all sizes (no horizontal scroll). "
                "5. Check images scale correctly. "
                "6. Test tap targets are minimum 44x44px on mobile. "
                "7. Verify forms are usable on mobile. "
                "8. Check for content overflow or truncation. "
                "9. Test orientation change (portrait to landscape)."
            ),
            "memory_node": "Runs/Artflarex_Responsive_Test.md",
        },
    )

    if result["status"] == "success":
        print(f"  UI Explorer: {result['result']['agent_id']}")
        return [result["result"]["agent_id"]]
    else:
        print(f"  ✗ Error: {result.get('error', 'Unknown error')}")
        return []


def test_performance_seo():
    """Test performance and SEO basics."""
    print("\n⚡ Testing Performance & SEO...")

    result = execute_tool(
        "spawn_agent",
        {
            "role": "ui_explorer",
            "objective": (
                f"Test performance and SEO of {TARGET_URL}. "
                "Perform these checks: "
                "1. Check page title is descriptive and contains company name. "
                "2. Verify meta description is present. "
                "3. Check for Open Graph tags (og:title, og:description, og:image). "
                "4. Verify favicon is present. "
                "5. Check for canonical URL. "
                "6. Verify heading structure (H1, H2, H3 hierarchy). "
                "7. Check for alt text on images. "
                "8. Verify robots.txt and sitemap.xml (if accessible). "
                "9. Check page load time (initial paint). "
                "10. Verify no render-blocking resources. "
                "11. Check for structured data (JSON-LD). "
                "12. Verify language attribute on HTML tag."
            ),
            "memory_node": "Runs/Artflarex_Performance_SEO_Test.md",
        },
    )

    if result["status"] == "success":
        print(f"  UI Explorer: {result['result']['agent_id']}")
        return [result["result"]["agent_id"]]
    else:
        print(f"  ✗ Error: {result.get('error', 'Unknown error')}")
        return []


def test_accessibility():
    """Test accessibility compliance."""
    print("\n♿ Testing Accessibility...")

    result = execute_tool(
        "spawn_agent",
        {
            "role": "ui_explorer",
            "objective": (
                f"Test accessibility of {TARGET_URL}. "
                "Perform these comprehensive checks: "
                "1. Test keyboard navigation (Tab, Enter, Space, Escape). "
                "2. Verify all interactive elements are keyboard accessible. "
                "3. Check focus indicators are visible. "
                "4. Verify form labels are associated with inputs. "
                "5. Check color contrast ratios (WCAG AA: 4.5:1 for normal text). "
                "6. Verify alt text on all images. "
                "7. Check for ARIA labels and roles. "
                "8. Verify skip navigation link exists. "
                "9. Test screen reader announcements (if possible). "
                "10. Check for animation triggers (prefers-reduced-motion). "
                "11. Verify page has lang attribute. "
                "12. Check for empty links or buttons."
            ),
            "memory_node": "Runs/Artflarex_Accessibility_Test.md",
        },
    )

    print(f"  UI Explorer: {result['result']['agent_id']}")
    return [result["result"]["agent_id"]]


def test_backend_api():
    """Test backend API endpoints."""
    print("\n🔍 Testing Backend APIs...")

    result = execute_tool(
        "spawn_agent",
        {
            "role": "data_validator",
            "objective": (
                f"Test backend APIs for {TARGET_URL}. "
                "Perform these checks: "
                "1. Monitor all XHR/fetch requests during page navigation. "
                "2. Verify API response statuses (200, 404, 500). "
                "3. Check response Content-Type headers. "
                "4. Verify JSON responses are valid. "
                "5. Check for API errors in responses. "
                "6. Verify CORS headers are properly configured. "
                "7. Test API response times (< 2 seconds). "
                "8. Check for authentication requirements on protected endpoints. "
                "9. Verify HTTPS is used (no mixed content). "
                "10. Check for security headers (X-Frame-Options, CSP, etc.)."
            ),
            "memory_node": "Runs/Artflarex_Backend_API_Test.md",
        },
    )

    if result["status"] == "success":
        print(f"  Data Validator: {result['result']['agent_id']}")
        return [result["result"]["agent_id"]]
    else:
        print(f"  ✗ Error: {result.get('error', 'Unknown error')}")
        return []


def print_summary():
    """Print test summary and results locations."""
    print("\n" + "=" * 80)
    print("🎉 ARTFLAREX TEST SUITE COMPLETE")
    print("=" * 80)
    print("\n📊 Results Dashboard:")
    print("   http://localhost:3000")
    print("\n📁 Detailed Test Reports:")
    print("   📄 obsidian_vault/Runs/Artflarex_Homepage_Test.md")
    print("   📄 obsidian_vault/Runs/Artflarex_Navigation_Test.md")
    print("   📄 obsidian_vault/Runs/Artflarex_Services_Test.md")
    print("   📄 obsidian_vault/Runs/Artflarex_Contact_UI_Test.md")
    print("   📄 obsidian_vault/Runs/Artflarex_Contact_API_Test.md")
    print("   📄 obsidian_vault/Runs/Artflarex_Responsive_Test.md")
    print("   📄 obsidian_vault/Runs/Artflarex_Performance_SEO_Test.md")
    print("   📄 obsidian_vault/Runs/Artflarex_Accessibility_Test.md")
    print("   📄 obsidian_vault/Runs/Artflarex_Backend_API_Test.md")
    print("\n📋 Master Log:")
    print("   📄 obsidian_vault/Global/Test_Run_Master.md")
    print("\n💡 Tips:")
    print("   • Open Obsidian vault folder in Obsidian app for visual graph")
    print("   • Check dashboard for real-time agent status")
    print("   • Review agent confidence scores in each report")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    print("=" * 80)
    print(f"🚀 Vectra QA - Testing {APP_NAME}")
    print(f"🎯 Target: {TARGET_URL}")
    print("=" * 80)
    print("\n⚙️  Test Coverage:")
    print("   ✓ Homepage structure & content")
    print("   ✓ Navigation & page transitions")
    print("   ✓ Services pages")
    print("   ✓ Contact form (UI + API)")
    print("   ✓ Responsive design")
    print("   ✓ Performance & SEO")
    print("   ✓ Accessibility")
    print("   ✓ Backend APIs")

    print("\n🤖 Deploying test agents...")
    print("   (Each test takes 30-60 seconds)\n")

    all_agents = []

    # Run all tests with delays between them
    all_agents.extend(test_homepage())
    time.sleep(3)

    all_agents.extend(test_navigation())
    time.sleep(3)

    all_agents.extend(test_services_pages())
    time.sleep(3)

    all_agents.extend(test_contact_form())
    time.sleep(3)

    all_agents.extend(test_responsive_design())
    time.sleep(3)

    all_agents.extend(test_performance_seo())
    time.sleep(3)

    all_agents.extend(test_accessibility())
    time.sleep(3)

    all_agents.extend(test_backend_api())

    print(f"\n✅ All {len(all_agents)} agents deployed successfully!")
    print("   Monitoring tests in real-time...")

    print_summary()

    print("🎉 Test suite initiated!")
    print("   Keep dashboard open: http://localhost:3000\n")
