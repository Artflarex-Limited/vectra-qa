#!/usr/bin/env python3
"""
Environment validation script for Vectra QA.

Run this before starting the framework to ensure all dependencies
and configurations are correct.

Usage:
    python scripts/validate_env.py
"""

import os
import sys
from pathlib import Path


def check_env_var(name: str, required: bool = True, example: str = "") -> bool:
    """Check if an environment variable is set."""
    value = os.getenv(name)
    if not value:
        if required:
            print(f"  ❌ {name}: MISSING (Required)")
            if example:
                print(f"     Example: {example}")
            return False
        else:
            print(f"  ⚠️  {name}: Not set (Optional)")
            return True
    
    # Mask sensitive values
    display_value = value
    if any(keyword in name.lower() for keyword in ["key", "secret", "password", "token"]):
        display_value = value[:8] + "..." if len(value) > 8 else "***"
    
    print(f"  ✅ {name}: {display_value}")
    return True


def check_directory(path: str, writable: bool = True) -> bool:
    """Check if a directory exists and is writable."""
    p = Path(path)
    
    if not p.exists():
        print(f"  ❌ Directory does not exist: {path}")
        return False
    
    if not p.is_dir():
        print(f"  ❌ Not a directory: {path}")
        return False
    
    if writable:
        try:
            test_file = p / ".write_test"
            test_file.write_text("test")
            test_file.unlink()
            print(f"  ✅ Directory exists and writable: {path}")
            return True
        except Exception as e:
            print(f"  ❌ Directory not writable: {path} ({e})")
            return False
    
    print(f"  ✅ Directory exists: {path}")
    return True


def check_python_package(package: str) -> bool:
    """Check if a Python package is installed."""
    try:
        __import__(package)
        print(f"  ✅ Package installed: {package}")
        return True
    except ImportError:
        print(f"  ❌ Package not installed: {package}")
        return False


def check_playwright_browsers() -> bool:
    """Check if Playwright browsers are installed."""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            # Try to launch chromium
            browser = p.chromium.launch()
            browser.close()
            print(f"  ✅ Playwright Chromium browser installed")
            return True
    except Exception as e:
        print(f"  ❌ Playwright browser not available: {e}")
        print(f"     Run: playwright install chromium")
        return False


def check_llm_connectivity() -> bool:
    """Check if at least one LLM provider is configured."""
    providers = [
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GOOGLE_API_KEY",
        "MINIMAX_API_KEY",
        "KIMI_API_KEY",
        "LOCAL_LLM_BASE_URL"
    ]
    
    configured = [p for p in providers if os.getenv(p)]
    
    if configured:
        print(f"  ✅ LLM providers configured: {len(configured)}")
        for p in configured:
            print(f"     - {p}")
        return True
    else:
        print(f"  ❌ No LLM providers configured")
        print(f"     Set at least one of: {', '.join(providers)}")
        return False


def main():
    """Run all validation checks."""
    print("=" * 60)
    print("VECTRA QA - Environment Validation")
    print("=" * 60)
    
    all_passed = True
    
    # Check required environment variables
    print("\n📋 Required Configuration:")
    all_passed &= check_env_var("OBSIDIAN_VAULT_PATH", required=True, example="/path/to/vault")
    
    print("\n🔑 LLM Providers (at least one required):")
    all_passed &= check_llm_connectivity()
    
    print("\n⚙️  Optional Configuration:")
    check_env_var("ORCHESTRATOR_MODEL", required=False, example="openai/gpt-4o")
    check_env_var("UI_EXPLORER_MODEL", required=False, example="anthropic/claude-3-5-sonnet")
    check_env_var("DATA_VALIDATOR_MODEL", required=False, example="openai/gpt-4o")
    check_env_var("MCP_SERVER_PORT", required=False, example="8080")
    check_env_var("COMMAND_CENTER_PORT", required=False, example="3000")
    check_env_var("VECTRA_MAX_BROWSERS", required=False, example="10")
    check_env_var("VECTRA_MAX_AGENT_DURATION", required=False, example="600")
    
    # Check directories
    print("\n📁 Directories:")
    vault_path = os.getenv("OBSIDIAN_VAULT_PATH")
    if vault_path:
        all_passed &= check_directory(vault_path)
    
    # Check Python packages
    print("\n📦 Python Packages:")
    packages = [
        "fastapi",
        "uvicorn",
        "httpx",
        "playwright",
        "pyyaml",
        "watchdog",
        "pydantic",
        "tenacity",
        "filelock",
        "structlog",
        "validators"
    ]
    
    for package in packages:
        all_passed &= check_python_package(package)
    
    # Check Playwright browsers
    print("\n🌐 Playwright Browsers:")
    all_passed &= check_playwright_browsers()
    
    # Summary
    print("\n" + "=" * 60)
    if all_passed:
        print("✅ All checks passed! Environment is ready.")
        print("\nYou can now start Vectra QA:")
        print("  python mcp_server/server.py --transport sse")
        return 0
    else:
        print("❌ Some checks failed. Please fix the issues above.")
        print("\nQuick start:")
        print("  1. Copy .env.example to .env")
        print("  2. Fill in your API keys")
        print("  3. Create the vault directory")
        print("  4. Install dependencies: pip install -r requirements.txt")
        print("  5. Install browsers: playwright install chromium")
        return 1


if __name__ == "__main__":
    sys.exit(main())
