"""
Shared test fixtures and configuration for Vectra QA test suite.
"""

import os
import sys
import pytest
import tempfile
import shutil
from pathlib import Path
from datetime import datetime, timezone

# Add project root to Python path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from mcp_server.tools import ObsidianVault, AgentSpawner


@pytest.fixture
def temp_vault_path():
    """Create a temporary vault directory for testing."""
    temp_dir = tempfile.mkdtemp(prefix="vectra_test_vault_")
    yield Path(temp_dir)
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def vault(temp_vault_path):
    """Create an ObsidianVault instance with a temporary directory."""
    return ObsidianVault(temp_vault_path)


@pytest.fixture
def sample_node_content():
    """Return a sample markdown node with YAML frontmatter."""
    return {
        "path": "test_node.md",
        "frontmatter": {
            "title": "Test Node",
            "created": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z",
            "tags": ["test", "sample"],
        },
        "content": "# Test Content\n\nThis is a test node.\n\n## Section 1\n\nSome content here.",
    }


@pytest.fixture
def agent_spawner(vault):
    """Create an AgentSpawner instance with a test vault."""
    return AgentSpawner(vault)


@pytest.fixture(autouse=True)
def setup_test_env():
    """Set up environment variables for testing."""
    os.environ.setdefault("LOG_LEVEL", "DEBUG")
    yield
