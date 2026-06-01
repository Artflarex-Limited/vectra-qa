# Understanding Results

Test results are presented in multiple formats: structured reports, chatbot interpretations, and raw vault data.

## Result Statuses

| Status | Icon | Meaning |
|--------|------|---------|
| **Pass** | ✅ | All checks passed |
| **Fail** | ❌ | One or more critical checks failed |
| **Warning** | ⚠️ | Non-critical issues found |
| **Pending** | ⏳ | Test still running |

## Structured Report Format

Each test generates a structured report with sections:

```markdown
# 📊 Test Report: Homepage

## Executive Summary
**Overall Status**: ✅ PASS
**Target URL**: https://example.com

### Summary
| Metric | Value |
|--------|-------|
| Sections Passed | 5 |
| Sections Failed | 0 |
| Warnings | 1 |
| Total Checks | 6 |

## ✅ Page Information
### Metrics
- **URL**: https://example.com
- **Title**: Example Domain
- **HTTP Status**: 200

## ✅ Navigation Audit
### Findings
- ⚪ Navigation Present: Found 3 navigation element(s)

## ⚠️ Content Structure
### Findings
- 🟡 No Main Content Area: No main or .content container found
```

## Severity Levels

Findings are categorized by severity:

| Severity | Icon | Impact | Action Required |
|----------|------|--------|----------------|
| **Critical** | 🔴 | Blocks functionality | Fix immediately |
| **High** | 🟠 | Major impact | Fix today |
| **Medium** | 🟡 | Moderate impact | Fix this week |
| **Low** | 🔵 | Minor impact | Fix when convenient |
| **Info** | ⚪ | Observation | No action needed |

## Sections Breakdown

### Homepage Test Sections

| Section | Checks | Fail Impact |
|---------|--------|-------------|
| Page Load | URL, title, status | Critical |
| Navigation | Elements, links | High |
| Content Structure | Main areas, headings | Medium |
| Footer | Presence | Low |
| Error Check | Console errors | High |
| Security | HTTPS | Critical |

### Navigation Test Sections

| Section | Checks | Fail Impact |
|---------|--------|-------------|
| Link Inventory | Total, internal, external | Info |
| Link Validation | Broken links | Critical |
| Pass Rate | Percentage working | High |

### Contact Form Test Sections

| Section | Checks | Fail Impact |
|---------|--------|-------------|
| Form Discovery | Find contact form | Critical |
| Field Analysis | Count, types, required | High |
| Validation | Email, required fields | High |

### Accessibility Test Sections

| Section | Checks | Fail Impact |
|---------|--------|-------------|
| Image Alt Text | All images labeled | High |
| Heading Structure | H1-H6 hierarchy | Medium |
| ARIA Labels | Accessible attributes | Medium |
| Form Labels | Input labeling | High |

## Result Page

The `/results/{agent_id}` page shows:

### Status Panel

- Overall status badge (pass/warning/fail)
- Progress bar
- Test metadata (URL, type, duration)

### Summary Stats

- Passed / Failed / Warning counts
- Total sections checked

### Detailed Sections

- Collapsible sections for each check
- Metrics tables
- Findings with severity icons

### Recommendations

- Numbered list of suggested fixes
- Code examples where applicable

### Screenshots

- Grid of captured screenshots
- Click to view full size

### Raw Log

- Toggle-able raw markdown content
- Full execution details

## Chatbot Interpretation

Vectra provides plain-English summaries:

### Example: Pass

```
The homepage test passed! Here's what I found:

✅ Page loaded successfully in 1.2s
✅ Navigation structure is solid (3 elements)
✅ No console errors
✅ HTTPS enabled

⚠️ One minor thing: The page lacks a main content 
container, which could affect screen reader navigation.

Overall: Great job! The homepage is in good shape.
```

### Example: Fail

```
The contact form test found some issues:

❌ Critical: Missing email validation
   - Users can submit empty emails
   - Fix: Add required attribute
   
❌ High: No contact form found
   - Checked links, forms, and sections
   - The page might not have a contact form

⚠️ Medium: Page lacks heading structure
   - No H1 found
   - Fix: Add H1 for page title

Recommendations:
1. Add email validation to contact form
2. Ensure contact form exists on the page
3. Add proper heading hierarchy
```

### Example: Warning

```
The accessibility audit completed with warnings:

✅ All images have alt text (5/5)
✅ ARIA attributes present (3 elements)
⚠️ 2 form fields lack labels
⚠️ No skip-to-content link

Fixes needed:
```html
<!-- Add labels -->
<label for="email">Email</label>
<input id="email" type="email" required>

<!-- Add skip link -->
<a href="#main" class="skip-link">Skip to content</a>
```

The site is mostly accessible but needs these
improvements for full WCAG compliance.

```

## Reading Raw Results

For debugging or custom analysis, read the vault directly:

```bash
# Read specific test result
cat obsidian_vault/Runs/Homepage_Test_20260115.md

# Search for failures
grep -r "status: failed" obsidian_vault/Runs/

# Count tests by result
grep -r "result: pass" obsidian_vault/Runs/ | wc -l
```

## Metrics Over Time

Track improvements across test runs:

```bash
# Compare two test runs
diff <(grep "console_errors" run1.md) <(grep "console_errors" run2.md)

# Extract all pass rates
grep -r "Pass rate" obsidian_vault/Runs/ | sort
```

## Exporting Results

### JSON API

```bash
curl http://localhost:3000/api/results/{agent_id} > result.json
```

### Markdown

Results are already in Markdown format in the vault.

### Screenshot Downloads

```bash
# Download all screenshots
cp obsidian_vault/Screenshots/*.png ./downloads/
```

## Interpreting Screenshots

Screenshots show visual state at test time:

| Screenshot Type | What to Look For |
|----------------|------------------|
| Homepage | Layout, navigation, CTAs |
| Contact | Form fields, labels, buttons |
| Desktop (1920x1080) | Full layout |
| Tablet (768x1024) | Tablet adaptations |
| Mobile (375x667) | Mobile breakpoints |

## Action Items

After reviewing results:

1. **Critical issues**: Fix immediately
2. **High issues**: Fix today
3. **Medium issues**: Schedule for this week
4. **Low issues**: Add to backlog
5. **Info items**: No action needed

Create GitHub issues from findings:

```markdown
## Test Finding: Missing Email Validation

**Severity**: Critical
**Test**: Contact Form on https://example.com
**Impact**: Users can submit empty emails

**Fix**:
```html
<input type="email" required>
```

**Reference**: [[Contact_Test_20260115]]

```
