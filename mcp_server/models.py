"""
Pydantic models for input validation across the Vectra QA framework.
Ensures all tool parameters are validated before processing.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator
import validators


class BaseToolRequest(BaseModel):
    """Base class for all tool requests."""

    pass


class ReadNodeRequest(BaseToolRequest):
    """Request to read an Obsidian node."""

    node_path: str = Field(..., min_length=1, description="Relative path to the Markdown file")

    @field_validator("node_path")
    @classmethod
    def validate_path(cls, v: str) -> str:
        if v.startswith("/"):
            raise ValueError("Absolute paths not allowed")
        if ".." in v:
            raise ValueError("Path traversal not allowed")
        return v


class WriteNodeRequest(BaseToolRequest):
    """Request to write an Obsidian node."""

    node_path: str = Field(..., min_length=1, description="Relative path to the Markdown file")
    content: str = Field(..., description="Markdown content to write")
    frontmatter: Optional[Dict[str, Any]] = Field(None, description="Optional YAML frontmatter")

    @field_validator("node_path")
    @classmethod
    def validate_path(cls, v: str) -> str:
        if v.startswith("/"):
            raise ValueError("Absolute paths not allowed")
        if ".." in v:
            raise ValueError("Path traversal not allowed")
        return v


class UpdateFrontmatterRequest(BaseToolRequest):
    """Request to update frontmatter of an Obsidian node."""

    node_path: str = Field(..., min_length=1, description="Relative path to the Markdown file")
    updates: Dict[str, Any] = Field(..., description="Dictionary of frontmatter fields to update")

    @field_validator("node_path")
    @classmethod
    def validate_path(cls, v: str) -> str:
        if v.startswith("/"):
            raise ValueError("Absolute paths not allowed")
        if ".." in v:
            raise ValueError("Path traversal not allowed")
        return v


class SpawnAgentRequest(BaseToolRequest):
    """Request to spawn an agent."""

    role: str = Field(
        ...,
        pattern=r"^(ui_explorer|data_validator|auth_tester|visual_regression_tester|performance_tester|api_contract_tester|accessibility_tester|multi_browser_tester)$",
        description="Agent specialization",
    )
    objective: str = Field(
        ..., min_length=1, max_length=5000, description="Task description for the agent"
    )
    memory_node: str = Field(
        ..., min_length=1, description="Target Obsidian file path for agent logs"
    )

    @field_validator("memory_node")
    @classmethod
    def validate_memory_node(cls, v: str) -> str:
        if v.startswith("/"):
            raise ValueError("Absolute paths not allowed")
        if ".." in v:
            raise ValueError("Path traversal not allowed")
        return v

    @field_validator("objective")
    @classmethod
    def validate_objective(cls, v: str) -> str:
        # Extract and validate URL if present
        words = v.split()
        for word in words:
            if word.startswith("http"):
                url = word.strip(".,;:!?)")
                if not validators.url(url):
                    raise ValueError(f"Invalid URL in objective: {url}")
        return v


class TerminateAgentRequest(BaseToolRequest):
    """Request to terminate an agent."""

    agent_id: str = Field(..., min_length=1, description="Unique agent identifier")


class ListNodesRequest(BaseToolRequest):
    """Request to list Obsidian nodes."""

    directory: str = Field(".", description="Relative directory path")

    @field_validator("directory")
    @classmethod
    def validate_directory(cls, v: str) -> str:
        if v.startswith("/"):
            raise ValueError("Absolute paths not allowed")
        if ".." in v:
            raise ValueError("Path traversal not allowed")
        return v


class QuerySelectorRequest(BaseToolRequest):
    """Request to query DOM selector."""

    selector: str = Field(..., min_length=1, description="CSS selector string")


class SimulateInteractionRequest(BaseToolRequest):
    """Request to simulate user interaction."""

    selector: str = Field(..., min_length=1, description="CSS selector of target element")
    action: str = Field(..., pattern=r"^(click|type|hover|focus|blur)$", description="Action type")
    params: Optional[Dict[str, Any]] = Field(None, description="Additional parameters")


class InterceptNetworkRequest(BaseToolRequest):
    """Request to intercept network requests."""

    method: str = Field(..., description="HTTP method")
    url_pattern: str = Field(..., min_length=1, description="URL pattern to match")

    @field_validator("url_pattern")
    @classmethod
    def validate_url_pattern(cls, v: str) -> str:
        if v.startswith(("javascript:", "data:", "file:")):
            raise ValueError(f"Invalid URL scheme in pattern: {v}")
        return v


class TestAuthFlowRequest(BaseToolRequest):
    """Request to test authentication flow."""

    login_url: str = Field(..., description="URL of the login page")
    username: Optional[str] = Field(None, description="Username for login test")
    password: Optional[str] = Field(None, description="Password for login test")
    logout_url: Optional[str] = Field(None, description="URL of the logout page")

    @field_validator("login_url")
    @classmethod
    def validate_login_url(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("Login URL must start with http:// or https://")
        return v


class TestVisualRegressionRequest(BaseToolRequest):
    """Request to test visual regression."""

    url: str = Field(..., description="URL to capture and compare")
    name: Optional[str] = Field(None, description="Name for this baseline")


class TestPerformanceRequest(BaseToolRequest):
    """Request to test performance."""

    url: str = Field(..., description="URL to test")
    thresholds: Optional[Dict[str, Any]] = Field(None, description="Custom thresholds")


class TestAPIContractRequest(BaseToolRequest):
    """Request to test API contract."""

    base_url: str = Field(..., description="Base URL of the API")
    endpoint: str = Field(..., description="API endpoint path")
    method: str = Field(..., pattern=r"^(GET|POST|PUT|DELETE|PATCH)$", description="HTTP method")
    schema_path: Optional[str] = Field(None, description="Path to OpenAPI schema file")
    body: Optional[Dict[str, Any]] = Field(None, description="Request body")


class TestAccessibilityRequest(BaseToolRequest):
    """Request to test accessibility."""

    url: str = Field(..., description="URL to test")
    standard: Optional[str] = Field(
        "wcag2aa", pattern=r"^(wcag2a|wcag2aa|wcag21aa)$", description="WCAG standard"
    )


class TestMultiBrowserRequest(BaseToolRequest):
    """Request to test across multiple browsers."""

    url: str = Field(..., description="URL to test")


# Request mapping for tool validation
REQUEST_MODELS = {
    "read_obsidian_node": ReadNodeRequest,
    "write_obsidian_node": WriteNodeRequest,
    "update_frontmatter": UpdateFrontmatterRequest,
    "spawn_agent": SpawnAgentRequest,
    "terminate_agent": TerminateAgentRequest,
    "list_obsidian_nodes": ListNodesRequest,
    "query_selector": QuerySelectorRequest,
    "simulate_interaction": SimulateInteractionRequest,
    "intercept_network_request": InterceptNetworkRequest,
    "test_auth_flow": TestAuthFlowRequest,
    "test_visual_regression": TestVisualRegressionRequest,
    "test_performance": TestPerformanceRequest,
    "test_api_contract": TestAPIContractRequest,
    "test_accessibility": TestAccessibilityRequest,
    "test_multi_browser": TestMultiBrowserRequest,
}
