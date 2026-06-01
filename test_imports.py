#!/usr/bin/env python3
"""
Quick Docker import test - verifies all imports work correctly in container context.
Run this locally to test before building Docker images.
"""

import sys
import os

# Simulate Docker environment
os.environ.setdefault("PYTHONPATH", "/app")
os.environ.setdefault("OBSIDIAN_VAULT_PATH", "/app/obsidian_vault")

# Add parent dir to path (simulates /app in Docker)
sys.path.insert(0, str(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def test_mcp_server_imports():
    """Test MCP server module imports."""
    print("Testing MCP Server imports...")
    try:
        from mcp_server.tools import execute_tool, vault, spawner, TOOLS  # noqa: F401

        print("  ✓ mcp_server.tools imported successfully")
        print(f"    - Vault path: {vault.vault_path}")
        print(f"    - Tools count: {len(TOOLS)}")
    except ImportError as e:
        print(f"  ✗ Failed to import mcp_server.tools: {e}")
        return False

    try:
        from mcp_server.server import MCPServer  # noqa: F401

        print("  ✓ mcp_server.server imported successfully")
    except ImportError as e:
        print(f"  ✗ Failed to import mcp_server.server: {e}")
        return False

    try:
        from mcp_server.llm_router import LLMRouter  # noqa: F401

        print("  ✓ mcp_server.llm_router imported successfully")
    except ImportError as e:
        print(f"  ✗ Failed to import mcp_server.llm_router: {e}")
        return False

    return True


def test_command_center_imports():
    """Test Command Center module imports."""
    print("\nTesting Command Center imports...")
    try:
        from command_center.obsidian_reader import reader, ObsidianReader  # noqa: F401

        print("  ✓ command_center.obsidian_reader imported successfully")
        print(f"    - Reader vault path: {reader.vault_path}")
    except ImportError as e:
        print(f"  ✗ Failed to import command_center.obsidian_reader: {e}")
        return False

    try:
        # Don't actually import main - it starts the server
        # Just check the file exists and is importable
        import importlib.util

        spec = importlib.util.find_spec("command_center.main")
        if spec:
            print("  ✓ command_center.main found")
        else:
            print("  ✗ command_center.main not found")
            return False
    except Exception as e:
        print(f"  ✗ Failed to locate command_center.main: {e}")
        return False

    return True


def main():
    """Run all import tests."""
    print("=" * 60)
    print("Docker Import Path Verification")
    print("=" * 60)
    print(f"Python path: {sys.path[0]}")
    print(f"Obsidian vault path: {os.getenv('OBSIDIAN_VAULT_PATH')}")
    print()

    mcp_ok = test_mcp_server_imports()
    cc_ok = test_command_center_imports()

    print("\n" + "=" * 60)
    if mcp_ok and cc_ok:
        print("✓ All imports successful! Docker should build correctly.")
        return 0
    else:
        print("✗ Some imports failed. Check the errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
