# Troubleshooting

## Common Issues

### Docker Won't Start
```bash
# Check ports
lsof -i :3000

# Clean build
docker compose down -v
docker compose build --no-cache
```

### Dashboard Shows No Data
- Check vault watcher is running
- Verify `OBSIDIAN_VAULT_PATH` is correct
- Check file permissions

### Tests Won't Start
- Verify MCP server is running: `curl http://localhost:8080/mcp/tools`
- Check agent logs: `docker logs vectra-mcp-server`

### Chatbot Not Responding
- Check LLM API key is set
- Test LLM connection
- Restart command center

### Browser Errors
```bash
# Install browsers
playwright install chromium

# Install system deps
playwright install-deps chromium
```

## Debug Mode

```bash
# Enable verbose logging
export LOG_LEVEL=DEBUG
export HEADLESS=false

# Watch logs
tail -f obsidian_vault/Runs/*_worker.log
```

## Getting Help

- [GitHub Issues](https://github.com/Artflarex-Limited/vectra-qa/issues)
- [GitHub Discussions](https://github.com/Artflarex-Limited/vectra-qa/discussions)
- [Full Troubleshooting Guide](https://vectra-qa.artflarex.com/reference/troubleshooting/)