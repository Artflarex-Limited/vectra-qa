"""
Unit tests for the generic E-Commerce testing framework.

Uses mocked Playwright browser (BrowserAutomation) to test navigation,
add-to-cart flows, checkout flows, selector resolution, GDPR compliance,
locale detection, and error handling — without hitting real websites.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, call, patch
from datetime import datetime, timezone

from mcp_server.ecommerce import (
    EcommerceTester,
    EcommerceTestResult,
    ECOMMERCE_SELECTOR_MAPS,
    OptozonTester,
)


# =============================================================================
# Helpers
# =============================================================================

def _mock_browser(page=None):
    """Create a mocked BrowserAutomation with a controllable page."""
    browser = MagicMock()
    if page is None:
        page = AsyncMock()
        page.url = "https://example.com"
    browser.page = page
    # Wire the async methods
    browser.visit = AsyncMock()
    browser.click = AsyncMock()
    browser.fill = AsyncMock()
    browser.get_text = AsyncMock()
    browser.get_elements = AsyncMock()
    return browser


# =============================================================================
# Selector Maps
# =============================================================================

@pytest.mark.unit
class TestEcommerceSelectorMaps:
    """Platform selector map resolution."""

    def test_optozon_has_required_selectors(self):
        """Optozon selector map should include all core selectors."""
        selectors = ECOMMERCE_SELECTOR_MAPS["optozon"]
        required = ["add_to_cart", "cart_count", "cart_icon", "checkout_button",
                     "product_price", "product_name", "search_input"]
        for key in required:
            assert key in selectors, f"Missing required selector: {key}"
            assert selectors[key], f"Empty selector for: {key}"

    def test_custom_platform_starts_empty(self):
        """Custom platform should start with an empty selector map."""
        assert ECOMMERCE_SELECTOR_MAPS["custom"] == {}

    def test_selector_getter_returns_correct_value(self):
        """EcommerceTester._get_selector should resolve platform selector."""
        tester = EcommerceTester("optozon")
        selector = tester._get_selector("add_to_cart")
        assert selector == ECOMMERCE_SELECTOR_MAPS["optozon"]["add_to_cart"]

    def test_selector_getter_returns_empty_for_unknown_key(self):
        """EcommerceTester._get_selector should return empty string for unknown key."""
        tester = EcommerceTester("optozon")
        assert tester._get_selector("nonexistent_key") == ""


# =============================================================================
# Safe click / fill helpers
# =============================================================================

@pytest.mark.unit
class TestEcommerceSafeHelpers:
    """Safe interaction helper methods."""

    @pytest.mark.asyncio
    async def test_safe_click_success(self):
        """_safe_click returns True when click succeeds."""
        browser = _mock_browser()
        browser.click.return_value = {"success": True}
        tester = EcommerceTester("optozon")

        result = await tester._safe_click(browser, "#my-button")

        assert result is True
        browser.click.assert_awaited_once_with("#my-button", timeout=5000)

    @pytest.mark.asyncio
    async def test_safe_click_failure_returns_false(self):
        """_safe_click returns False when click fails."""
        browser = _mock_browser()
        browser.click.return_value = {"success": False}
        tester = EcommerceTester("optozon")

        result = await tester._safe_click(browser, "#my-button")

        assert result is False

    @pytest.mark.asyncio
    async def test_safe_click_exception_returns_false(self):
        """_safe_click returns False when click raises."""
        browser = _mock_browser()
        browser.click.side_effect = RuntimeError("element detached")
        tester = EcommerceTester("optozon")

        result = await tester._safe_click(browser, "#my-button")

        assert result is False

    @pytest.mark.asyncio
    async def test_safe_click_empty_selector_returns_false(self):
        """_safe_click returns False for empty selector."""
        browser = _mock_browser()
        tester = EcommerceTester("custom")  # empty selectors

        result = await tester._safe_click(browser, "")

        assert result is False

    @pytest.mark.asyncio
    async def test_safe_fill_success(self):
        """_safe_fill returns True when fill succeeds."""
        browser = _mock_browser()
        browser.fill.return_value = {"success": True}
        tester = EcommerceTester("optozon")

        result = await tester._safe_fill(browser, "#email", "test@example.com")

        assert result is True
        browser.fill.assert_awaited_once_with("#email", "test@example.com")

    @pytest.mark.asyncio
    async def test_safe_fill_empty_selector_returns_false(self):
        """_safe_fill returns False for empty selector."""
        browser = _mock_browser()
        tester = EcommerceTester("custom")

        result = await tester._safe_fill(browser, "", "text")

        assert result is False


# =============================================================================
# Cart flow tests
# =============================================================================

@pytest.mark.unit
class TestEcommerceCartFlow:
    """Test the add-to-cart flow."""

    @pytest.mark.asyncio
    async def test_cart_flow_success(self):
        """Happy path: visit product, add to cart, verify cart count."""
        browser = _mock_browser()
        browser.visit.return_value = {"success": True}
        browser.get_text.side_effect = [
            {"success": True, "text": "$29.99"},   # product_price
            {"success": True, "text": "Cool Hat"},  # product_name
            {"success": True, "text": "1"},          # cart_count
        ]
        browser.click.return_value = {"success": True}

        tester = EcommerceTester("optozon")
        result = await tester.test_cart_flow(browser, "https://example.com/product/hat")

        assert isinstance(result, EcommerceTestResult)
        assert result.status == "pass"
        assert result.test_type == "cart_flow"
        assert result.platform == "optozon"
        assert result.url == "https://example.com/product/hat"
        assert result.duration_seconds >= 0

        # Should have findings for cart count and removal
        assert len(result.findings) >= 2

    @pytest.mark.asyncio
    async def test_cart_flow_page_load_failure(self):
        """Should return fail status when product page cannot be loaded."""
        browser = _mock_browser()
        browser.visit.return_value = {"success": False}

        tester = EcommerceTester("optozon")
        result = await tester.test_cart_flow(browser, "https://example.com/broken")

        assert result.status == "fail"
        assert any("critical" in f["severity"] for f in result.findings)

    @pytest.mark.asyncio
    async def test_cart_flow_add_to_cart_failure(self):
        """Should return fail status when add-to-cart button cannot be clicked."""
        browser = _mock_browser()
        browser.visit.return_value = {"success": True}
        browser.get_text.side_effect = [
            {"success": True, "text": "$10.00"},
            {"success": True, "text": "Widget"},
        ]
        # Make add_to_cart click fail
        browser.click.return_value = {"success": False}

        tester = EcommerceTester("optozon")
        result = await tester.test_cart_flow(browser, "https://example.com/product/widget")

        assert result.status == "fail"
        assert any("Add to Cart Failed" in f["title"] for f in result.findings)

    @pytest.mark.asyncio
    async def test_cart_flow_missing_product_info(self):
        """Should report findings when product price or name is missing."""
        browser = _mock_browser()
        browser.visit.return_value = {"success": True}
        browser.get_text.side_effect = [
            {"success": False, "text": ""},   # product_price — missing
            {"success": False, "text": ""},   # product_name — missing
        ]
        browser.click.return_value = {"success": True}

        tester = EcommerceTester("optozon")
        result = await tester.test_cart_flow(browser, "https://example.com/product/x")

        # Status is "warning" (pass but with high-severity findings)
        assert result.status in ("pass", "warning")
        titles = [f["title"] for f in result.findings]
        assert "Missing Product Price" in titles
        assert "Missing Product Name" in titles

    @pytest.mark.asyncio
    async def test_cart_flow_exception_returns_error(self):
        """Should return error status when an unexpected exception occurs."""
        browser = _mock_browser()
        browser.visit.side_effect = RuntimeError("unexpected crash")

        tester = EcommerceTester("optozon")
        result = await tester.test_cart_flow(browser, "https://example.com/product/err")

        assert result.status == "error"
        assert any("Cart Flow Error" in f["title"] for f in result.findings)


# =============================================================================
# Checkout flow tests
# =============================================================================

@pytest.mark.unit
class TestEcommerceCheckoutFlow:
    """Test the checkout flow."""

    @pytest.mark.asyncio
    async def test_checkout_flow_success(self):
        """Happy path: checkout page has button, shipping form, and payment methods."""
        browser = _mock_browser()
        browser.visit.return_value = {"success": True}
        browser.get_elements.side_effect = [
            {"success": True, "count": 1},   # checkout_button exists
            {"success": True, "count": 1},   # shipping_form exists
            {"success": True, "count": 3},   # payment_methods exist
        ]

        tester = EcommerceTester("optozon")
        result = await tester.test_checkout_flow(browser, "https://example.com/cart")

        assert result.status == "pass"
        assert result.test_type == "checkout_flow"

    @pytest.mark.asyncio
    async def test_checkout_flow_missing_button(self):
        """Should fail when checkout button is not found."""
        browser = _mock_browser()
        browser.visit.return_value = {"success": True}
        browser.get_elements.side_effect = [
            {"success": True, "count": 0},   # checkout_button missing
            {"success": True, "count": 1},   # shipping_form exists
            {"success": True, "count": 2},   # payment_methods exist
        ]

        tester = EcommerceTester("optozon")
        result = await tester.test_checkout_flow(browser, "https://example.com/cart")

        assert result.status == "fail"
        assert any("Missing Checkout Button" in f["title"] for f in result.findings)

    @pytest.mark.asyncio
    async def test_checkout_flow_page_load_failure(self):
        """Should return fail when cart page cannot be loaded."""
        browser = _mock_browser()
        browser.visit.return_value = {"success": False}

        tester = EcommerceTester("optozon")
        result = await tester.test_checkout_flow(browser, "https://example.com/cart")

        assert result.status == "fail"

    @pytest.mark.asyncio
    async def test_checkout_flow_exception_returns_error(self):
        """Should return error status on unexpected exception."""
        browser = _mock_browser()
        browser.visit.side_effect = RuntimeError("page crash")

        tester = EcommerceTester("optozon")
        result = await tester.test_checkout_flow(browser, "https://example.com/cart")

        assert result.status == "error"


# =============================================================================
# GDPR compliance tests
# =============================================================================

@pytest.mark.unit
class TestEcommerceGDPR:
    """Test GDPR compliance detection."""

    @pytest.mark.asyncio
    async def test_gdpr_cookie_banner_detected(self):
        """Should report findings when a cookie banner and reject option are found."""
        browser = _mock_browser()
        browser.visit.return_value = {"success": True}
        browser.get_elements.side_effect = [
            {"success": True, "count": 1},   # cookie_banner
            {"success": True, "count": 1},   # cookie_reject
        ]

        # Mock page methods for privacy link and tracking pixel checks
        browser.page.query_selector_all = AsyncMock(return_value=[MagicMock()])
        browser.page.content = AsyncMock(return_value="<html></html>")

        tester = EcommerceTester("optozon")
        result = await tester.test_gdpr_compliance(browser, "https://example.com")

        assert result.status == "pass"
        titles = [f["title"] for f in result.findings]
        assert "Cookie Banner Present" in titles
        assert "Cookie Reject Option Available" in titles

    @pytest.mark.asyncio
    async def test_gdpr_missing_reject_option(self):
        """Should flag missing cookie reject option as high severity."""
        browser = _mock_browser()
        browser.visit.return_value = {"success": True}
        browser.get_elements.side_effect = [
            {"success": True, "count": 1},   # cookie_banner
            {"success": True, "count": 0},   # cookie_reject — missing
        ]
        browser.page.query_selector_all = AsyncMock(return_value=[])
        browser.page.content = AsyncMock(return_value="<html></html>")

        tester = EcommerceTester("optozon")
        result = await tester.test_gdpr_compliance(browser, "https://example.com")

        titles = [f["title"] for f in result.findings]
        assert "Missing Cookie Reject Option" in titles

    @pytest.mark.asyncio
    async def test_gdpr_page_load_failure(self):
        """Should return fail when page cannot be loaded."""
        browser = _mock_browser()
        browser.visit.return_value = {"success": False}

        tester = EcommerceTester("optozon")
        result = await tester.test_gdpr_compliance(browser, "https://example.com")

        assert result.status == "fail"


# =============================================================================
# Locale tests
# =============================================================================

@pytest.mark.unit
class TestEcommerceLocale:
    """Test Turkish locale detection."""

    @pytest.mark.asyncio
    async def test_locale_turkish_chars_found(self):
        """Should detect Turkish characters on page."""
        browser = _mock_browser()
        browser.visit.return_value = {"success": True}
        browser.page.evaluate = AsyncMock()
        browser.page.evaluate.side_effect = [
            "Sayfa İçeriği çğşıüö",       # body.innerText
            "tr",                           # document.documentElement.lang
        ]

        tester = EcommerceTester("optozon")
        result = await tester.test_locale(browser, "https://example.com.tr")

        assert result.status == "pass"
        titles = [f["title"] for f in result.findings]
        assert "Turkish Characters Present" in titles
        assert "Turkish Language Set" in titles

    @pytest.mark.asyncio
    async def test_locale_missing_turkish_chars(self):
        """Should flag missing Turkish characters as medium severity."""
        browser = _mock_browser()
        browser.visit.return_value = {"success": True}
        browser.page.evaluate = AsyncMock()
        browser.page.evaluate.side_effect = [
            "English Only Page",           # body.innerText
            "en",                          # document.documentElement.lang
        ]

        tester = EcommerceTester("optozon")
        result = await tester.test_locale(browser, "https://example.com")

        titles = [f["title"] for f in result.findings]
        assert "Missing Turkish Characters" in titles
        assert "Language Not Set to Turkish" in titles


# =============================================================================
# OptozonTester
# =============================================================================

@pytest.mark.unit
class TestOptozonTester:
    """Optozon-specific tester."""

    @pytest.mark.asyncio
    async def test_smoke_test_runs_all_checks(self):
        """OptozonTester.smoke_test should run locale, search, and GDPR checks."""
        browser = _mock_browser()
        browser.visit.return_value = {"success": True}
        browser.page.evaluate = AsyncMock(return_value="Türkçe Sayfa")
        browser.page.title = AsyncMock(return_value="laptop sonuçları")
        browser.page.query_selector_all = AsyncMock(return_value=[])
        browser.page.content = AsyncMock(return_value="<html></html>")
        browser.get_elements.return_value = {"success": True, "count": 1}
        browser.get_text.return_value = {"success": True, "text": "test"}
        browser.fill.return_value = {"success": True}
        browser.click.return_value = {"success": True}

        tester = OptozonTester()
        results = await tester.smoke_test(browser)

        assert len(results) >= 3
        test_types = [r.test_type for r in results]
        assert "locale" in test_types
        assert "search" in test_types
        assert "gdpr" in test_types

    def test_optozon_tester_uses_correct_platform(self):
        """OptozonTester should default to optozon platform."""
        tester = OptozonTester()
        assert tester.platform == "optozon"
        assert tester.base_url == "https://www.optozon.com.tr"
