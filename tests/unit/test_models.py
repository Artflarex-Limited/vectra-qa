"""
Unit tests for Pydantic input validation models.
"""

import pytest
from pydantic import ValidationError
from mcp_server.models import (
    ReadNodeRequest,
    WriteNodeRequest,
    SpawnAgentRequest,
    SimulateInteractionRequest,
    InterceptNetworkRequest,
)


class TestReadNodeRequest:
    """Test ReadNodeRequest validation."""

    def test_valid_path(self):
        """Should accept valid relative paths."""
        req = ReadNodeRequest(node_path="test.md")
        assert req.node_path == "test.md"

    def test_absolute_path_rejected(self):
        """Should reject absolute paths."""
        with pytest.raises(ValidationError):
            ReadNodeRequest(node_path="/etc/passwd")

    def test_path_traversal_rejected(self):
        """Should reject path traversal."""
        with pytest.raises(ValidationError):
            ReadNodeRequest(node_path="../outside.md")

    def test_empty_path_rejected(self):
        """Should reject empty paths."""
        with pytest.raises(ValidationError):
            ReadNodeRequest(node_path="")


class TestWriteNodeRequest:
    """Test WriteNodeRequest validation."""

    def test_valid_write(self):
        """Should accept valid write request."""
        req = WriteNodeRequest(node_path="test.md", content="# Test", frontmatter={"title": "Test"})
        assert req.node_path == "test.md"
        assert req.content == "# Test"

    def test_missing_content(self):
        """Should reject missing content."""
        with pytest.raises(ValidationError):
            WriteNodeRequest(node_path="test.md")


class TestSpawnAgentRequest:
    """Test SpawnAgentRequest validation."""

    def test_valid_spawn(self):
        """Should accept valid spawn request."""
        req = SpawnAgentRequest(
            role="ui_explorer",
            objective="Test the homepage at https://example.com",
            memory_node="Runs/Test.md",
        )
        assert req.role == "ui_explorer"

    def test_invalid_role(self):
        """Should reject invalid role."""
        with pytest.raises(ValidationError):
            SpawnAgentRequest(
                role="invalid_role", objective="Test something", memory_node="Runs/Test.md"
            )

    def test_url_validation(self):
        """Should validate URLs in objective."""
        with pytest.raises(ValidationError):
            SpawnAgentRequest(
                role="ui_explorer",
                objective="Test at http://not-a-valid-url",
                memory_node="Runs/Test.md",
            )

    def test_objective_too_long(self):
        """Should reject overly long objectives."""
        with pytest.raises(ValidationError):
            SpawnAgentRequest(role="ui_explorer", objective="x" * 5001, memory_node="Runs/Test.md")


class TestSimulateInteractionRequest:
    """Test SimulateInteractionRequest validation."""

    def test_valid_click(self):
        """Should accept valid click action."""
        req = SimulateInteractionRequest(selector="#btn", action="click")
        assert req.action == "click"

    def test_invalid_action(self):
        """Should reject invalid action."""
        with pytest.raises(ValidationError):
            SimulateInteractionRequest(selector="#btn", action="invalid")


class TestInterceptNetworkRequest:
    """Test InterceptNetworkRequest validation."""

    def test_valid_pattern(self):
        """Should accept valid URL pattern."""
        req = InterceptNetworkRequest(method="GET", url_pattern="/api/*")
        assert req.method == "GET"

    def test_javascript_scheme_rejected(self):
        """Should reject javascript: URLs."""
        with pytest.raises(ValidationError):
            InterceptNetworkRequest(method="GET", url_pattern="javascript:alert(1)")
