# Advanced Usage

This guide covers advanced features and integrations for power users.

## CI/CD Integration

### GitHub Actions

```yaml
name: Vectra QA Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Start Vectra QA
        run: docker compose up -d
        
      - name: Wait for services
        run: sleep 30
        
      - name: Run tests
        run: |
          curl -X POST http://localhost:3000/api/tests/run \
            -d "url=https://staging.example.com" \
            -d "test_type=full"
            
      - name: Wait for completion
        run: sleep 180
        
      - name: Check results
        run: |
          RESULT=$(curl -s http://localhost:3000/api/results | jq '.results[0].result')
          if [ "$RESULT" = '"fail"' ]; then
            echo "Tests failed!"
            exit 1
          fi
```

### GitLab CI

```yaml
stages:
  - test

vectra_tests:
  stage: test
  image: curlimages/curl
  services:
    - name: vectra-qa
      alias: vectra
  script:
    - curl -X POST http://vectra:3000/api/tests/run -d "url=$CI_ENVIRONMENT_URL"
```

## Custom Test Scenarios

### Multi-URL Testing

Test multiple pages in sequence:

```python
import requests
import time

urls = [
    "https://example.com",
    "https://example.com/about",
    "https://example.com/contact"
]

for url in urls:
    response = requests.post("http://localhost:3000/api/tests/run", data={
        "url": url,
        "test_type": "homepage"
    })
    agent_id = response.json()["agent_id"]
    
    # Wait for completion
    while True:
        result = requests.get(f"http://localhost:3000/api/results/{agent_id}").json()
        if result["status"] in ["completed", "failed"]:
            break
        time.sleep(5)
    
    print(f"{url}: {result['result']}")
```

### Scheduled Testing

Run tests on a schedule using cron:

```bash
# Edit crontab
crontab -e

# Run full test suite every night at 2 AM
0 2 * * * curl -X POST http://localhost:3000/api/tests/run -d "url=https://example.com" -d "test_type=full"

# Run accessibility test weekly
0 3 * * 1 curl -X POST http://localhost:3000/api/tests/run -d "url=https://example.com" -d "test_type=accessibility"
```

## Batch Operations

### Run All Test Types

```bash
#!/bin/bash
URL="https://example.com"

for test_type in homepage navigation contact api accessibility responsive; do
    echo "Running $test_type test..."
    curl -X POST http://localhost:3000/api/tests/run \
        -d "url=$URL" \
        -d "test_type=$test_type"
    sleep 60  # Wait between tests
done
```

### Parallel Testing

Run multiple tests simultaneously:

```python
import asyncio
import aiohttp

async def run_test(session, url, test_type):
    async with session.post(
        "http://localhost:3000/api/tests/run",
        data={"url": url, "test_type": test_type}
    ) as response:
        return await response.json()

async def main():
    async with aiohttp.ClientSession() as session:
        tasks = [
            run_test(session, "https://example.com", "homepage"),
            run_test(session, "https://example.com", "navigation"),
            run_test(session, "https://example.com", "api")
        ]
        results = await asyncio.gather(*tasks)
        for result in results:
            print(f"Agent: {result['agent_id']}")

asyncio.run(main())
```

## Custom Agents

### Creating a New Agent Type

1. **Create worker directory**:
```bash
mkdir agents/security_scanner
```

2. **Write worker script**:
```python
# agents/security_scanner/worker.py
import asyncio
import sys

async def run_agent(agent_id, memory_node):
    # Read objective
    # Run security tests
    # Write results to vault
    pass

if __name__ == "__main__":
    agent_id = sys.argv[1]
    memory_node = sys.argv[2]
    asyncio.run(run_agent(agent_id, memory_node))
```

3. **Register in spawner**:
```python
# mcp_server/tools.py
worker_scripts = {
    "ui_explorer": "agents/ui_explorer/worker.py",
    "data_validator": "agents/data_validator/worker.py",
    "security_scanner": "agents/security_scanner/worker.py"
}
```

4. **Add to chatbot**:
```python
# command_center/chatbot.py
TEST_TYPES = {
    "security": {
        "name": "Security Scan",
        "role": "security_scanner",
        "keywords": ["security", "scan", "vulnerability"]
    }
}
```

## Environment-Specific Testing

### Staging Environment

```bash
# .env.staging
MCP_SERVER_URL=http://staging-mcp:8080
OPENAI_API_KEY=sk-staging-key
```

```bash
docker compose -f docker-compose.yml -f docker-compose.staging.yml up
```

### Production Monitoring

Run periodic tests against production:

```python
# monitoring.py
import requests
import time

while True:
    response = requests.post("http://localhost:3000/api/tests/run", data={
        "url": "https://example.com",
        "test_type": "homepage"
    })
    
    agent_id = response.json()["agent_id"]
    time.sleep(60)  # Wait for test
    
    result = requests.get(f"http://localhost:3000/api/results/{agent_id}").json()
    
    if result["result"] == "fail":
        # Send alert
        send_alert(f"Production test failed: {result['objective']}")
    
    time.sleep(300)  # Check every 5 minutes
```

## Result Analysis

### Generate Reports

```python
import requests
import json
from datetime import datetime

# Get all results
response = requests.get("http://localhost:3000/api/results")
results = response.json()["results"]

# Generate summary report
report = {
    "generated_at": datetime.now().isoformat(),
    "total_tests": len(results),
    "pass_rate": sum(1 for r in results if r["result"] == "pass") / len(results),
    "by_type": {}
}

for result in results:
    test_type = result["role"]
    if test_type not in report["by_type"]:
        report["by_type"][test_type] = {"total": 0, "pass": 0}
    report["by_type"][test_type]["total"] += 1
    if result["result"] == "pass":
        report["by_type"][test_type]["pass"] += 1

with open("test_report.json", "w") as f:
    json.dump(report, f, indent=2)
```

### Export to CSV

```python
import csv
import requests

response = requests.get("http://localhost:3000/api/results")
results = response.json()["results"]

with open("test_results.csv", "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["Agent ID", "Role", "Status", "Result", "URL", "Timestamp"])
    
    for result in results:
        writer.writerow([
            result["agent_id"],
            result["role"],
            result["status"],
            result["result"],
            result["objective"],
            result["timestamp"]
        ])
```

## Performance Optimization

### Browser Pooling

For high-frequency testing, reuse browser contexts:

```python
# In custom worker
from mcp_server.browser_tools import BrowserAutomation

# Create once, reuse
browser = BrowserAutomation()
await browser.start()

for url in urls:
    result = await browser.visit(url)
    # Test...

await browser.close()
```

### Parallel Agents

Run multiple agents concurrently:

```bash
# Start 5 agents simultaneously
for i in {1..5}; do
    curl -X POST http://localhost:3000/api/tests/run \
        -d "url=https://example.com/page$i" \
        -d "test_type=homepage" &
done
wait
```

## Debugging

### Enable Verbose Logging

```bash
# .env
LOG_LEVEL=DEBUG
HEADLESS=false  # Show browser window
```

### Watch Agent Logs

```bash
# In real-time
tail -f obsidian_vault/Runs/*_worker.log

# Specific agent
tail -f obsidian_vault/Runs/ui_explorer-*_worker.log
```

### Inspect Vault State

```bash
# List all test runs
ls -lt obsidian_vault/Runs/

# Check active agents
grep -r "status: active" obsidian_vault/Runs/

# Find failures
grep -r "result: fail" obsidian_vault/Runs/
```

## Security Considerations

### API Key Rotation

```bash
# Rotate API keys periodically
# 1. Generate new key
# 2. Update .env
# 3. Restart services
# 4. Revoke old key
docker compose restart
```

### Network Isolation

```yaml
# docker-compose.yml
services:
  mcp-server:
    networks:
      - vectra-network
    # No external network access for agents
```

### Sensitive Data

Never include in test objectives:
- API keys
- Passwords
- Personal information
- Internal URLs

```python
# Bad
objective = "Test login with password123"

# Good
objective = "Test login form validation"
```

## Backup and Recovery

### Backup Strategy

```bash
#!/bin/bash
# backup.sh

DATE=$(date +%Y%m%d)
BACKUP_DIR="/backups/vectra-qa/$DATE"

mkdir -p $BACKUP_DIR

# Backup vault
cp -r obsidian_vault/ $BACKUP_DIR/

# Backup config
cp .env $BACKUP_DIR/
cp docker-compose.yml $BACKUP_DIR/

# Compress
tar -czf $BACKUP_DIR.tar.gz $BACKUP_DIR
rm -rf $BACKUP_DIR

# Upload to S3 (optional)
aws s3 cp $BACKUP_DIR.tar.gz s3://my-bucket/vectra-qa-backups/
```

### Recovery

```bash
# Restore from backup
tar -xzf 20260115.tar.gz
cp -r 20260115/obsidian_vault/* obsidian_vault/
cp 20260115/.env .env
docker compose up --build
```