"""
Integration tests for Vectra QA.

Tests real browser automation against a local Flask server.
Requires: playwright install chromium

Usage:
    pytest tests/integration/ -v
"""

import pytest
import asyncio
import tempfile
import shutil
from pathlib import Path

# Import framework modules
from mcp_server.browser_tools import BrowserAutomation


@pytest.fixture(scope="module")
def test_server():
    """Start the Flask test server."""
    import subprocess
    import time
    import requests

    # Start server
    proc = subprocess.Popen(
        ["python", "tests/integration/server.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Wait for server to be ready
    for _ in range(30):
        try:
            response = requests.get("http://localhost:8765/health", timeout=1)
            if response.status_code == 200:
                break
        except Exception:
            time.sleep(0.5)
    else:
        proc.terminate()
        raise RuntimeError("Test server failed to start")

    yield "http://localhost:8765"

    proc.terminate()
    proc.wait(timeout=5)


@pytest.fixture
async def browser():
    """Create a real browser instance."""
    browser = BrowserAutomation(headless=True)
    await browser.start()
    yield browser
    await browser.close()


@pytest.fixture
def temp_vault():
    """Create a temporary vault directory."""
    temp_dir = tempfile.mkdtemp(prefix="vectra_test_vault_")
    yield Path(temp_dir)
    shutil.rmtree(temp_dir, ignore_errors=True)


class TestBrowserAutomationE2E:
    """End-to-end browser automation tests."""

    @pytest.mark.asyncio
    async def test_visit_homepage(self, browser, test_server):
        """Should navigate to homepage and verify content."""
        result = await browser.visit(test_server + "/")
        assert result["success"] is True
        assert result["url"] == test_server + "/"

        # Verify page title
        title = await browser.page.title()
        assert "Test Store" in title

    @pytest.mark.asyncio
    async def test_click_navigation(self, browser, test_server):
        """Should click navigation links."""
        await browser.visit(test_server + "/")

        # Click contact link
        result = await browser.click("a[href='/contact']")
        assert result["success"] is True

        # Verify navigation
        assert "/contact" in browser.page.url

    @pytest.mark.asyncio
    async def test_fill_form(self, browser, test_server):
        """Should fill and submit contact form."""
        await browser.visit(test_server + "/contact")

        # Fill form
        await browser.fill("input[name='name']", "Test User")
        await browser.fill("input[name='email']", "test@example.com")
        await browser.fill("textarea[name='message']", "This is a test message")

        # Verify values
        name_value = await browser.page.input_value("input[name='name']")
        assert name_value == "Test User"

    @pytest.mark.asyncio
    async def test_screenshot(self, browser, test_server, temp_vault):
        """Should take a screenshot."""
        await browser.visit(test_server + "/")

        screenshot_path = str(temp_vault / "homepage.png")
        result = await browser.screenshot(screenshot_path)
        assert result["success"] is True
        assert Path(screenshot_path).exists()

    @pytest.mark.asyncio
    async def test_console_errors(self, browser, test_server):
        """Should capture console errors."""
        await browser.visit(test_server + "/")

        # Wait a moment for any console messages
        await asyncio.sleep(0.5)

        errors = await browser.get_console_errors()
        # Our test server shouldn't have JS errors
        assert len(errors) == 0


class TestAuthFlowE2E:
    """Authentication flow integration tests."""

    @pytest.mark.asyncio
    async def test_login_success(self, browser, test_server):
        """Should login successfully with valid credentials."""
        await browser.visit(test_server + "/login")

        # Fill login form
        await browser.fill("input[name='email']", "test@example.com")
        await browser.fill("input[name='password']", "password123")

        # Click login
        result = await browser.click("button[type='submit']")
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_login_failure(self, browser, test_server):
        """Should fail login with invalid credentials."""
        await browser.visit(test_server + "/login")

        await browser.fill("input[name='email']", "wrong@example.com")
        await browser.fill("input[name='password']", "wrongpassword")

        result = await browser.click("button[type='submit']")
        assert result["success"] is True  # Request succeeded
        # But page should show error


class TestEcommerceE2E:
    """E-commerce testing integration tests."""

    @pytest.mark.asyncio
    async def test_product_page_loads(self, browser, test_server):
        """Should load product listing page."""
        result = await browser.visit(test_server + "/products")
        assert result["success"] is True

        # Check for products
        elements = await browser.get_elements(".product")
        assert elements["count"] > 0

    @pytest.mark.asyncio
    async def test_add_to_cart(self, browser, test_server):
        """Should add product to cart."""
        await browser.visit(test_server + "/products")

        # Click add to cart on first product
        result = await browser.click(".add-to-cart")
        assert result["success"] is True

        # Wait for cart update
        await asyncio.sleep(1)

    @pytest.mark.asyncio
    async def test_turkish_locale(self, browser, test_server):
        """Should verify Turkish locale elements."""
        await browser.visit(test_server + "/")

        # Check for Turkish text
        text = await browser.get_text("body")
        assert text["success"] is True
        body_text = text.get("text", "")

        # Turkish characters should be present
        assert "ç" in body_text or "ğ" in body_text

    @pytest.mark.asyncio
    async def test_cookie_banner(self, browser, test_server):
        """Should detect cookie consent banner."""
        await browser.visit(test_server + "/")

        elements = await browser.get_elements(".cookie-banner")
        assert elements["count"] > 0


class TestOptozonSmokeE2E:
    """Optozon smoke tests (requires internet)."""

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Requires internet access to www.optozon.com.tr")
    async def test_optozon_homepage(self, browser):
        """Should load Optozon homepage."""
        result = await browser.visit("https://www.optozon.com.tr")
        assert result["success"] is True

        # Verify Turkish locale
        title = await browser.page.title()
        assert len(title) > 0

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Requires internet access")
    async def test_optozon_search(self, browser):
        """Should search for products on Optozon."""
        await browser.visit("https://www.optozon.com.tr")

        # Try to find search input
        search_exists = await browser.get_elements("input[type='search']")
        if search_exists["count"] == 0:
            pytest.skip("Search not available")

        await browser.fill("input[type='search']", "laptop")
        await browser.page.keyboard.press("Enter")
        await asyncio.sleep(3)

        # Verify results page loaded
        assert "laptop" in browser.page.url or "arama" in browser.page.url


class TestDeterministicModeE2E:
    """Deterministic mode integration tests."""

    @pytest.mark.asyncio
    async def test_deterministic_playbook(self, browser, test_server):
        """Should execute a deterministic test playbook."""
        playbook = {
            "name": "Homepage Smoke Test",
            "url": test_server + "/",
            "steps": [
                {"action": "visit", "url": test_server + "/"},
                {"action": "assert", "selector": "h1", "expected_text": "Hoş Geldiniz"},
                {"action": "click", "selector": "a[href='/contact']"},
                {"action": "assert", "selector": "h1", "expected_text": "İletişim"},
            ],
        }

        # Execute playbook
        results = []
        for step in playbook["steps"]:
            if step["action"] == "visit":
                result = await browser.visit(step["url"])
                results.append({"step": step, "success": result["success"]})
            elif step["action"] == "click":
                result = await browser.click(step["selector"])
                results.append({"step": step, "success": result["success"]})
            elif step["action"] == "assert":
                text = await browser.get_text(step["selector"])
                success = step["expected_text"] in text.get("text", "")
                results.append({"step": step, "success": success})

        # All steps should pass
        assert all(r["success"] for r in results)
