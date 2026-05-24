#!/bin/bash
# Docker Build Verification Script
# Run this to verify the Docker setup before deploying

set -e

echo "=========================================="
echo "Vectra QA Docker Verification"
echo "=========================================="
echo ""

# Check Docker is installed
if ! command -v docker &> /dev/null; then
    echo "✗ Docker is not installed"
    exit 1
fi
echo "✓ Docker installed"

# Check Docker Compose
if ! docker compose version &> /dev/null; then
    echo "✗ Docker Compose is not installed"
    exit 1
fi
echo "✓ Docker Compose installed"

# Check .env file exists
if [ ! -f .env ]; then
    echo "✗ .env file not found. Copy .env.example to .env and configure it."
    exit 1
fi
echo "✓ .env file exists"

# Check required Python files exist
echo ""
echo "Checking source files..."

required_files=(
    "mcp_server/__init__.py"
    "mcp_server/server.py"
    "mcp_server/tools.py"
    "mcp_server/llm_router.py"
    "command_center/__init__.py"
    "command_center/main.py"
    "command_center/obsidian_reader.py"
    "docker/Dockerfile.mcp"
    "docker/Dockerfile.dashboard"
    "docker-compose.yml"
)

for file in "${required_files[@]}"; do
    if [ -f "$file" ]; then
        echo "  ✓ $file"
    else
        echo "  ✗ $file NOT FOUND"
        exit 1
    fi
done

# Verify imports are correct
echo ""
echo "Checking import statements..."

if grep -q "from tools import" mcp_server/server.py; then
    echo "  ✗ mcp_server/server.py still has old import: from tools import"
    exit 1
fi
echo "  ✓ mcp_server/server.py imports fixed"

if grep -q "from obsidian_reader import" command_center/main.py; then
    echo "  ✗ command_center/main.py still has old import: from obsidian_reader import"
    exit 1
fi
echo "  ✓ command_center/main.py imports fixed"

# Check for hardcoded paths
echo ""
echo "Checking for hardcoded paths..."

if grep -r "/home/bugra/Documents/projects/vectra-qa" --include="*.py" .; then
    echo "  ✗ Found hardcoded paths in Python files"
    exit 1
fi
echo "  ✓ No hardcoded paths found"

# Check for nested event loop issue
echo ""
echo "Checking for nested event loop issue..."

if grep -q "asyncio.run(server.run_sse" mcp_server/server.py; then
    echo "  ✗ Found nested event loop: asyncio.run(server.run_sse)"
    echo "    This causes RuntimeError in Docker containers"
    exit 1
fi

if grep -q "async def run_sse" mcp_server/server.py; then
    echo "  ✗ Found async def run_sse - should be regular def"
    echo "    Uvicorn manages its own event loop"
    exit 1
fi

echo "  ✓ No nested event loop issue found"

# Check static files path
echo ""
echo "Checking static files path..."

if grep -q 'StaticFiles(directory="static")' command_center/main.py; then
    echo "  ✗ Found incorrect static path: directory='static'"
    echo "    Should be 'command_center/static' for Docker container"
    exit 1
fi

echo "  ✓ Static files path correct"

# Check vault watcher keep-alive
echo ""
echo "Checking vault watcher keep-alive..."

if ! grep -q 'while True:' command_center/obsidian_reader.py; then
    echo "  ✗ Vault watcher missing keep-alive loop"
    echo "    Will exit immediately in Docker container"
    exit 1
fi

echo "  ✓ Vault watcher keep-alive loop present"

# Test Python imports (locally, if Python is available)
if command -v python3 &> /dev/null; then
    echo ""
    echo "Testing Python imports..."
    if python3 test_imports.py; then
        echo "  ✓ Import test passed"
    else
        echo "  ⚠ Import test failed (this may be OK if dependencies aren't installed locally)"
    fi
fi

echo ""
echo "=========================================="
echo "✓ Verification complete! Ready to build."
echo ""
echo "Next steps:"
echo "  1. Ensure .env is configured with API keys"
echo "  2. Run: docker compose up --build"
echo "  3. Open: http://localhost:3000"
echo "=========================================="