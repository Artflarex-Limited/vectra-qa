# Understanding Results

## Result Statuses

| Status | Icon | Meaning |
|--------|------|---------|
| Pass | ✅ | All checks passed |
| Fail | ❌ | Critical issues found |
| Warning | ⚠️ | Non-critical issues |

## Severity Levels

| Level | Icon | Action |
|-------|------|--------|
| Critical | 🔴 | Fix immediately |
| High | 🟠 | Fix today |
| Medium | 🟡 | Fix this week |
| Low | 🔵 | Fix when convenient |
| Info | ⚪ | No action needed |

## Viewing Results

### Dashboard
- Agent cards show pass/warning/fail
- Click "View Result" for details

### Result Page
- Status panel with metadata
- Summary statistics
- Detailed sections with findings
- Screenshots grid
- Raw log

### Chatbot
Ask Vectra for interpretation:
```
What did the last test find?
```

Vectra provides:
- Executive summary
- Critical issues
- Actionable recommendations
- Code examples for fixes

## Example Result

```
✅ Homepage Test Complete

Critical Issues: None
Warnings: 1 (missing meta description)
Passed: 5/6 checks

Recommendations:
1. Add meta description for SEO
```

## Exporting

```bash
# JSON API
curl http://localhost:3000/api/results/{agent_id}

# Screenshots
cp obsidian_vault/Screenshots/*.png ./downloads/
```

## Learn More

- [Full Results Guide](https://vectra-qa.artflarex.com/user-guide/understanding-results/)
- [API Reference](https://vectra-qa.artflarex.com/api/endpoints/)