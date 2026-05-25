# Frequently Asked Questions

## General

**Q: What is Vectra QA?**
A: A multi-agent autonomous testing framework that deploys specialized AI agents to test web applications.

**Q: Do I need to write test scripts?**
A: No! You can use natural language through the chatbot or select test types from the dashboard.

**Q: Is it free?**
A: Yes, Vectra QA is open source under the MIT License. You only pay for LLM API usage.

## Installation

**Q: What are the system requirements?**
A: Python 3.11+, Docker (recommended), and at least one LLM API key.

**Q: Can I run it without Docker?**
A: Yes, but Docker is recommended for easier setup.

**Q: Which LLM provider should I use?**
A: Any works. OpenAI and Anthropic are most reliable. Local models (Ollama) work for privacy.

## Usage

**Q: How do I test my website?**
A: Open the dashboard, enter your URL, select a test type, and click "Initiate".

**Q: Can I run multiple tests at once?**
A: Yes, either run a "Full Suite" or launch multiple tests in parallel via the API.

**Q: How long do tests take?**
A: Most tests complete in 30-60 seconds. Full suites take ~3 minutes.

**Q: Can I test local development servers?**
A: Yes, use `http://localhost:3000` or your local URL.

## Results

**Q: Where are test results stored?**
A: In the Obsidian Vault (`obsidian_vault/Runs/`).

**Q: Can I export results?**
A: Yes, via the API (`/api/results/{agent_id}`) or by copying vault files.

**Q: What do the severity levels mean?**
A: Critical = fix immediately, High = fix today, Medium = fix this week, Low = fix when convenient.

## Customization

**Q: Can I add custom test types?**
A: Yes! Create a custom agent worker and register it. See the [Custom Agents Guide](https://vectra-qa.artflarex.com/development/custom-agents/).

**Q: Can I change the LLM model?**
A: Yes, set `CHATBOT_MODEL` environment variable.

**Q: Can I use my own Obsidian vault?**
A: Yes, set `OBSIDIAN_VAULT_PATH` to your vault location.

## Troubleshooting

**Q: Tests fail immediately**
A: Check the worker log in `obsidian_vault/Runs/*_worker.log`.

**Q: Dashboard is empty**
A: Ensure the vault watcher is running and the vault path is correct.

**Q: Chatbot doesn't respond**
A: Verify your LLM API key is set correctly.

## Contributing

**Q: How can I contribute?**
A: See [Contributing Guide](https://vectra-qa.artflarex.com/development/contributing/).

**Q: Where do I report bugs?**
A: [GitHub Issues](https://github.com/Artflarex-Limited/vectra-qa/issues)

**Q: Can I suggest features?**
A: Yes! Use [GitHub Discussions](https://github.com/Artflarex-Limited/vectra-qa/discussions).