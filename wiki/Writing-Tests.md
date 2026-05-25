# Writing Tests

## Method 1: Chat with Vectra (Recommended)

The easiest way to run tests is through the chatbot:

```
Test the homepage of https://example.com
```

Vectra will plan and execute the test automatically.

## Method 2: Dashboard Form

1. Open `http://localhost:3000`
2. Enter URL
3. Select test type
4. Click "Initiate"

## Available Test Types

| Type | Description | Duration |
|------|-------------|----------|
| Homepage | Page structure, navigation, CTAs | ~30s |
| Navigation | Link validation | ~60s |
| Contact Form | Form fields, validation | ~45s |
| API Monitoring | Backend API calls | ~60s |
| Accessibility | WCAG compliance | ~40s |
| Responsive | Multi-viewport testing | ~50s |
| Full Suite | All tests combined | ~3min |

## Examples

### Basic Test
```
Test the contact form on https://example.com
```

### Multi-Test
```
Check navigation and mobile layout on https://example.com
```

### Complex Request
```
Run a full accessibility audit on https://example.com
```

## Tips

- **Be specific**: "Test the contact form" > "Run a test"
- **Include URLs**: Always provide the full URL
- **Use keywords**: "navigation", "contact", "accessibility"
- **Follow up**: Ask "What did the last test find?"

## API

```bash
# Run test via API
curl -X POST http://localhost:3000/api/tests/run \
  -d "url=https://example.com" \
  -d "test_type=homepage"
```

## Learn More

- [Full User Guide](https://vectra-qa.artflarex.com/user-guide/writing-tests/)
- [Advanced Usage](https://vectra-qa.artflarex.com/user-guide/advanced-usage/)