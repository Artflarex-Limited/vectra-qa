"""PostgreSQL mock fixtures for integration tests."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def mock_db_manager():
    """Create a mocked DatabaseManager instance."""
    with patch("mcp_server.db.get_db_manager_sync") as mock:
        db = MagicMock()
        db._initialized = True
        db.execute = AsyncMock(return_value=True)
        db.fetchone = AsyncMock(return_value=None)
        db.fetchall = AsyncMock(return_value=[])
        db.initialize = AsyncMock(return_value=True)
        db.close = AsyncMock(return_value=True)
        mock.return_value = db
        yield mock


@pytest.fixture
def mock_browser():
    """Create a mocked BrowserAutomation instance."""
    with patch("mcp_server.resource_manager.BrowserAutomation") as mock:
        browser = MagicMock()
        browser.page = MagicMock()
        browser.browser = MagicMock()
        browser.browser.is_connected = MagicMock(return_value=True)
        browser.start = AsyncMock()
        browser.close = AsyncMock()
        browser.navigate = AsyncMock()
        mock.return_value = browser
        yield mock


@pytest.fixture
def sample_llm_response():
    """Return a sample LLMResponse for testing."""
    from mcp_server.llm_router import LLMResponse
    return LLMResponse(
        content="Test response",
        model="gpt-4o",
        provider="openai",
        usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        raw_response=None,
    )
