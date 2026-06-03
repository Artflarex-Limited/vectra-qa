# Changelog

All notable changes to Vectra QA will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Live QA Engineer (BREAKING)

The chatbot persona is gone. In its place: a Live QA Engineer that walks you through testing in 6 stages, asks plain-English questions, prompts for credentials only when needed, and narrates progress in real time. This is a hard break. There is no compat shim. Migrate any client that still hits the old `/api/chat/*` routes to `/api/engineer/*`.

#### Removed
- `GET /api/chat/history`
- `POST /api/chat/message`
- `POST /api/chat/execute`
- `GET /api/chat/sse`
- `GET /api/chat/interpret/{agent_id}`
- `command_center/chatbot.py` (the entire module)
- The dashboard's old chat widget that consumed the removed routes

#### Added
- `POST /api/engineer/start` — opens a new engineer session
- `POST /api/engineer/{sid}/message` — sends a user message or credential
- `GET /api/engineer/{sid}/stream` — Server-Sent Events for live narration
- `GET /api/engineer/{sid}/metrics` — per-session metrics
- `GET /api/engineer/{sid}/resume` — pick up where you left off
- `command_center/engineer/` package — events, vocabulary, state machine, site catalog, session store, credentials, classifier, conversation engine, narrator, report builder, metrics
- `command_center/live_engineer.py` — top-level orchestrator that wires the engineer modules together
- Frontend chat panel in `command_center/static/index.html` that consumes structured engineer events and renders the 6-stage flow

#### Migration
- Hard break, no compat shim. Any client calling `/api/chat/*` will get a 404.
- Replace `chat_engine` imports with `LiveEngineer` from `command_center.live_engineer`.
- Replace the `chat_sse` EventSource with `engineerEventSource` against `/api/engineer/{sid}/stream`.
- Persist the `session_id` cookie set by `/api/engineer/start` and pass it to subsequent calls. Use `/api/engineer/{sid}/resume` after a page refresh to continue a session.
- See [USER_GUIDE.md](USER_GUIDE.md) for the new "Talk to Vectra" quickstart.

### Fixed
- **Model routing**: Models like `minimax-m2.7` without `provider/` prefix defaulted to OpenAI, causing 401 auth errors. All models now use `provider/model` format (e.g., `minimax/MiniMax-M2.7`).
- **MiniMax base URL**: Updated from `api.minimax.chat` to `api.minimax.io` to match the actual MiniMax API endpoint.
- **UI Explorer JSON parsing**: Replaced fragile manual string splitting with robust `extract_json()` from `mcp_server/json_extractor.py` to handle nested code blocks and edge cases.
- **Dashboard raw log**: Raw log panel was hardcoded to "Loading..." and never received content. Now populates from the agent's full report content.
- **Dashboard summary**: Summary stats always showed 0 because the parser only supported markdown table format. Added bullet point format support to parse `- **Steps Executed**: N` and `- **Findings**: N` from the agent's report.

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
