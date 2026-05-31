"""
Unit tests for wired-up browser MCP tools.
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch

from mcp_server.tools import TOOLS, execute_tool
import mcp_server.tools as tools_module


@pytest.fixture(autouse=True)
def reset_browser_instance():
    """Reset browser instance before each test."""
    original = getattr(tools_module, "_browser_instance", None)
    tools_module._browser_instance = None
    yield
    tools_module._browser_instance = original


class TestQuerySelectorTool:
    """Test query_selector MCP tool."""

    def test_query_selector_with_browser(self):
        """Should query DOM when browser is available."""
        mock_element = AsyncMock()
        mock_element.is_visible.return_value = True

        mock_page = AsyncMock()
        mock_page.query_selector_all.return_value = [mock_element, mock_element]

        mock_browser = Mock()
        mock_browser.page = mock_page
        mock_browser.network_logs = []

        with patch.object(tools_module, "_get_browser", return_value=mock_browser):
            result = execute_tool("query_selector", {"selector": ".btn"})

            assert result["status"] == "success"
            assert result["result"]["matches"] == 2
            assert result["result"]["visible"] == 2


class TestSimulateInteractionTool:
    """Test simulate_interaction MCP tool."""

    def test_click_action(self):
        """Should simulate click."""
        mock_page = AsyncMock()
        mock_page.click.return_value = None
        mock_page.wait_for_load_state.return_value = None
        mock_page.url = "https://example.com"

        mock_browser = Mock()
        mock_browser.page = mock_page
        mock_browser.network_logs = []

        with patch.object(tools_module, "_get_browser", return_value=mock_browser):
            result = execute_tool(
                "simulate_interaction", {"selector": "#submit", "action": "click"}
            )

            assert result["status"] == "success"
            assert result["result"]["action"] == "click"

    def test_type_action(self):
        """Should simulate typing."""
        mock_page = AsyncMock()
        mock_page.fill.return_value = None
        mock_page.url = "https://example.com"

        mock_browser = Mock()
        mock_browser.page = mock_page
        mock_browser.network_logs = []

        with patch.object(tools_module, "_get_browser", return_value=mock_browser):
            result = execute_tool(
                "simulate_interaction",
                {"selector": "#email", "action": "type", "params": {"text": "test@example.com"}},
            )

            assert result["status"] == "success"


class TestInterceptNetworkTool:
    """Test intercept_network_request MCP tool."""

    def test_intercept_network(self):
        """Should return network interception status."""
        mock_browser = Mock()
        mock_browser.network_logs = [{"url": "https://api.example.com/data", "status": 200}]
        mock_browser.page = Mock()

        with patch.object(tools_module, "_get_browser", return_value=mock_browser):
            result = execute_tool(
                "intercept_network_request", {"method": "GET", "url_pattern": "/api/*"}
            )

            assert result["status"] == "success"
            assert result["result"]["status"] == "intercepting"
            assert result["result"]["network_logs_count"] == 1
