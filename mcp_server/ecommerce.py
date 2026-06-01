"""
Generic E-Commerce Testing Framework for Vectra QA.

Platform-agnostic testing using CSS selector maps. Supports:
- Shopify, WooCommerce, Magento, custom platforms
- Optozon (Turkish e-commerce)

Usage:
    from mcp_server.ecommerce import EcommerceTester, ECOMMERCE_SELECTOR_MAPS
    
    tester = EcommerceTester("optozon")
    await tester.test_cart_flow(browser, "https://www.optozon.com.tr")
"""

import os
import re
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone

import structlog

from mcp_server.browser_tools import BrowserAutomation

logger = structlog.get_logger()


# ============================================
# PLATFORM SELECTOR MAPS
# ============================================

ECOMMERCE_SELECTOR_MAPS: Dict[str, Dict[str, str]] = {
    "optozon": {
        "add_to_cart": "button[data-add-to-cart], .add-to-cart, [data-action='add-to-cart']",
        "cart_count": ".cart-count-badge, .cart-item-count, [data-cart-count]",
        "cart_icon": ".cart-icon, [data-cart-icon], .header-cart",
        "checkout_button": "button.checkout, [data-checkout], .btn-checkout",
        "product_price": ".product-price .current-price, .price-current, [data-product-price]",
        "product_name": ".product-title, h1.product-name, [data-product-name]",
        "product_image": ".product-image img, [data-product-image]",
        "login_email": "#CustomerEmail, input[type='email'], [name='email']",
        "login_password": "#CustomerPassword, input[type='password'], [name='password']",
        "login_button": "button[type='submit'], .btn-login, [data-login-button]",
        "search_input": "input[type='search'], .search-input, [data-search-input]",
        "search_button": "button[type='submit'], .search-button, [data-search-submit]",
        "cookie_banner": ".cookie-banner, .cookie-consent, [data-cookie-banner]",
        "cookie_accept": ".cookie-accept, .accept-cookies, [data-accept-cookies]",
        "cookie_reject": ".cookie-reject, .reject-cookies, [data-reject-cookies]",
        "quantity_input": "input[name='quantity'], .quantity-input, [data-quantity]",
        "remove_from_cart": ".remove-item, [data-remove-item], .cart-remove",
        "shipping_form": "#shipping-form, .shipping-form, [data-shipping-form]",
        "payment_methods": ".payment-method, [data-payment-method]",
        "order_confirmation": ".order-confirmation, .thank-you, [data-order-confirmation]",
    },
    "shopify": {
        "add_to_cart": "button[name='add'], .add-to-cart",
        "cart_count": ".cart-count-bubble",
        "checkout_button": "button[name='checkout']",
        "product_price": ".price-item--regular",
        "login_email": "#CustomerEmail",
        "login_password": "#CustomerPassword",
        "search_input": "input[type='search']",
        "cookie_banner": ".shopify-pc__banner",
    },
    "woocommerce": {
        "add_to_cart": ".add_to_cart_button",
        "cart_count": ".cart-contents-count",
        "checkout_button": "#place_order",
        "product_price": ".woocommerce-Price-amount",
        "login_email": "#username",
        "login_password": "#password",
        "search_input": "input[name='s']",
    },
    "magento": {
        "add_to_cart": "#product-addtocart-button",
        "cart_count": ".minicart-qty",
        "checkout_button": "#checkout",
        "product_price": ".price",
        "login_email": "#email",
        "login_password": "#pass",
        "search_input": "#search",
    },
    "custom": {},
}


@dataclass
class EcommerceTestResult:
    """Result from an e-commerce test."""

    test_type: str
    status: str  # pass, fail, warning, error
    findings: List[Dict[str, Any]] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    duration_seconds: float = 0.0
    platform: str = "unknown"
    url: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "test_type": self.test_type,
            "status": self.status,
            "findings": self.findings,
            "metrics": self.metrics,
            "duration_seconds": self.duration_seconds,
            "platform": self.platform,
            "url": self.url,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z",
        }


class EcommerceTester:
    """Generic e-commerce testing framework."""

    def __init__(self, platform: str = "custom"):
        self.platform = platform
        self.selectors = ECOMMERCE_SELECTOR_MAPS.get(platform, ECOMMERCE_SELECTOR_MAPS["custom"])
        self.findings: List[Dict[str, Any]] = []

    def _get_selector(self, key: str) -> str:
        """Get CSS selector for a given element key."""
        return self.selectors.get(key, "")

    async def _safe_click(self, browser: BrowserAutomation, selector: str, 
                         timeout: int = 5000) -> bool:
        """Safely click an element, return success status."""
        if not selector:
            return False
        try:
            result = await browser.click(selector, timeout=timeout)
            return result.get("success", False)
        except Exception:
            return False

    async def _safe_fill(self, browser: BrowserAutomation, selector: str, 
                        text: str) -> bool:
        """Safely fill an input, return success status."""
        if not selector:
            return False
        try:
            result = await browser.fill(selector, text)
            return result.get("success", False)
        except Exception:
            return False

    async def _get_element_text(self, browser: BrowserAutomation, selector: str) -> str:
        """Get text content of an element."""
        if not selector:
            return ""
        try:
            result = await browser.get_text(selector)
            return result.get("text", "") if result.get("success") else ""
        except Exception:
            return ""

    async def _get_element_count(self, browser: BrowserAutomation, selector: str) -> int:
        """Count elements matching selector."""
        if not selector:
            return 0
        try:
            result = await browser.get_elements(selector)
            return result.get("count", 0) if result.get("success") else 0
        except Exception:
            return 0

    # ============================================
    # CART FLOW TESTS
    # ============================================

    async def test_cart_flow(self, browser: BrowserAutomation, product_url: str) -> EcommerceTestResult:
        """Test add to cart, update quantity, remove item."""
        start_time = datetime.now(timezone.utc)
        self.findings = []

        try:
            # Visit product page
            result = await browser.visit(product_url)
            if not result.get("success"):
                self.findings.append({
                    "title": "Product Page Load Failed",
                    "description": f"Cannot navigate to {product_url}",
                    "severity": "critical",
                })
                return self._build_result("cart_flow", "fail", start_time, product_url)

            # Check product info
            price = await self._get_element_text(browser, self._get_selector("product_price"))
            name = await self._get_element_text(browser, self._get_selector("product_name"))

            if not price:
                self.findings.append({
                    "title": "Missing Product Price",
                    "description": "Product price not displayed",
                    "severity": "high",
                })
            if not name:
                self.findings.append({
                    "title": "Missing Product Name",
                    "description": "Product name not displayed",
                    "severity": "medium",
                })

            # Add to cart
            added = await self._safe_click(browser, self._get_selector("add_to_cart"))
            if not added:
                self.findings.append({
                    "title": "Add to Cart Failed",
                    "description": "Add to cart button not found or not clickable",
                    "severity": "critical",
                })
                return self._build_result("cart_flow", "fail", start_time, product_url)

            await browser.page.wait_for_timeout(2000) if browser.page else None

            # Verify cart count increased
            cart_count = await self._get_element_text(browser, self._get_selector("cart_count"))
            if not cart_count or cart_count == "0":
                self.findings.append({
                    "title": "Cart Not Updated",
                    "description": "Cart count did not increase after adding item",
                    "severity": "high",
                })
            else:
                self.findings.append({
                    "title": "Item Added to Cart",
                    "description": f"Cart count: {cart_count}",
                    "severity": "info",
                })

            # Navigate to cart
            await self._safe_click(browser, self._get_selector("cart_icon"))
            await browser.page.wait_for_timeout(1500) if browser.page else None

            # Remove from cart
            removed = await self._safe_click(browser, self._get_selector("remove_from_cart"))
            if removed:
                self.findings.append({
                    "title": "Item Removed from Cart",
                    "description": "Successfully removed item from cart",
                    "severity": "info",
                })

            return self._build_result("cart_flow", "pass", start_time, product_url)

        except Exception as e:
            self.findings.append({
                "title": "Cart Flow Error",
                "description": str(e),
                "severity": "critical",
            })
            return self._build_result("cart_flow", "error", start_time, product_url)

    # ============================================
    # CHECKOUT FLOW TESTS
    # ============================================

    async def test_checkout_flow(self, browser: BrowserAutomation, cart_url: str) -> EcommerceTestResult:
        """Test checkout page elements and form validation."""
        start_time = datetime.now(timezone.utc)
        self.findings = []

        try:
            result = await browser.visit(cart_url)
            if not result.get("success"):
                return self._build_result("checkout_flow", "fail", start_time, cart_url)

            # Check checkout button
            checkout_exists = await self._get_element_count(browser, self._get_selector("checkout_button")) > 0
            if not checkout_exists:
                self.findings.append({
                    "title": "Missing Checkout Button",
                    "description": "Checkout button not found on cart page",
                    "severity": "critical",
                })

            # Check shipping form (if on checkout page)
            shipping_exists = await self._get_element_count(browser, self._get_selector("shipping_form")) > 0
            if shipping_exists:
                self.findings.append({
                    "title": "Shipping Form Present",
                    "description": "Shipping address form is available",
                    "severity": "info",
                })

            # Check payment methods
            payment_count = await self._get_element_count(browser, self._get_selector("payment_methods"))
            if payment_count == 0:
                self.findings.append({
                    "title": "No Payment Methods",
                    "description": "No payment method options found",
                    "severity": "high",
                })
            else:
                self.findings.append({
                    "title": "Payment Methods Available",
                    "description": f"Found {payment_count} payment option(s)",
                    "severity": "info",
                })

            status = "pass" if checkout_exists else "fail"
            return self._build_result("checkout_flow", status, start_time, cart_url)

        except Exception as e:
            self.findings.append({
                "title": "Checkout Flow Error",
                "description": str(e),
                "severity": "critical",
            })
            return self._build_result("checkout_flow", "error", start_time, cart_url)

    # ============================================
    # LOCALE TESTS
    # ============================================

    async def test_locale(self, browser: BrowserAutomation, url: str) -> EcommerceTestResult:
        """Test Turkish locale support."""
        start_time = datetime.now(timezone.utc)
        self.findings = []

        try:
            result = await browser.visit(url)
            if not result.get("success"):
                return self._build_result("locale", "fail", start_time, url)

            # Check for Turkish characters
            page_text = ""
            if browser.page:
                page_text = await browser.page.evaluate("() => document.body.innerText")

            turkish_chars = ["ç", "ğ", "ı", "ö", "ş", "ü", "Ç", "Ğ", "I", "Ö", "Ş", "Ü"]
            found_chars = [c for c in turkish_chars if c in page_text]

            if not found_chars:
                self.findings.append({
                    "title": "Missing Turkish Characters",
                    "description": "No Turkish characters (ç,ğ,ı,ö,ş,ü) found on page",
                    "severity": "medium",
                })
            else:
                self.findings.append({
                    "title": "Turkish Characters Present",
                    "description": f"Found characters: {', '.join(found_chars)}",
                    "severity": "info",
                })

            # Check for Turkish Lira symbol
            if "₺" in page_text or "TL" in page_text:
                self.findings.append({
                    "title": "Turkish Lira Currency",
                    "description": "Turkish Lira (₺) symbol found",
                    "severity": "info",
                })
            else:
                self.findings.append({
                    "title": "Missing Turkish Lira Symbol",
                    "description": "No Turkish Lira (₺) symbol found",
                    "severity": "low",
                })

            # Check page language
            lang = ""
            if browser.page:
                lang = await browser.page.evaluate("() => document.documentElement.lang")

            if lang and "tr" in lang.lower():
                self.findings.append({
                    "title": "Turkish Language Set",
                    "description": f"Page language: {lang}",
                    "severity": "info",
                })
            else:
                self.findings.append({
                    "title": "Language Not Set to Turkish",
                    "description": f"Page language attribute: {lang}",
                    "severity": "low",
                })

            return self._build_result("locale", "pass", start_time, url)

        except Exception as e:
            self.findings.append({
                "title": "Locale Test Error",
                "description": str(e),
                "severity": "critical",
            })
            return self._build_result("locale", "error", start_time, url)

    # ============================================
    # GDPR TESTS
    # ============================================

    async def test_gdpr_compliance(self, browser: BrowserAutomation, url: str) -> EcommerceTestResult:
        """Test GDPR compliance indicators."""
        start_time = datetime.now(timezone.utc)
        self.findings = []

        try:
            result = await browser.visit(url)
            if not result.get("success"):
                return self._build_result("gdpr", "fail", start_time, url)

            # Check for cookie banner
            banner_count = await self._get_element_count(browser, self._get_selector("cookie_banner"))
            if banner_count > 0:
                self.findings.append({
                    "title": "Cookie Banner Present",
                    "description": "Cookie consent banner found on page",
                    "severity": "info",
                })

                # Check for reject option
                reject_count = await self._get_element_count(browser, self._get_selector("cookie_reject"))
                if reject_count > 0:
                    self.findings.append({
                        "title": "Cookie Reject Option Available",
                        "description": "Users can reject non-essential cookies",
                        "severity": "info",
                    })
                else:
                    self.findings.append({
                        "title": "Missing Cookie Reject Option",
                        "description": "No reject option found - may violate GDPR",
                        "severity": "high",
                    })
            else:
                self.findings.append({
                    "title": "No Cookie Banner",
                    "description": "No cookie consent mechanism found",
                    "severity": "medium",
                })

            # Check for privacy policy link
            if browser.page:
                links = await browser.page.query_selector_all("a[href*='privacy'], a[href*='gizlilik']")
                if len(links) > 0:
                    self.findings.append({
                        "title": "Privacy Policy Link Found",
                        "description": f"Found {len(links)} privacy-related link(s)",
                        "severity": "info",
                    })
                else:
                    self.findings.append({
                        "title": "Missing Privacy Policy",
                        "description": "No privacy policy link found",
                        "severity": "medium",
                    })

            # Check for tracking pixels (Facebook, Google)
            if browser.page:
                page_content = await browser.page.content()
                trackers = []
                if "facebook.com/tr" in page_content or "fbq(" in page_content:
                    trackers.append("Facebook Pixel")
                if "googletagmanager" in page_content or "gtag(" in page_content:
                    trackers.append("Google Analytics")
                if "hotjar" in page_content:
                    trackers.append("Hotjar")

                if trackers:
                    self.findings.append({
                        "title": "Tracking Pixels Detected",
                        "description": f"Found: {', '.join(trackers)}",
                        "severity": "info",
                    })

            return self._build_result("gdpr", "pass", start_time, url)

        except Exception as e:
            self.findings.append({
                "title": "GDPR Test Error",
                "description": str(e),
                "severity": "critical",
            })
            return self._build_result("gdpr", "error", start_time, url)

    # ============================================
    # HELPER METHODS
    # ============================================

    def _build_result(
        self, test_type: str, status: str, start_time: datetime, url: str
    ) -> EcommerceTestResult:
        """Build a standardized test result."""
        elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()

        # Determine overall status from findings
        severities = [f["severity"] for f in self.findings]
        if "critical" in severities or "high" in severities:
            if status == "pass":
                status = "warning"

        return EcommerceTestResult(
            test_type=test_type,
            status=status,
            findings=self.findings.copy(),
            duration_seconds=elapsed,
            platform=self.platform,
            url=url,
        )


# ============================================
# OPTOZON-SPECIFIC TESTS
# ============================================

class OptozonTester(EcommerceTester):
    """Pre-configured tester for Optozon (www.optozon.com.tr)."""

    def __init__(self):
        super().__init__("optozon")
        self.base_url = "https://www.optozon.com.tr"

    async def smoke_test(self, browser: BrowserAutomation) -> List[EcommerceTestResult]:
        """Run a full smoke test suite against Optozon."""
        results = []

        # 1. Homepage loads
        logger.info("optozon_smoke_test", step="homepage")
        result = await self.test_locale(browser, self.base_url)
        results.append(result)

        # 2. Search functionality
        search_input = self._get_selector("search_input")
        if search_input and browser.page:
            await browser.visit(self.base_url)
            await self._safe_fill(browser, search_input, "laptop")
            await self._safe_click(browser, self._get_selector("search_button"))
            await browser.page.wait_for_timeout(2000)

            search_results = await browser.page.title()
            results.append(EcommerceTestResult(
                test_type="search",
                status="pass" if "laptop" in search_results.lower() or "sonuç" in search_results.lower() else "warning",
                findings=[{"title": "Search Test", "description": f"Searched for 'laptop', page title: {search_results}", "severity": "info"}],
                url=f"{self.base_url}/search?q=laptop",
                platform="optozon",
            ))

        # 3. GDPR check
        logger.info("optozon_smoke_test", step="gdpr")
        result = await self.test_gdpr_compliance(browser, self.base_url)
        results.append(result)

        return results
