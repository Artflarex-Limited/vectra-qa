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

### UI Explorer Agent Fails Immediately with API Key Error

**Symptom:** Agent reports "PASSED" or "initialized" status within 5-10 seconds with no real work done. Container logs show `401 Incorrect API key provided`.

**Cause:** The model name in your `.env` file is missing the `provider/` prefix. For example, `UI_EXPLORER_MODEL=minimax-m2.7` defaults to OpenAI (using your `OPENAI_API_KEY`), not MiniMax.

**Fix:** Update your `.env` file to use the `provider/model` format:
```bash
# Wrong - defaults to OpenAI
UI_EXPLORER_MODEL=minimax-m2.7

# Correct - explicitly uses MiniMax client
UI_EXPLORER_MODEL=minimax/MiniMax-M2.7
```

Apply this format to `ORCHESTRATOR_MODEL`, `UI_EXPLORER_MODEL`, `CHATBOT_MODEL`, and `DATA_VALIDATOR_MODEL`.

### "Failed to Parse LLM Response" in Agent Logs

**Symptom:** Agent executes many steps but logs show `Failed to parse LLM response, taking screenshot for context` repeatedly, and the agent falls back to screenshots instead of planned actions.

**Cause:** The LLM response format doesn't match what the parser expects (e.g., nested code blocks, embedded JSON, unusual formatting).

**Fix:** This is handled automatically by the robust `extract_json()` function in `mcp_server/json_extractor.py`. If you see this error after updating to the latest version, check the agent's raw log for the actual LLM response and file an issue with the response text.

### Dashboard Raw Log is Empty

**Symptom:** The "Raw Log" section in the test result page shows "Loading..." and never displays the agent's full report.

**Cause:** The raw log was hardcoded to "Loading..." in older versions and never received the API content.

**Fix:** This is fixed in the latest version. The raw log element now populates with the full report content automatically. Make sure you're running the latest image: `docker compose pull && docker compose up --build -d`.

### Dashboard Summary Always Shows Zero

**Symptom:** The summary panel shows "Passed: 0, Failed: 0, Warnings: 0, Total: 0" even after a successful test run with many steps.

**Cause:** The summary parser only handled markdown table format (e.g., `| Sections Passed | 5 |`), but the UI Explorer generates bullet points (e.g., `- **Steps Executed**: 36`).

**Fix:** This is fixed in the latest version. The summary parser now supports both formats. Update your image: `docker compose pull && docker compose up --build -d`.

## Getting Help

- [GitHub Issues](https://github.com/Artflarex-Limited/vectra-qa/issues)
- [GitHub Discussions](https://github.com/Artflarex-Limited/vectra-qa/discussions)
- [Full Troubleshooting Guide](https://vectra-qa.artflarex.com/reference/troubleshooting/)