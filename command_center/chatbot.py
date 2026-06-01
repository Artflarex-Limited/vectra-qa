"""
Vectra Chatbot Engine

Conversational AI for natural language test configuration and result interpretation.
Uses existing LLMRouter from mcp_server for multi-provider LLM support.
"""

import os
import re
import asyncio
import yaml
from typing import List, Dict, Any, Optional, AsyncGenerator
from datetime import datetime, timezone
from pathlib import Path

# Import existing LLM router
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from mcp_server.llm_router import LLMRouter

# Vault path
VAULT_PATH = Path(os.getenv("OBSIDIAN_VAULT_PATH", "/app/obsidian_vault"))
CHAT_LOG_PATH = VAULT_PATH / "Global" / "Chat_Log.md"

# Configuration
CHATBOT_MODEL = os.getenv("CHATBOT_MODEL", "anthropic/claude-3-5-sonnet-20241022")
MAX_HISTORY_MESSAGES = int(os.getenv("CHATBOT_MAX_HISTORY", "50"))
ENABLE_STREAMING = os.getenv("CHATBOT_ENABLE_STREAMING", "true").lower() == "true"

# Test type definitions
TEST_TYPES = {
    "homepage": {
        "name": "Homepage",
        "description": "Page structure, navigation, CTAs, footer, console errors",
        "role": "ui_explorer",
        "keywords": ["homepage", "home page", "landing page", "main page", "front page"],
    },
    "navigation": {
        "name": "Navigation",
        "description": "Link validation, page transitions, mobile menu",
        "role": "ui_explorer",
        "keywords": ["navigation", "nav", "links", "menu", "click", "browse"],
    },
    "contact": {
        "name": "Contact Form",
        "description": "Form fields, validation, accessibility",
        "role": "ui_explorer",
        "keywords": ["contact", "form", "email form", "contact us", "get in touch"],
    },
    "api": {
        "name": "API Monitoring",
        "description": "Backend API calls, response validation",
        "role": "data_validator",
        "keywords": ["api", "backend", "endpoint", "request", "response", "ajax"],
    },
    "accessibility": {
        "name": "Accessibility",
        "description": "WCAG compliance, ARIA, keyboard navigation, alt text",
        "role": "ui_explorer",
        "keywords": ["accessibility", "a11y", "wcag", "aria", "screen reader", "keyboard"],
    },
    "responsive": {
        "name": "Responsive Design",
        "description": "Multi-viewport testing (desktop, tablet, mobile)",
        "role": "ui_explorer",
        "keywords": ["responsive", "mobile", "tablet", "viewport", "breakpoint", "screen size"],
    },
    "full": {
        "name": "Full Suite",
        "description": "Complete audit — all test types",
        "role": "ui_explorer",
        "keywords": ["full", "complete", "comprehensive", "all", "everything", "audit", "suite"],
    },
}


class ChatMessage:
    """Represents a single chat message."""

    def __init__(
        self,
        role: str,
        content: str,
        timestamp: Optional[str] = None,
        metadata: Optional[Dict] = None,
    ):
        self.role = role
        self.content = content
        self.timestamp = timestamp or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z"
        self.metadata = metadata or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }


class ChatEngine:
    """Core chatbot engine for Vectra QA."""

    def __init__(self):
        self.llm: LLMRouter = LLMRouter()
        self._ensure_chat_log_exists()

    def _ensure_chat_log_exists(self):
        """Create chat log file if it doesn't exist."""
        if not CHAT_LOG_PATH.exists():
            CHAT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            CHAT_LOG_PATH.write_text(
                "---\n"
                "chat_id: global\n"
                f"created_at: {datetime.now(timezone.utc).isoformat()}Z\n"
                f"modified_at: {datetime.now(timezone.utc).isoformat()}Z\n"
                "message_count: 0\n"
                "---\n\n"
                "# Vectra Chat Log\n\n"
                "Conversation history between user and Vectra QA assistant.\n\n"
            )

    def _read_chat_log(self) -> Dict[str, Any]:
        """Read and parse the chat log file."""
        if not CHAT_LOG_PATH.exists():
            self._ensure_chat_log_exists()

        content = CHAT_LOG_PATH.read_text(encoding="utf-8")

        # Parse frontmatter
        frontmatter: Dict[str, Any] = {}
        body = content
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                try:
                    frontmatter = yaml.safe_load(parts[1]) or {}
                    body = parts[2].strip()
                except yaml.YAMLError:
                    pass

        return {"frontmatter": frontmatter, "body": body, "raw": content}

    def _write_chat_log(self, frontmatter: Dict, body: str):
        """Write chat log with updated frontmatter and body."""
        frontmatter["modified_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z"
        yaml_content = yaml.dump(frontmatter, default_flow_style=False, allow_unicode=True)
        full_content = f"---\n{yaml_content}---\n\n{body}"
        CHAT_LOG_PATH.write_text(full_content, encoding="utf-8")

    def _parse_messages(self, body: str) -> List[ChatMessage]:
        """Parse chat messages from markdown body."""
        messages = []
        lines = body.split("\n")
        current_role: Optional[str] = None
        current_content: List[str] = []
        current_timestamp: Optional[str] = None
        current_metadata: Dict[str, Any] = {}

        for line in lines:
            line_stripped = line.strip()

            # Check for message header: ## [timestamp] role
            if line_stripped.startswith("## ["):
                # Save previous message
                if current_role and current_content:
                    messages.append(
                        ChatMessage(
                            role=current_role,
                            content="\n".join(current_content).strip(),
                            timestamp=current_timestamp,
                            metadata=current_metadata,
                        )
                    )

                # Parse new header
                header = line_stripped[3:].strip()  # Remove '## '
                timestamp_end = header.find("]")
                if timestamp_end > 0:
                    current_timestamp = header[1:timestamp_end]
                    current_role = header[timestamp_end + 1 :].strip().lower()
                else:
                    current_timestamp = (
                        datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z"
                    )
                    current_role = "unknown"

                current_content = []
                current_metadata = {}
            elif line_stripped.startswith("[PLAN:"):
                # Parse plan metadata
                try:
                    plan_str = line_stripped[6:-1]  # Remove [PLAN: and ]
                    parts = plan_str.split(":", 1)
                    if len(parts) == 2:
                        current_metadata["plan"] = {"tests": parts[0].split(","), "url": parts[1]}
                except Exception:
                    pass
            elif line_stripped.startswith("[EXECUTED:"):
                current_metadata["executed"] = line_stripped[10:-1]
            elif line_stripped.startswith("[RESULT:"):
                current_metadata["result"] = line_stripped[8:-1]
            elif current_role is not None:
                current_content.append(line)

        # Save last message
        if current_role and current_content:
            messages.append(
                ChatMessage(
                    role=current_role,
                    content="\n".join(current_content).strip(),
                    timestamp=current_timestamp,
                    metadata=current_metadata,
                )
            )

        return messages

    def get_history(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get conversation history."""
        log = self._read_chat_log()
        messages = self._parse_messages(log["body"])

        if limit:
            messages = messages[-limit:]

        return [msg.to_dict() for msg in messages]

    def add_message(self, role: str, content: str, metadata: Optional[Dict] = None):
        """Add a message to the chat log."""
        log = self._read_chat_log()

        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z"

        # Build message entry
        entry = f"## [{timestamp}] {role}\n{content}\n"

        # Add metadata tags
        if metadata:
            if "plan" in metadata:
                plan = metadata["plan"]
                tests_str = ",".join(plan["tests"])
                entry += f"[PLAN:{tests_str}:{plan['url']}]\n"
            if "executed" in metadata:
                entry += f"[EXECUTED:{metadata['executed']}]\n"
            if "result" in metadata:
                entry += f"[RESULT:{metadata['result']}]\n"

        entry += "\n"

        # Append to body
        new_body = log["body"] + entry

        # Update frontmatter
        frontmatter = log["frontmatter"]
        frontmatter["message_count"] = frontmatter.get("message_count", 0) + 1

        self._write_chat_log(frontmatter, new_body)

    def _extract_url(self, text: str) -> Optional[str]:
        """Extract URL from text using regex."""
        url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
        match = re.search(url_pattern, text)
        if match:
            url = match.group(0).rstrip(".,;:!?)")
            return url
        return None

    def _classify_intent(self, message: str, context: Optional[List[Dict]] = None) -> str:
        """Classify user intent using LLM."""
        prompt = f"""Classify the user's intent. Respond with ONLY ONE word:
- "chat" — General conversation, questions, greetings
- "plan_tests" — User wants to run one or more tests on a website
- "interpret_results" — User wants to understand or analyze test results

User message: {message}

Intent:"""

        try:
            response = self.llm.complete(
                model=CHATBOT_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an intent classifier. Respond with exactly one word: chat, plan_tests, or interpret_results.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_tokens=20,
            )
            intent = response.content.strip().lower()
            if intent in ["chat", "plan_tests", "interpret_results"]:
                return intent
        except Exception as e:
            print(f"[CHATBOT] Intent classification error: {e}")

        # Fallback: keyword-based classification
        msg_lower = message.lower()
        if any(
            kw in msg_lower
            for kw in ["result", "found", "mean", "issue", "problem", "fix", "what did"]
        ):
            return "interpret_results"
        elif any(kw in msg_lower for kw in ["test", "check", "run", "audit", "verify", "scan"]):
            return "plan_tests"

        return "chat"

    def _extract_test_plan(self, message: str) -> Optional[Dict[str, Any]]:
        """Extract test plan (URL + test types) from user message."""
        url = self._extract_url(message)

        if not url:
            return None

        msg_lower = message.lower()
        tests = []

        # Check for explicit test type mentions
        for test_id, config in TEST_TYPES.items():
            for keyword in config["keywords"]:
                if keyword in msg_lower:
                    if test_id not in tests:
                        tests.append(test_id)
                    break

        # If no specific tests mentioned, use LLM to determine
        if not tests:
            prompt = f"""Given this test request, which test types are most appropriate?

Request: "{message}"

Available tests:
- homepage: Page structure, navigation, CTAs
- navigation: Link validation, page transitions
- contact: Form fields, validation
- api: Backend API monitoring
- accessibility: WCAG compliance, ARIA, alt text
- responsive: Multi-viewport (desktop, tablet, mobile)
- full: Complete audit of everything

Respond with a comma-separated list of test IDs (e.g., "homepage,navigation" or "full"):"""

            try:
                response = self.llm.complete(
                    model=CHATBOT_MODEL,
                    messages=[
                        {
                            "role": "system",
                            "content": "You are a test planner. Respond only with comma-separated test IDs.",
                        },
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.2,
                    max_tokens=50,
                )
                test_list = response.content.strip().lower()
                # Parse comma-separated list
                for test_id in test_list.split(","):
                    test_id = test_id.strip()
                    if test_id in TEST_TYPES:
                        tests.append(test_id)
            except Exception as e:
                print(f"[CHATBOT] Test extraction error: {e}")

        # Default to homepage if URL found but no tests determined
        if not tests:
            tests = ["homepage"]

        return {"url": url, "tests": tests, "test_configs": [TEST_TYPES[t] for t in tests]}

    def _build_system_prompt(self) -> str:
        """Build the system prompt for Vectra."""
        return """You are Vectra, an expert QA testing assistant embedded in the Vectra QA multi-agent testing framework. You help users configure, execute, and interpret automated browser tests.

Personality: Technical, precise, helpful. You speak like a senior QA engineer — knowledgeable but accessible. Use testing terminology correctly.

Capabilities:
- Plan and execute tests: homepage, navigation, contact forms, API monitoring, accessibility audits, responsive design, full suites
- Interpret test results and provide actionable recommendations
- Answer questions about testing best practices
- Maintain context across the conversation

When the user wants to run tests:
1. Extract the target URL from their message
2. Determine which test types are appropriate
3. Present a clear test plan for confirmation
4. Only execute after explicit user confirmation

When interpreting results:
1. Summarize pass/fail status in plain English
2. Explain specific findings and their impact
3. Suggest concrete fixes with code examples where relevant
4. Recommend follow-up tests if warranted

Always be concise but thorough. Use formatting for readability."""

    def generate_response(self, message: str, history: Optional[List[Dict]] = None) -> str:
        """Generate a conversational response."""
        messages = [{"role": "system", "content": self._build_system_prompt()}]

        # Retrieve relevant knowledge from RAG
        knowledge = ""
        try:
            import asyncio
            from mcp_server.rag import get_rag_pipeline

            loop = asyncio.get_event_loop()
            if loop.is_running():
                rag = loop.run_until_complete(get_rag_pipeline())
                results = loop.run_until_complete(rag.search_knowledge(message, k=2))
                if results:
                    knowledge = "\nRelevant knowledge:\n"
                    for r in results:
                        knowledge += f"- {r['text'][:200]}...\n"
        except Exception:
            pass

        # Add history context
        if history:
            for msg in history[-10:]:  # Last 10 messages for context
                if msg["role"] in ["user", "assistant"]:
                    messages.append({"role": msg["role"], "content": msg["content"]})

        messages.append({"role": "user", "content": message + knowledge})

        try:
            response = self.llm.complete(
                model=CHATBOT_MODEL, messages=messages, temperature=0.7, max_tokens=2000
            )
            return response.content
        except Exception as e:
            print(f"[CHATBOT] Response generation error: {e}")
            return f"I apologize, but I encountered an error processing your request: {str(e)}"

    def generate_plan_response(self, plan: Dict[str, Any]) -> str:
        """Generate a response presenting a test plan for confirmation."""
        url = plan["url"]
        tests = plan["test_configs"]

        response = f"I'll run the following tests on **{url}**:\n\n"
        for i, test in enumerate(tests, 1):
            response += f"{i}. **{test['name']}** — {test['description']}\n"

        response += "\nDoes this look correct? Say **yes** to proceed or let me know if you'd like to adjust."

        return response

    def interpret_results(self, agent_id: str, result_data: Dict[str, Any]) -> str:
        """Generate an LLM-interpreted summary of test results."""
        # Build context from result data
        context = f"""Test: {result_data.get('role', 'unknown')} on {result_data.get('objective', 'unknown URL')}
Status: {result_data.get('result', 'unknown')}
Overall: {result_data.get('overall_status', 'unknown')}

"""

        if "summary" in result_data:
            summary = result_data["summary"]
            context += f"Summary: {summary.get('pass', 0)} passed, {summary.get('fail', 0)} failed, {summary.get('warning', 0)} warnings\n"

        if "sections" in result_data:
            context += "\nSections:\n"
            for section in result_data["sections"]:
                context += f"- {section['title']}: {section['status']}\n"
                if "findings" in section:
                    for finding in section["findings"]:
                        context += (
                            f"  - {finding.get('severity', 'info')}: {finding.get('title', '')}\n"
                        )

        if "recommendations" in result_data:
            context += f"\nRecommendations: {len(result_data['recommendations'])}\n"

        prompt = f"""Analyze these test results and provide a clear, actionable summary.

{context}

Provide:
1. Executive summary (2-3 sentences)
2. Critical issues that need immediate attention
3. Positive findings
4. Specific, actionable recommendations with code examples where applicable
5. Suggested follow-up tests

Format with markdown for readability."""

        try:
            response = self.llm.complete(
                model=CHATBOT_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a QA analyst interpreting automated test results.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
                max_tokens=2500,
            )
            return response.content
        except Exception as e:
            print(f"[CHATBOT] Result interpretation error: {e}")
            return f"I encountered an error interpreting the results: {str(e)}"

    async def stream_response(
        self, message: str, history: Optional[List[Dict]] = None
    ) -> AsyncGenerator[str, None]:
        """Stream LLM response token by token."""
        messages = [{"role": "system", "content": self._build_system_prompt()}]

        if history:
            for msg in history[-10:]:
                if msg["role"] in ["user", "assistant"]:
                    messages.append({"role": msg["role"], "content": msg["content"]})

        messages.append({"role": "user", "content": message})

        try:
            # Note: Streaming support depends on the LLM provider
            # For now, we'll yield the full response (can be enhanced per-provider)
            response = self.llm.complete(
                model=CHATBOT_MODEL, messages=messages, temperature=0.7, max_tokens=2000
            )

            # Simulate streaming by yielding chunks
            content = response.content
            chunk_size = 10
            for i in range(0, len(content), chunk_size):
                yield content[i : i + chunk_size]
                await asyncio.sleep(0.01)  # Small delay for streaming effect

        except Exception as e:
            yield f"Error: {str(e)}"

    def process_message(self, message: str) -> Dict[str, Any]:
        """Process a user message and determine the response type."""
        # Get recent history for context
        history = self.get_history(limit=20)

        # Classify intent
        intent = self._classify_intent(message, history)

        if intent == "plan_tests":
            # Extract test plan
            plan = self._extract_test_plan(message)

            if plan:
                # Return plan for confirmation
                return {
                    "type": "plan",
                    "intent": intent,
                    "plan": plan,
                    "message": self.generate_plan_response(plan),
                }
            else:
                # URL not found, ask for it
                return {
                    "type": "chat",
                    "intent": intent,
                    "message": "I'd be happy to run tests for you! Could you provide the URL you'd like me to test?",
                }

        elif intent == "interpret_results":
            # Try to find the test to interpret
            # Check if user mentioned an agent_id
            agent_id_match = re.search(
                r"agent[_-]?([a-z]+-\d{14}-[a-f0-9]{6})", message, re.IGNORECASE
            )

            if agent_id_match:
                return {
                    "type": "interpret",
                    "intent": intent,
                    "agent_id": agent_id_match.group(1),
                    "message": "Let me analyze those test results for you...",
                }
            else:
                # Return a response asking for clarification or use most recent test
                return {
                    "type": "interpret",
                    "intent": intent,
                    "agent_id": None,  # Will use most recent
                    "message": "I'll analyze the most recent test results for you.",
                }

        else:
            # General chat
            response = self.generate_response(message, history)
            return {"type": "chat", "intent": intent, "message": response}


# Global chat engine instance
chat_engine = ChatEngine()
