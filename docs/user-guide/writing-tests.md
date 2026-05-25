# Writing Tests

Vectra QA supports multiple ways to define and run tests, from natural language chat to structured API calls.

## Method 1: Natural Language (Recommended)

The easiest way to run tests is through the chatbot.

### Basic Test Request

**Vectra Chat:**
```
Test the homepage of https://example.com
```

**Result:** Vectra plans and executes a homepage test automatically.

### Multi-Test Request

```
Check navigation and contact form on https://example.com
```

**Result:** Vectra plans two tests:
1. Navigation test
2. Contact form test

### Complex Request

```
Run a full accessibility audit on https://example.com and check if it works on mobile
```

**Result:** Vectra plans:
1. Accessibility test
2. Responsive design test

### Follow-Up Questions

After tests complete, ask for clarification:

```
What did the navigation test find?
```

```
Can you explain why the contact form failed?
```

```
What should I fix first?
```

## Method 2: Dashboard Form

For precise control, use the Launch Test form:

1. **Open Dashboard**: `http://localhost:3000`
2. **Enter URL**: `https://example.com`
3. **Select Test Type**: Choose from dropdown
4. **Click Initiate**

### Available Test Types

| Type | Best For | Duration |
|------|----------|----------|
| Homepage | Initial page load verification | ~30s |
| Navigation | Link validation | ~60s |
| Contact Form | Form field testing | ~45s |
| API Monitoring | Backend validation | ~60s |
| Accessibility | WCAG compliance | ~40s |
| Responsive | Multi-device testing | ~50s |
| Full Suite | Comprehensive audit | ~3min |

## Method 3: API Calls

For CI/CD integration or automation:

### cURL

```bash
curl -X POST http://localhost:3000/api/tests/run \
  -d "url=https://example.com" \
  -d "test_type=homepage"
```

### Python

```python
import requests

response = requests.post("http://localhost:3000/api/tests/run", data={
    "url": "https://example.com",
    "test_type": "full"
})

result = response.json()
agent_id = result["agent_id"]
print(f"Test started: {agent_id}")
```

### JavaScript

```javascript
const response = await fetch('http://localhost:3000/api/tests/run', {
    method: 'POST',
    headers: {'Content-Type': 'application/x-www-form-urlencoded'},
    body: 'url=https://example.com&test_type=navigation'
});

const result = await response.json();
console.log('Agent ID:', result.agent_id);
```

## Writing Effective Test Requests

### Be Specific

**Good:**
```
Test the contact form on https://example.com/contact
```

**Vague:**
```
Test my website
```

### Include URLs

Always provide the full URL including protocol:

```
https://example.com/page
```

Not:
```
example.com/page
```

### Use Keywords

Help Vectra understand your intent:

| Keyword | Test Type |
|---------|-----------|
| "homepage", "main page" | Homepage |
| "navigation", "links", "menu" | Navigation |
| "contact", "form" | Contact Form |
| "api", "backend", "endpoint" | API Monitoring |
| "accessibility", "a11y", "wcag" | Accessibility |
| "mobile", "responsive", "viewport" | Responsive |
| "full", "complete", "all" | Full Suite |

### Mention Specific Concerns

```
Test the homepage and check if there are any console errors
```

```
Check if the navigation works on mobile devices
```

```
Verify the contact form has proper validation
```

## Multi-Step Testing Workflows

### Sequential Testing

Run tests one after another:

```
1. Test homepage
2. Test navigation
3. Test contact form
```

Or simply:
```
Run a full test suite on https://example.com
```

### Conditional Testing

Based on results, run follow-up tests:

```
User: Test the homepage
Vectra: ✅ Homepage test passed
User: Now test the navigation
Vectra: Running navigation test...
```

### Regression Testing

After fixes, re-run tests:

```
I fixed the contact form. Can you test it again?
```

## Test Scenarios

### E-Commerce Site

```
Test these on https://shop.example.com:
1. Homepage loads correctly
2. Product navigation works
3. Contact form validates email
4. Checkout page is responsive
```

### Portfolio Site

```
Run an accessibility audit on https://portfolio.example.com
```

### API-Heavy Application

```
Monitor API calls on https://app.example.com
Check for 4xx and 5xx errors
```

## Understanding Test Coverage

### Homepage Test Covers:
- Page load success/failure
- Title and meta tags
- Navigation structure
- Hero section
- Call-to-action buttons
- Footer presence
- Console errors
- Total link count

### Navigation Test Covers:
- Internal link validation
- External link count
- Broken link detection
- Page transition success
- Mobile menu functionality

### Contact Form Test Covers:
- Form field discovery
- Required field validation
- Email format validation
- Form submission flow
- Accessibility attributes

### Accessibility Test Covers:
- Image alt text
- Heading hierarchy (H1-H6)
- ARIA labels
- Form labels
- Keyboard navigation
- Color contrast (basic)

### Responsive Test Covers:
- Desktop (1920x1080)
- Tablet (768x1024)
- Mobile (375x667)
- Screenshot comparison

## Best Practices

### 1. Start Simple
Begin with a homepage test before running full suites:
```
Test the homepage first
```

### 2. Iterate Based on Results
Fix critical issues before running comprehensive tests:
```
The homepage has errors. Let me fix those first.
```

### 3. Use Chat for Complex Workflows
For multi-step testing, chat with Vectra:
```
I need to test a user registration flow:
1. Homepage
2. Sign up page
3. Form validation
4. Thank you page
```

### 4. Save Test Plans
Document your testing strategy:
```markdown
# Test Plan: Example.com

## Phase 1: Homepage
- [x] Load test
- [x] Navigation check

## Phase 2: Features
- [ ] Contact form
- [ ] Search functionality

## Phase 3: Quality
- [ ] Accessibility audit
- [ ] Responsive test
```

## Troubleshooting Tests

### Test Won't Start
- Check if URL is accessible: `curl -I https://example.com`
- Verify Docker services are running: `docker compose ps`
- Check agent logs: `docker logs vectra-mcp-server`

### Test Hangs
- Some tests wait for page load (30s timeout)
- Check if site blocks automated browsers
- Try headless=false to see the browser

### False Positives
- Dynamic content may cause intermittent failures
- Run test multiple times to confirm
- Check screenshots for visual verification