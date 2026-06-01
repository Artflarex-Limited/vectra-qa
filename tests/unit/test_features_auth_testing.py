"""
Unit tests for mcp_server/features/auth_testing.py.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock

from mcp_server.features.auth_testing import AuthFlowTester


@pytest.mark.unit
class TestAuthFlowTester:
    """Tests for AuthFlowTester."""

    @pytest.fixture
    def mock_browser(self):
        browser = Mock()
        browser.page = AsyncMock()
        browser.visit = AsyncMock(return_value={"success": True, "status": 200})
        browser.fill = AsyncMock(return_value={"success": True})
        browser.click = AsyncMock(return_value={"success": True})
        return browser

    @pytest.fixture
    def tester(self, mock_browser):
        return AuthFlowTester(mock_browser)

    def test_init(self, mock_browser):
        """Should initialize with browser and empty findings."""
        tester = AuthFlowTester(mock_browser)
        assert tester.browser == mock_browser
        assert tester.findings == []
        assert tester.session_data == {}

    @pytest.mark.asyncio
    async def test_login_flow_success(self, tester, mock_browser):
        """Should test login flow successfully."""
        mock_element = AsyncMock()
        mock_element.get_attribute.side_effect = ["password", "current-password"]

        mock_browser.page.query_selector = AsyncMock(return_value=mock_element)
        mock_browser.page.context.cookies = AsyncMock(
            return_value=[
                {
                    "name": "session_id",
                    "httpOnly": True,
                    "secure": True,
                    "sameSite": "Strict",
                }
            ]
        )
        mock_browser.page.url = "https://example.com/dashboard"
        mock_browser.page.evaluate = AsyncMock(return_value="{}")
        mock_browser.page.wait_for_load_state = AsyncMock()

        result = await tester.test_login_flow(
            login_url="https://example.com/login",
            username="test@example.com",
            password="password123",
        )

        assert result["status"] == "pass"
        assert len(result["findings"]) > 0
        assert result["session_data"]["session_cookie"]["httpOnly"] is True
        assert result["session_data"]["session_cookie"]["secure"] is True
        mock_browser.visit.assert_awaited_once_with("https://example.com/login")
        mock_browser.fill.assert_awaited()
        mock_browser.click.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_login_flow_navigation_failure(self, tester, mock_browser):
        """Should fail when navigation fails."""
        mock_browser.visit = AsyncMock(return_value={"success": False, "error": "Timeout"})

        result = await tester.test_login_flow(
            login_url="https://example.com/login",
            username="test",
            password="pass",
        )

        assert result["status"] == "fail"
        assert any("Navigation Failed" in f["title"] for f in result["findings"])

    @pytest.mark.asyncio
    async def test_login_flow_insecure_http(self, tester, mock_browser):
        """Should flag insecure HTTP login page."""
        mock_element = AsyncMock()
        mock_element.get_attribute.side_effect = ["password", "current-password"]

        mock_browser.page.query_selector = AsyncMock(return_value=mock_element)
        mock_browser.page.context.cookies = AsyncMock(return_value=[])
        mock_browser.page.url = "http://example.com/login"
        mock_browser.page.evaluate = AsyncMock(return_value="{}")
        mock_browser.page.wait_for_load_state = AsyncMock()

        result = await tester.test_login_flow(
            login_url="http://example.com/login",
            username="test",
            password="pass",
        )

        assert any("Insecure Login Page" in f["title"] for f in result["findings"])
        assert any(f["severity"] == "critical" for f in result["findings"])

    @pytest.mark.asyncio
    async def test_login_flow_password_not_masked(self, tester, mock_browser):
        """Should flag password field not masked."""
        mock_element = AsyncMock()
        mock_element.get_attribute.side_effect = ["text", "current-password"]

        mock_browser.page.query_selector = AsyncMock(return_value=mock_element)
        mock_browser.page.context.cookies = AsyncMock(return_value=[])
        mock_browser.page.url = "https://example.com/dashboard"
        mock_browser.page.evaluate = AsyncMock(return_value="{}")
        mock_browser.page.wait_for_load_state = AsyncMock()

        result = await tester.test_login_flow(
            login_url="https://example.com/login",
            username="test",
            password="pass",
        )

        assert any(
            "Password Field Not Masked" in f["title"] for f in result["findings"]
        )

    @pytest.mark.asyncio
    async def test_login_flow_weak_autocomplete(self, tester, mock_browser):
        """Should flag weak password autocomplete."""
        mock_element = AsyncMock()
        mock_element.get_attribute.side_effect = ["password", "off"]

        mock_browser.page.query_selector = AsyncMock(return_value=mock_element)
        mock_browser.page.context.cookies = AsyncMock(return_value=[])
        mock_browser.page.url = "https://example.com/dashboard"
        mock_browser.page.evaluate = AsyncMock(return_value="{}")
        mock_browser.page.wait_for_load_state = AsyncMock()

        result = await tester.test_login_flow(
            login_url="https://example.com/login",
            username="test",
            password="pass",
        )

        assert any(
            "Password Autocomplete" in f["title"] for f in result["findings"]
        )

    @pytest.mark.asyncio
    async def test_login_flow_no_username_field(self, tester, mock_browser):
        """Should fail when username field not found."""
        mock_browser.page.query_selector = AsyncMock(return_value=None)

        result = await tester.test_login_flow(
            login_url="https://example.com/login",
            username="test",
            password="pass",
        )

        assert result["status"] == "fail"
        assert any("Username field Not Found" in f["title"] for f in result["findings"])

    @pytest.mark.asyncio
    async def test_login_flow_no_password_field(self, tester, mock_browser):
        """Should fail when password field not found."""
        mock_element = AsyncMock()
        mock_browser.page.query_selector = AsyncMock(side_effect=[mock_element, None, None])

        result = await tester.test_login_flow(
            login_url="https://example.com/login",
            username="test",
            password="pass",
        )

        assert result["status"] == "fail"
        assert any("Password field Not Found" in f["title"] for f in result["findings"])

    @pytest.mark.asyncio
    async def test_login_flow_no_submit_button(self, tester, mock_browser):
        """Should fail when submit button not found."""
        mock_element = AsyncMock()
        mock_browser.page.query_selector = AsyncMock(
            side_effect=[mock_element, mock_element, None]
        )

        result = await tester.test_login_flow(
            login_url="https://example.com/login",
            username="test",
            password="pass",
        )

        assert result["status"] == "fail"
        assert any("Submit button Not Found" in f["title"] for f in result["findings"])

    @pytest.mark.asyncio
    async def test_login_flow_insecure_cookie(self, tester, mock_browser):
        """Should flag insecure session cookies."""
        mock_element = AsyncMock()
        mock_element.get_attribute.side_effect = ["password", "current-password"]

        mock_browser.page.query_selector = AsyncMock(return_value=mock_element)
        mock_browser.page.context.cookies = AsyncMock(
            return_value=[
                {
                    "name": "session",
                    "httpOnly": False,
                    "secure": False,
                    "sameSite": "None",
                }
            ]
        )
        mock_browser.page.url = "https://example.com/dashboard"
        mock_browser.page.evaluate = AsyncMock(return_value="{}")
        mock_browser.page.wait_for_load_state = AsyncMock()

        result = await tester.test_login_flow(
            login_url="https://example.com/login",
            username="test",
            password="pass",
        )

        assert any(
            "Session Cookie Not HttpOnly" in f["title"] for f in result["findings"]
        )
        assert any(
            "Session Cookie Not Secure" in f["title"] for f in result["findings"]
        )
        assert any("Session Cookie SameSite" in f["title"] for f in result["findings"])

    @pytest.mark.asyncio
    async def test_login_flow_no_session_cookie(self, tester, mock_browser):
        """Should warn when no session cookie found."""
        mock_element = AsyncMock()
        mock_element.get_attribute.side_effect = ["password", "current-password"]

        mock_browser.page.query_selector = AsyncMock(return_value=mock_element)
        mock_browser.page.context.cookies = AsyncMock(return_value=[])
        mock_browser.page.url = "https://example.com/dashboard"
        mock_browser.page.evaluate = AsyncMock(return_value="{}")
        mock_browser.page.wait_for_load_state = AsyncMock()

        result = await tester.test_login_flow(
            login_url="https://example.com/login",
            username="test",
            password="pass",
        )

        assert any("No Session Cookie" in f["title"] for f in result["findings"])

    @pytest.mark.asyncio
    async def test_login_flow_token_in_localstorage(self, tester, mock_browser):
        """Should detect JWT token in localStorage."""
        mock_element = AsyncMock()
        mock_element.get_attribute.side_effect = ["password", "current-password"]

        mock_browser.page.query_selector = AsyncMock(return_value=mock_element)
        mock_browser.page.context.cookies = AsyncMock(
            return_value=[
                {"name": "session", "httpOnly": True, "secure": True, "sameSite": "Strict"}
            ]
        )
        mock_browser.page.url = "https://example.com/dashboard"
        mock_browser.page.evaluate = AsyncMock(return_value='{"token": "abc123"}')
        mock_browser.page.wait_for_load_state = AsyncMock()

        result = await tester.test_login_flow(
            login_url="https://example.com/login",
            username="test",
            password="pass",
        )

        assert any("Token in localStorage" in f["title"] for f in result["findings"])

    @pytest.mark.asyncio
    async def test_login_flow_success_indicator(self, tester, mock_browser):
        """Should use success indicator when provided."""
        mock_element = AsyncMock()
        mock_element.get_attribute.side_effect = ["password", "current-password"]

        mock_browser.page.query_selector = AsyncMock(return_value=mock_element)
        mock_browser.page.context.cookies = AsyncMock(return_value=[])
        mock_browser.page.url = "https://example.com/dashboard"
        mock_browser.page.evaluate = AsyncMock(return_value="{}")
        mock_browser.page.wait_for_load_state = AsyncMock()

        result = await tester.test_login_flow(
            login_url="https://example.com/login",
            username="test",
            password="pass",
            success_indicator="#welcome-message",
        )

        assert any("Login Successful" in f["title"] for f in result["findings"])

    @pytest.mark.asyncio
    async def test_login_flow_login_failed(self, tester, mock_browser):
        """Should detect failed login."""
        mock_element = AsyncMock()
        mock_element.get_attribute.side_effect = ["password", "current-password"]

        mock_browser.page.query_selector = AsyncMock(return_value=mock_element)
        mock_browser.page.context.cookies = AsyncMock(return_value=[])
        mock_browser.page.url = "https://example.com/login"  # Same URL = not redirected
        mock_browser.page.evaluate = AsyncMock(return_value="{}")
        mock_browser.page.wait_for_load_state = AsyncMock()

        result = await tester.test_login_flow(
            login_url="https://example.com/login",
            username="test",
            password="wrong",
        )

        assert any("Login May Have Failed" in f["title"] for f in result["findings"])

    @pytest.mark.asyncio
    async def test_login_flow_exception(self, tester, mock_browser):
        """Should handle exceptions during login flow."""
        mock_browser.visit = AsyncMock(side_effect=Exception("Browser crash"))

        result = await tester.test_login_flow(
            login_url="https://example.com/login",
            username="test",
            password="pass",
        )

        assert result["status"] == "fail"
        assert any("Test Error" in f["title"] for f in result["findings"])

    @pytest.mark.asyncio
    async def test_logout_flow_with_url(self, tester, mock_browser):
        """Should test logout via URL."""
        mock_browser.page.context.cookies = AsyncMock(return_value=[])

        result = await tester.test_logout_flow(logout_url="https://example.com/logout")

        assert result["status"] == "pass"
        assert any("Logout Successful" in f["title"] for f in result["findings"])
        mock_browser.visit.assert_awaited_once_with("https://example.com/logout")

    @pytest.mark.asyncio
    async def test_logout_flow_with_selector(self, tester, mock_browser):
        """Should test logout via selector."""
        mock_browser.page.context.cookies = AsyncMock(return_value=[])
        mock_browser.page.wait_for_load_state = AsyncMock()

        result = await tester.test_logout_flow(logout_selector="#logout-btn")

        assert result["status"] == "pass"
        mock_browser.click.assert_awaited_once_with("#logout-btn")

    @pytest.mark.asyncio
    async def test_logout_flow_session_still_active(self, tester, mock_browser):
        """Should flag session still active after logout."""
        mock_browser.page.context.cookies = AsyncMock(
            return_value=[{"name": "session_id"}]
        )

        result = await tester.test_logout_flow(logout_url="https://example.com/logout")

        assert any("Session Still Active" in f["title"] for f in result["findings"])
        assert any(f["severity"] == "high" for f in result["findings"])

    @pytest.mark.asyncio
    async def test_logout_flow_no_method(self, tester):
        """Should pass when no logout method provided."""
        result = await tester.test_logout_flow()

        assert result["status"] == "pass"
        assert any("No Logout Method" in f["title"] for f in result["findings"])

    @pytest.mark.asyncio
    async def test_logout_flow_exception(self, tester, mock_browser):
        """Should handle exceptions during logout."""
        mock_browser.visit = AsyncMock(side_effect=Exception("Network error"))

        result = await tester.test_logout_flow(logout_url="https://example.com/logout")

        assert result["status"] == "fail"
        assert any("Logout Error" in f["title"] for f in result["findings"])

    def test_find_session_cookie(self, tester):
        """Should find session cookies by name patterns."""
        cookies = [
            {"name": "random", "value": "x"},
            {"name": "session_id", "value": "abc"},
            {"name": "jwt_token", "value": "def"},
        ]

        result = tester._find_session_cookie(cookies)
        assert result is not None
        assert result["name"] == "session_id"

        # Test with sid
        result = tester._find_session_cookie([{"name": "sid", "value": "x"}])
        assert result["name"] == "sid"

        # Test no match
        result = tester._find_session_cookie([{"name": "analytics", "value": "x"}])
        assert result is None

    def test_add_finding(self, tester):
        """Should add findings with timestamp."""
        tester._add_finding("Test Finding", "Description", "high")

        assert len(tester.findings) == 1
        assert tester.findings[0]["title"] == "Test Finding"
        assert tester.findings[0]["description"] == "Description"
        assert tester.findings[0]["severity"] == "high"
        assert "timestamp" in tester.findings[0]

    def test_build_result(self, tester):
        """Should build result with correct structure."""
        start = datetime.now(timezone.utc)
        result = tester._build_result("pass", start)

        assert result["status"] == "pass"
        assert result["findings"] == []
        assert "session_data" in result
        assert "duration_seconds" in result
        assert "timestamp" in result

    @pytest.mark.asyncio
    async def test_find_element_exception(self, tester, mock_browser):
        """Should handle element query exceptions."""
        mock_browser.page.query_selector = AsyncMock(side_effect=Exception("DOM error"))

        result = await tester._find_element("#bad", "Test Element")
        assert result is None
        assert any("Test Element Error" in f["title"] for f in tester.findings)

    @pytest.mark.asyncio
    async def test_check_element_exists_true(self, tester, mock_browser):
        """Should return True when element exists."""
        mock_browser.page.query_selector = AsyncMock(return_value=Mock())

        result = await tester._check_element_exists("#exists")
        assert result is True

    @pytest.mark.asyncio
    async def test_check_element_exists_false(self, tester, mock_browser):
        """Should return False when element does not exist."""
        mock_browser.page.query_selector = AsyncMock(return_value=None)

        result = await tester._check_element_exists("#missing")
        assert result is False

    @pytest.mark.asyncio
    async def test_check_element_exists_exception(self, tester, mock_browser):
        """Should return False on element check exception."""
        mock_browser.page.query_selector = AsyncMock(side_effect=Exception("DOM error"))

        result = await tester._check_element_exists("#bad")
        assert result is False
