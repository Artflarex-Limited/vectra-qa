#!/usr/bin/env python3
"""
Example: Testing a Generic Web Application

This demonstrates how to test common web app features:
- Login/logout flow
- Dashboard navigation
- Form submission
- API validation

Usage:
    1. Set TARGET_URL in your .env file
    2. docker compose up
    3. python examples/test_real_app.py

The agents will:
    - Explore your UI
    - Test functionality
    - Report findings to the Obsidian vault
    - Update the Command Center dashboard
"""

import sys
import time
from pathlib import Path

# Add parent directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp_server.tools import execute_tool

# ============ CONFIGURATION ============
# Edit these for your specific application
TARGET_URL = "http://localhost:3001"  # Your app's URL
APP_NAME = "My Web Application"
TEST_FEATURES = [
    "login",
    "dashboard",
    "profile",
]


def test_login_flow():
    """
    Test the authentication system.

    Agents will:
    1. Navigate to login page
    2. Verify form fields
    3. Test validation
    4. Submit credentials
    5. Verify redirect
    """
    print("\n🔐 Testing Login Flow...")

    # UI Explorer tests the frontend
    ui_result = execute_tool(
        "spawn_agent",
        {
            "role": "ui_explorer",
            "objective": (
                f"Test the login page at {TARGET_URL}/login. "
                "Perform these checks: "
                "1. Verify the page loads without errors. "
                "2. Check for email/username input field. "
                "3. Check for password input field. "
                "4. Check for submit/login button. "
                "5. Test form validation (empty fields, invalid email). "
                "6. If test credentials are available, attempt login. "
                "7. Verify successful redirect or error message. "
                "8. Check accessibility (labels, focus states, ARIA)."
            ),
            "memory_node": "Runs/Login_Flow_UI.md",
        },
    )

    print(f"  UI Explorer: {ui_result['result']['agent_id']}")

    # Wait for UI test to complete
    time.sleep(3)

    # Data Validator monitors API calls
    api_result = execute_tool(
        "spawn_agent",
        {
            "role": "data_validator",
            "objective": (
                "Monitor authentication API endpoints. "
                "Perform these checks: "
                "1. Intercept POST requests to login endpoints (/api/auth/login, /login, etc.). "
                "2. Verify request payload contains credentials. "
                "3. Check response status code (200 for success, 401 for invalid). "
                "4. If successful, verify response contains token or session ID. "
                "5. Verify JWT structure if token is returned. "
                "6. Check for secure cookie flags (HttpOnly, Secure, SameSite). "
                "7. Verify CORS headers are correct."
            ),
            "memory_node": "Runs/Login_Flow_API.md",
        },
    )

    print(f"  Data Validator: {api_result['result']['agent_id']}")

    return [ui_result["result"]["agent_id"], api_result["result"]["agent_id"]]


def test_dashboard():
    """
    Test the main dashboard/application area.

    Agents will:
    1. Navigate to dashboard
    2. Verify key elements load
    3. Test navigation
    4. Check data display
    """
    print("\n📊 Testing Dashboard...")

    result = execute_tool(
        "spawn_agent",
        {
            "role": "ui_explorer",
            "objective": (
                f"Test the main dashboard at {TARGET_URL}/dashboard (or main app page). "
                "Perform these checks: "
                "1. Verify page loads and shows expected layout. "
                "2. Check for navigation menu/sidebar. "
                "3. Verify main content area is visible. "
                "4. Test navigation links (click each, verify route change). "
                "5. Check for loading states and spinners. "
                "6. Verify responsive design (if applicable). "
                "7. Look for console errors or broken images."
            ),
            "memory_node": "Runs/Dashboard_Test.md",
        },
    )

    print(f"  UI Explorer: {result['result']['agent_id']}")

    return [result["result"]["agent_id"]]


def test_critical_user_journey():
    """
    Test the most important user path end-to-end.

    This is typically:
    Login → Main Feature → Action → Verify Result
    """
    print("\n🎯 Testing Critical User Journey...")

    result = execute_tool(
        "spawn_agent",
        {
            "role": "ui_explorer",
            "objective": (
                "Complete a full user journey: "
                f"1. Start at {TARGET_URL}. "
                "2. Navigate to the most important feature of the app. "
                "3. Interact with the main functionality (create, update, or view something). "
                "4. Verify the action succeeds (success message, state change, etc.). "
                "5. Check that data persists (refresh page, verify still there). "
                "6. Logout if applicable. "
                "Report any broken flows, confusing UX, or errors."
            ),
            "memory_node": "Runs/Critical_Journey_Test.md",
        },
    )

    print(f"  UI Explorer: {result['result']['agent_id']}")

    return [result["result"]["agent_id"]]


def run_regression_suite():
    """
    Run a quick regression test to verify core functionality.
    """
    print("\n🔄 Running Regression Suite...")

    result = execute_tool(
        "spawn_agent",
        {
            "role": "ui_explorer",
            "objective": (
                "Quick regression check: "
                f"1. Visit {TARGET_URL} and verify homepage loads. "
                "2. Check all main navigation links work (no 404s). "
                "3. Verify login page is accessible. "
                "4. Check footer and header are present. "
                "5. Look for any console errors or visual bugs. "
                "6. Test on mobile viewport (375x667)."
            ),
            "memory_node": "Runs/Regression_Test.md",
        },
    )

    print(f"  UI Explorer: {result['result']['agent_id']}")

    return [result["result"]["agent_id"]]


def print_results_summary():
    """Print a summary of where to find results."""
    print("\n" + "=" * 70)
    print("📋 RESULTS SUMMARY")
    print("=" * 70)
    print("\nView real-time results:")
    print("  🌐 Dashboard: http://localhost:3000")
    print("\nDetailed reports (Obsidian Vault):")
    print("  📁 obsidian_vault/Runs/Login_Flow_UI.md")
    print("  📁 obsidian_vault/Runs/Login_Flow_API.md")
    print("  📁 obsidian_vault/Runs/Dashboard_Test.md")
    print("  📁 obsidian_vault/Runs/Critical_Journey_Test.md")
    print("  📁 obsidian_vault/Runs/Regression_Test.md")
    print("\nMaster test log:")
    print("  📁 obsidian_vault/Global/Test_Run_Master.md")
    print("\n" + "=" * 70)
    print("💡 Tip: Open the Obsidian vault folder in Obsidian app for")
    print("   a visual graph of all test relationships!")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    print("=" * 70)
    print(f"🚀 Vectra QA - Testing {APP_NAME}")
    print(f"🎯 Target: {TARGET_URL}")
    print("=" * 70)

    print("\n⚙️  Configuration:")
    print(f"   URL: {TARGET_URL}")
    print(f"   Features: {', '.join(TEST_FEATURES)}")

    print("\n🤖 Deploying test agents...")
    print("   (This may take 30-60 seconds per test)\n")

    all_agents = []

    # Run tests
    if "login" in TEST_FEATURES:
        all_agents.extend(test_login_flow())
        time.sleep(5)  # Wait between tests

    if "dashboard" in TEST_FEATURES:
        all_agents.extend(test_dashboard())
        time.sleep(5)

    all_agents.extend(test_critical_user_journey())
    time.sleep(5)

    all_agents.extend(run_regression_suite())

    print("\n✅ All tests initiated!")
    print(f"   Total agents spawned: {len(all_agents)}")

    print_results_summary()

    print("🎉 Test suite complete!")
    print("   Keep the dashboard open to watch agents work in real-time.\n")
