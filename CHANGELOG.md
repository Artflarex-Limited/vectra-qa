# Changelog

All notable changes to Vectra QA will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-01-15

### Added
- Initial release of Vectra QA
- Multi-agent testing framework with UI Explorer and Data Validator agents
- Obsidian Vault memory layer for structured test logging
- Real-time dashboard with Server-Sent Events
- Chatbot interface (Vectra) for natural language test configuration
- Support for multiple LLM providers (OpenAI, Anthropic, Google, MiniMax, Kimi, Local)
- Test types: Homepage, Navigation, Contact Form, API Monitoring, Accessibility, Responsive Design, Full Suite
- Structured test reports with severity levels and recommendations
- Screenshot capture during tests
- Docker Compose setup for easy deployment
- GitHub Actions workflows for docs deployment and releases
- Documentation site with MkDocs Material
- GitHub Wiki sync
- Versioned documentation support

### Features
- **Dynamic Agent Spawning**: On-demand agent creation with auto-termination
- **Natural Language Testing**: Chat with Vectra to configure and run tests
- **Real-Time Monitoring**: Live progress updates via SSE
- **Structured Reports**: Detailed findings with metrics and recommendations
- **Multi-Viewport Testing**: Desktop, tablet, and mobile screenshots
- **API Interception**: Network request monitoring for backend validation
- **Accessibility Audits**: WCAG compliance checks
- **Result Interpretation**: LLM-powered plain-English result summaries

### Technical
- FastAPI backend with HTMX frontend
- Playwright browser automation
- YAML frontmatter for structured metadata
- Wiki-links for semantic relationships
- File-based agent communication (A2A protocol)
- Dark-mode dashboard (Mission Control Noir theme)
- Collapsible chat widget with unread notifications

[0.1.0]: https://github.com/Artflarex-Limited/vectra-qa/releases/tag/v0.1.0