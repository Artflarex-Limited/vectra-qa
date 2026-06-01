"""
Authentication flow testing for Vectra QA.

Tests login/logout flows, session management, and credential security.
Supports configurable credentials via environment variables.
"""

from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

import structlog

logger = structlog.get_logger()


class AuthFlowTester:
    """Tests authentication flows using Playwright."""

    def __init__(self, browser):
        """
        Initialize auth flow tester.

        Args:
            browser: BrowserAutomation instance
        """
        self.browser = browser
        self.findings: List[Dict[str, Any]] = []
        self.session_data: Dict[str, Any] = {}

    async def test_login_flow(
        self,
        login_url: str,
        username: str,
        password: str,
        username_selector: str = "input[type='email'], input[name='username'], input[name='email'], #username, #email",
        password_selector: str = "input[type='password'], input[name='password'], #password",
        submit_selector: str = "button[type='submit'], input[type='submit'], button:has-text('Sign In'), button:has-text('Login')",
        success_indicator: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Test complete login flow.

        Args:
            login_url: URL of login page
            username: Test username
            password: Test password
            username_selector: CSS selector for username field
            password_selector: CSS selector for password field
            submit_selector: CSS selector for submit button
            success_indicator: CSS selector indicating successful login (optional)

        Returns:
            Test results with findings
        """
        self.findings = []
        start_time = datetime.now(timezone.utc)

        try:
            # Navigate to login page
            result = await self.browser.visit(login_url)
            if not result["success"]:
                self._add_finding(
                    "Navigation Failed",
                    f"Cannot load login page: {result.get('error')}",
                    "critical",
                )
                return self._build_result("fail", start_time)

            # Check for HTTPS
            if not login_url.startswith("https://"):
                self._add_finding(
                    "Insecure Login Page", "Login page not served over HTTPS", "critical"
                )

            # Find form elements
            username_field = await self._find_element(username_selector, "Username field")
            if not username_field:
                return self._build_result("fail", start_time)

            password_field = await self._find_element(password_selector, "Password field")
            if not password_field:
                return self._build_result("fail", start_time)

            submit_button = await self._find_element(submit_selector, "Submit button")
            if not submit_button:
                return self._build_result("fail", start_time)

            # Check password field type
            password_type = await password_field.get_attribute("type")
            if password_type != "password":
                self._add_finding(
                    "Password Field Not Masked",
                    f"Password input type is '{password_type}' instead of 'password'",
                    "critical",
                )

            # Check for autocomplete
            autocomplete = await password_field.get_attribute("autocomplete")
            if autocomplete not in ["current-password", "new-password"]:
                self._add_finding(
                    "Password Autocomplete",
                    "Password field missing proper autocomplete attribute",
                    "medium",
                )

            # Fill credentials
            await self.browser.fill(username_selector, username)
            await self.browser.fill(password_selector, password)

            # Submit form
            await self.browser.click(submit_selector)

            # Wait for navigation
            await self.browser.page.wait_for_load_state("networkidle")

            # Check session cookies
            cookies = await self.browser.page.context.cookies()
            session_cookie = self._find_session_cookie(cookies)

            if session_cookie:
                self.session_data["session_cookie"] = {
                    "name": session_cookie.get("name"),
                    "httpOnly": session_cookie.get("httpOnly"),
                    "secure": session_cookie.get("secure"),
                    "sameSite": session_cookie.get("sameSite"),
                }

                # Validate cookie security
                if not session_cookie.get("httpOnly"):
                    self._add_finding(
                        "Session Cookie Not HttpOnly",
                        "Session cookie accessible to JavaScript",
                        "high",
                    )

                if not session_cookie.get("secure"):
                    self._add_finding(
                        "Session Cookie Not Secure", "Session cookie sent over HTTP", "high"
                    )

                if session_cookie.get("sameSite") not in ["Strict", "Lax"]:
                    self._add_finding(
                        "Session Cookie SameSite",
                        f"SameSite is '{session_cookie.get('sameSite')}'",
                        "medium",
                    )
            else:
                self._add_finding(
                    "No Session Cookie", "No session cookie found after login", "warning"
                )

            # Check for success
            current_url = self.browser.page.url
            logged_in = success_indicator is None or await self._check_element_exists(
                success_indicator
            )

            if logged_in and current_url != login_url:
                self._add_finding("Login Successful", f"Redirected to {current_url}", "info")

                # Check for JWT in localStorage
                local_storage = await self.browser.page.evaluate(
                    "() => JSON.stringify(localStorage)"
                )
                if "token" in local_storage.lower() or "jwt" in local_storage.lower():
                    self._add_finding(
                        "Token in localStorage",
                        "Authentication token stored in localStorage (consider httpOnly cookies)",
                        "medium",
                    )
            else:
                self._add_finding(
                    "Login May Have Failed", f"Still on or returned to {current_url}", "warning"
                )

            return self._build_result(
                (
                    "pass"
                    if not any(f["severity"] == "critical" for f in self.findings)
                    else "warning"
                ),
                start_time,
            )

        except Exception as e:
            logger.error("auth_test_error", error=str(e))
            self._add_finding("Test Error", str(e), "critical")
            return self._build_result("fail", start_time)

    async def test_logout_flow(
        self, logout_selector: Optional[str] = None, logout_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """Test logout flow."""
        start_time = datetime.now(timezone.utc)

        try:
            if logout_url:
                await self.browser.visit(logout_url)
            elif logout_selector:
                await self.browser.click(logout_selector)
                await self.browser.page.wait_for_load_state("networkidle")
            else:
                self._add_finding("No Logout Method", "No logout selector or URL provided", "info")
                return self._build_result("pass", start_time)

            # Check session cookie is removed or invalidated
            cookies = await self.browser.page.context.cookies()
            session_cookie = self._find_session_cookie(cookies)

            if session_cookie:
                self._add_finding(
                    "Session Still Active", "Session cookie present after logout", "high"
                )
            else:
                self._add_finding("Logout Successful", "Session cookie removed", "info")

            return self._build_result("pass", start_time)

        except Exception as e:
            self._add_finding("Logout Error", str(e), "high")
            return self._build_result("fail", start_time)

    async def _find_element(self, selector: str, name: str) -> Optional[Any]:
        """Find element by selector."""
        try:
            element = await self.browser.page.query_selector(selector)
            if element:
                return element
            else:
                self._add_finding(
                    f"{name} Not Found", f"Selector '{selector}' not found", "critical"
                )
                return None
        except Exception as e:
            self._add_finding(f"{name} Error", str(e), "critical")
            return None

    async def _check_element_exists(self, selector: str) -> bool:
        """Check if element exists."""
        try:
            element = await self.browser.page.query_selector(selector)
            return element is not None
        except Exception as e:
            logger.warning("element_exists_check_failed", error=str(e), selector=selector)
            return False

    def _find_session_cookie(self, cookies: List[Dict]) -> Optional[Dict]:
        """Find session cookie from list."""
        session_names = ["session", "sess", "sid", "auth", "token", "jwt"]
        for cookie in cookies:
            if any(name in cookie.get("name", "").lower() for name in session_names):
                return cookie
        return None

    def _add_finding(self, title: str, description: str, severity: str):
        """Add a finding."""
        self.findings.append(
            {
                "title": title,
                "description": description,
                "severity": severity,
                "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z",
            }
        )

    def _build_result(self, status: str, start_time: datetime) -> Dict[str, Any]:
        """Build test result."""
        elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()

        return {
            "status": status,
            "findings": self.findings,
            "session_data": self.session_data,
            "duration_seconds": elapsed,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z",
        }
