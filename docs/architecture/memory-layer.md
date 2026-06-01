# Memory Layer

The Obsidian Vault serves as the shared memory system for all agents. Unlike traditional databases or message queues, it uses **Markdown files with YAML frontmatter** — making it human-readable, version-control friendly, and natively compatible with large language models.

## Why Markdown?

### Human Readable

```markdown
## [10:30:15] Page Load Complete

- **URL**: https://example.com
- **Status**: 200 OK
- **Load Time**: 1.2s
```

### LLM Native

Large language models are trained on vast amounts of Markdown. The format is their "native language":

- Headers structure context
- Bullet points organize findings
- Code blocks contain examples
- Bold text emphasizes importance

### Version Control Friendly

```bash
git diff obsidian_vault/Runs/Homepage_Test_20260115.md
```

Diffs show exactly what changed:

```diff
- progress_percent: 50
+ progress_percent: 75
```

### No Dependencies

No database server, no connection pool, no ORM. Just the filesystem:

- Works offline
- Survives container restarts
- Easy to back up (rsync, tar)
- Debuggable (cat, grep, less)

## YAML Frontmatter

Every memory node starts with structured metadata:

```yaml
---
agent_role: ui_explorer
agent_id: ui_explorer-20260115-120000-abc123
status: active
objective: Test homepage at https://example.com
spawned_at: 2026-01-15T12:00:00Z
progress_percent: 75
result: pending
screenshots:
  - obsidian_vault/Screenshots/agent-id_homepage.png
compute_pid: 12345
---
```

### Standard Fields

| Field | Type | Description |
|-------|------|-------------|
| `agent_role` | string | Agent specialization (ui_explorer, data_validator) |
| `agent_id` | string | Unique identifier with timestamp |
| `status` | string | Current state: spawned, active, completed, failed |
| `objective` | string | Human-readable mission description |
| `spawned_at` | ISO datetime | When the agent was created |
| `progress_percent` | integer | Completion percentage (0-100) |
| `result` | string | Test outcome: pass, fail, warning, pending |
| `screenshots` | list | Paths to captured screenshots |
| `compute_pid` | integer | Operating system process ID |

### Custom Fields

Agents can add any additional fields:

```yaml
---
browser_engine: chromium
viewport: 1920x1080
headless: true
console_errors: 0
---
```

## Node Types

### 1. Global Nodes

System-wide state that persists across test runs.

#### Test_Run_Master.md

```yaml
---
status: active
phase: testing
overall_result: pending
pass_count: 12
fail_count: 3
skip_count: 0
active_agents: ["ui_explorer-...", "data_validator-..."]
completed_agents: ["ui_explorer-..."]
---
```

#### Chat_Log.md

```yaml
---
chat_id: global
message_count: 42
---
```

### 2. Test Run Nodes

Individual test results created for each execution.

```yaml
---
agent_role: ui_explorer
agent_id: ui_explorer-20260115-120000-abc123
status: completed
result: pass
progress_percent: 100
---

# Test Report: Homepage

## Executive Summary
Overall Status: PASS
Target URL: https://example.com

## Page Information
| Metric | Value |
|--------|-------|
| URL | https://example.com |
| Title | Example Domain |
| HTTP Status | 200 |

## Navigation Audit
- Navigation elements found: 3

## Screenshots
- [[obsidian_vault/Screenshots/agent-id_homepage.png]]
```

### 3. Template Nodes

Reusable templates for spawning agents.

```markdown
---
agent_role: "{{ROLE}}"
agent_id: "{{AGENT_ID}}"
status: spawned
---

# Agent Log

## Objective
{{OBJECTIVE}}

## Progress

## Findings
```

## Wiki-Links

Agents create semantic connections between findings:

```markdown
The navigation test found a broken link.
See also: [[Navigation_Test_20260115]]

Related screenshots: [[Screenshot_Homepage]]
```

### Benefits

- **Knowledge Graph**: Obsidian visualizes connections
- **Context Preservation**: Related tests are linked
- **Human Exploration**: Browse findings like a wiki

## File Operations

### Reading a Node

```python
from mcp_server.tools import vault

node = vault.read_node("Runs/Homepage_Test_20260115.md")
print(node["frontmatter"]["status"])  # "completed"
print(node["content"])  # Markdown body
```

### Writing a Node

```python
vault.write_node(
    "Runs/My_Test.md",
    content="# Test Results\n\nAll passed!",
    frontmatter={"status": "completed", "result": "pass"}
)
```

### Updating Frontmatter

```python
vault.update_frontmatter(
    "Runs/My_Test.md",
    {"progress_percent": 100, "status": "completed"}
)
```

## Storage Considerations

### Performance

- **SSD recommended** — Vault files are read/written frequently
- **Inode limits** — Each test run creates 1-3 files
- **Screenshot size** — PNGs can be 100KB-2MB each

### Cleanup

```bash
# Archive old test runs
tar -czf runs-$(date +%Y%m%d).tar.gz obsidian_vault/Runs/
rm -rf obsidian_vault/Runs/*.md

# Keep only last 30 days
find obsidian_vault/Runs/ -mtime +30 -delete
```

### Backup

```bash
# Real-time sync to S3
aws s3 sync obsidian_vault/ s3://my-bucket/vectra-qa/

# Or rsync to backup server
rsync -avz obsidian_vault/ backup-server:/backups/vectra-qa/
```

## Security

### File Permissions

```bash
# Restrict vault access
chmod 700 obsidian_vault/
chown vectra:vectra obsidian_vault/
```

### Sensitive Data

Never store in vault:

- API keys (use `.env`)
- Passwords
- Session tokens
- Personal data

### Audit Trail

Every file change is logged by the Vault Watcher:

```python
# obsidian_reader.py logs:
# "File modified: Runs/Test_20260115.md"
# "File created: Runs/Test_20260116.md"
```

## Comparison with Alternatives

| Feature | Obsidian Vault | PostgreSQL | Redis | Message Queue |
|---------|---------------|------------|-------|---------------|
| **Human Readable** | ✅ Markdown | ❌ Binary | ❌ Binary | ❌ Binary |
| **LLM Compatible** | ✅ Native | ⚠️ SQL | ⚠️ Protocol | ⚠️ Protocol |
| **No Dependencies** | ✅ Filesystem | ❌ Server | ❌ Server | ❌ Server |
| **Version Control** | ✅ Git | ❌ Difficult | ❌ No | ❌ No |
| **Real-Time** | ⚠️ Polling | ✅ Triggers | ✅ Pub/Sub | ✅ Events |
| **Querying** | ⚠️ Grep | ✅ SQL | ✅ Key lookup | ✅ Filtering |
| **Scalability** | ⚠️ Filesystem | ✅ High | ✅ High | ✅ High |

**Verdict**: For Vectra QA's use case (testing framework, not production service), the trade-offs favor simplicity and observability over raw performance.
