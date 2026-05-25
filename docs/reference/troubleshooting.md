# Troubleshooting

Common issues and their solutions.

## Installation Issues

### Docker Won't Start

**Symptom**: `docker compose up` fails with errors

**Solutions**:
```bash
# Check Docker is running
docker ps

# Check ports are available
lsof -i :3000
lsof -i :8080

# Free up ports
kill $(lsof -t -i:3000)

# Clean build
docker compose down -v
docker compose build --no-cache
docker compose up
```

### Playwright Errors

**Symptom**: `Browser not found` or `Executable doesn't exist`

**Solutions**:
```bash
# Install browsers
playwright install chromium

# Install system dependencies (Linux)
playwright install-deps chromium

# Force reinstall
playwright install --force chromium

# Verify installation
python -c "from playwright.sync_api import sync_playwright; p = sync_playwright().start(); p.chromium.launch(); p.stop()"
```

### Import Errors

**Symptom**: `ModuleNotFoundError` or `ImportError`

**Solutions**:
```bash
# Ensure virtual environment is active
source venv/bin/activate

# Reinstall dependencies
pip install -r requirements.txt

# Check Python path
python -c "import sys; print(sys.path)"

# Run with module syntax
python -m command_center.main
```

## Runtime Issues

### Dashboard Shows No Data

**Symptom**: Empty agents list, no test results

**Causes & Solutions**:

1. **Vault Watcher not running**
   ```bash
   # Check if watcher is active
   ps aux | grep obsidian_reader
   
   # Start watcher
   python -m command_center.obsidian_reader
   ```

2. **Incorrect vault path**
   ```bash
   # Check path
   echo $OBSIDIAN_VAULT_PATH
   
   # Should be absolute path
   export OBSIDIAN_VAULT_PATH=/full/path/to/obsidian_vault
   ```

3. **Permission issues**
   ```bash
   # Fix permissions
   chmod -R 755 obsidian_vault/
   chown -R $USER:$USER obsidian_vault/
   ```

### Tests Won't Start

**Symptom**: Clicking "Initiate" does nothing

**Solutions**:
```bash
# Check MCP server is reachable
curl http://localhost:8080/mcp/tools

# Check logs
docker compose logs mcp-server

# Restart services
docker compose restart

# Verify agent spawner
curl -X POST http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"spawn_agent","arguments":{"role":"ui_explorer","objective":"Test","memory_node":"Runs/Test.md"}}}'
```

### Agent Crashes

**Symptom**: Agent status changes to `failed` immediately

**Solutions**:
```bash
# Check worker log
cat obsidian_vault/Runs/{agent_id}_worker.log

# Common causes:
# 1. URL not accessible
# 2. Browser launch failed
# 3. Objective parsing error

# Test browser manually
python -c "
import asyncio
from mcp_server.browser_tools import BrowserAutomation
async def test():
    b = BrowserAutomation()
    await b.start()
    r = await b.visit('https://example.com')
    print(r)
    await b.close()
asyncio.run(test())
"
```

### Chatbot Not Responding

**Symptom**: Vectra doesn't respond or gives errors

**Solutions**:
```bash
# Check LLM API key
curl -H "Authorization: Bearer $OPENAI_API_KEY" https://api.openai.com/v1/models

# Test LLM router
python -c "
from mcp_server.llm_router import LLMRouter
r = LLMRouter()
resp = r.complete('openai/gpt-4o-mini', [{'role':'user','content':'Hello'}])
print(resp.content)
"

# Check chat log
head -50 obsidian_vault/Global/Chat_Log.md

# Restart command center
docker compose restart command-center
```

## Performance Issues

### Slow Test Execution

**Symptom**: Tests take much longer than expected

**Solutions**:
```bash
# Use lighter LLM model
CHATBOT_MODEL=openai/gpt-4o-mini

# Reduce history context
CHATBOT_MAX_HISTORY=20

# Disable streaming
CHATBOT_ENABLE_STREAMING=false

# Check system resources
docker stats

# Limit concurrent agents
# (Modify docker-compose.yml resources)
```

### High Memory Usage

**Symptom**: System runs out of memory

**Solutions**:
```bash
# Limit Docker memory
docker compose up -d --memory=4g

# Clean old test runs
find obsidian_vault/Runs/ -mtime +7 -delete

# Reduce screenshot retention
rm -f obsidian_vault/Screenshots/*.png
```

### Browser Timeouts

**Symptom**: `TimeoutError` during page load

**Solutions**:
```bash
# Increase timeout
export PLAYWRIGHT_TIMEOUT=60000

# Check if site blocks automation
# Try with different user agent

# Test connectivity
curl -I https://example.com
```

## Configuration Issues

### API Key Errors

**Symptom**: `AuthenticationError` or `Invalid API key`

**Solutions**:
```bash
# Verify key is set
echo $OPENAI_API_KEY

# Check .env file
cat .env | grep API_KEY

# Test key
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY"

# Regenerate key if needed
# (Go to provider's dashboard)
```

### CORS Errors

**Symptom**: Browser blocks API requests

**Solutions**:
```bash
# In development
CORS_ORIGINS=*

# In production
CORS_ORIGINS=https://yourdomain.com,https://app.yourdomain.com

# Check browser console for specific error
```

### Port Conflicts

**Symptom**: `Address already in use`

**Solutions**:
```bash
# Find process using port
lsof -i :3000

# Kill process
kill -9 $(lsof -t -i:3000)

# Or use different port
COMMAND_CENTER_PORT=3001
MCP_SERVER_PORT=8081
```

## Data Issues

### Corrupted Vault Files

**Symptom**: Parsing errors or missing data

**Solutions**:
```bash
# Check file syntax
cat obsidian_vault/Runs/Test.md | head -20

# Should start with ---
# Frontmatter should be valid YAML

# Fix corrupted file
# 1. Backup
cp obsidian_vault/Runs/Test.md obsidian_vault/Runs/Test.md.bak

# 2. Recreate with proper format
cat > obsidian_vault/Runs/Test.md << 'EOF'
---
agent_role: ui_explorer
status: completed
---

# Fixed content
EOF
```

### Missing Screenshots

**Symptom**: Screenshot paths in results but files don't exist

**Solutions**:
```bash
# Check directory exists
ls -la obsidian_vault/Screenshots/

# Check permissions
chmod 755 obsidian_vault/Screenshots/

# Verify paths in results
grep -r "screenshots:" obsidian_vault/Runs/
```

## Network Issues

### Cannot Reach Target URL

**Symptom**: `Connection error` or `DNS resolution failed`

**Solutions**:
```bash
# Test connectivity
curl -I https://example.com
ping example.com

# Check DNS
nslookup example.com

# Try IP directly
curl -I https://93.184.216.34 -H "Host: example.com"

# Check if behind proxy
export HTTP_PROXY=http://proxy.company.com:8080
export HTTPS_PROXY=http://proxy.company.com:8080
```

### SSL Certificate Errors

**Symptom**: `SSL certificate verify failed`

**Solutions**:
```bash
# For self-signed certificates (development only)
# In browser_tools.py, add:
# context = await browser.new_context(ignore_https_errors=True)

# Or update certificates
sudo update-ca-certificates
```

## Getting Help

If none of these solutions work:

1. **Check logs**:
   ```bash
   docker compose logs > logs.txt
   ```

2. **Gather info**:
   - OS version
   - Docker version
   - Python version
   - Error messages
   - Reproduction steps

3. **Open issue**:
   https://github.com/Artflarex-Limited/vectra-qa/issues

4. **Community**:
   https://github.com/Artflarex-Limited/vectra-qa/discussions

## Debug Mode

Enable maximum logging:

```bash
# .env
LOG_LEVEL=DEBUG
HEADLESS=false
PYTHONUNBUFFERED=1

# Run with verbose output
python -m uvicorn command_center.main:app --log-level debug --reload

# Monitor in real-time
tail -f obsidian_vault/Runs/*_worker.log &
tail -f obsidian_vault/Global/Chat_Log.md
```