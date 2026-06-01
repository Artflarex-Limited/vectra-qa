#!/usr/bin/env python3
"""
LLM-Driven UI Explorer Worker

Replaces keyword-matching with an observe-plan-act loop using LLM reasoning.
Reads soul.md and agents.md for behavioral context.

Usage:
    python agents/ui_explorer/worker_llm.py <agent_id> <memory_node_path>
"""

import sys
import os
import asyncio
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import structlog

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from mcp_server.tools import get_vault
from mcp_server.browser_tools import BrowserAutomation
from mcp_server.llm_router import llm_router

logger = structlog.get_logger()

# Configuration
VAULT_PATH = Path(os.getenv("OBSIDIAN_VAULT_PATH", "/app/obsidian_vault"))
MAX_STEPS = int(os.getenv("UI_EXPLORER_MAX_STEPS", "50"))
MAX_DURATION_SECONDS = int(os.getenv("UI_EXPLORER_MAX_DURATION", "600"))
UI_EXPLORER_MODEL = os.getenv("UI_EXPLORER_MODEL", "anthropic/claude-3-5-sonnet-20241022")


class LLMDrivenUIExplorer:
    """
    UI Explorer that uses LLM reasoning to decide what to test.

    observe -> plan -> act -> log -> repeat
    """

    def __init__(self, agent_id: str, memory_node: str):
        self.agent_id = agent_id
        self.memory_node = memory_node
        self.vault = get_vault()
        self.browser = BrowserAutomation(headless=os.getenv("HEADLESS", "true").lower() == "true")
        self.soul = self._load_persona("soul.md")
        self.agents_context = self._load_persona("agents.md")
        self.step_count = 0
        self.action_history: List[Dict] = []
        self.findings: List[Dict] = []
        self.screenshots: List[str] = []
        self.start_time = datetime.now(timezone.utc)

    def _load_persona(self, filename: str) -> str:
        """Load agent persona files."""
        paths = [
            VAULT_PATH / ".." / "agents" / "ui_explorer" / filename,
            Path("/app/agents/ui_explorer") / filename,
            Path("agents/ui_explorer") / filename,
            Path(__file__).parent / filename,
        ]

        for path in paths:
            if path.exists():
                return path.read_text(encoding="utf-8")

        logger.warning("persona_file_not_found", filename=filename)
        return ""

    def _build_system_prompt(self) -> str:
        """Build system prompt from persona files."""
        return f"""{self.soul}

## Agent Configuration
{self.agents_context}

## Instructions
You are a UI testing agent. You will receive the current state of a webpage and must decide the next action to take.

Respond ONLY with a JSON object in this exact format:
{{
    "action": "click|fill|navigate|assert|screenshot|complete|hover|scroll",
    "selector": "CSS selector (if applicable)",
    "value": "Text to type (if applicable)",
    "url": "URL to navigate to (if action=navigate)",
    "reasoning": "Why you're taking this action",
    "expected_result": "What you expect to happen",
    "confidence": 0-100
}}

Actions:
- "click": Click an element
- "fill": Type text into an input
- "navigate": Go to a URL
- "assert": Check if element exists/contains text
- "screenshot": Take a screenshot
- "complete": Finish testing (use when objective achieved)
- "hover": Hover over element
- "scroll": Scroll page

Rules:
- Be precise with CSS selectors
- Test edge cases and error states
- Log everything you observe
- Use "complete" action when you've thoroughly tested the objective
"""

    async def _observe(self) -> Dict[str, Any]:
        """Observe current page state."""
        observation = {
            "url": self.browser.page.url if self.browser.page else "",
            "title": await self.browser.page.title() if self.browser.page else "",
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z",
        }

        # Get visible interactive elements
        try:
            elements = await self.browser.page.query_selector_all(
                'button, a, input, select, textarea, [role="button"], [role="link"]'
            )
            observation["interactive_elements"] = []
            for i, el in enumerate(elements[:20]):  # Limit to 20 elements
                try:
                    tag = await el.evaluate("el => el.tagName.toLowerCase()")
                    text = await el.text_content()
                    visible = await el.is_visible()
                    selector = await el.evaluate(
                        'el => {\n                        if (el.id) return "#" + el.id;\n                        if (el.className) return "." + el.className.split(" ")[0];\n                        return el.tagName.toLowerCase();\n                    }'
                    )

                    if visible and text and text.strip():
                        observation["interactive_elements"].append(
                            {
                                "index": i,
                                "tag": tag,
                                "text": text.strip()[:50],
                                "selector": selector,
                            }
                        )
                except Exception:
                    pass
        except Exception as e:
            observation["interactive_elements_error"] = str(e)

        # Get console errors
        errors = await self.browser.get_console_errors()
        if errors:
            observation["console_errors"] = errors[:5]

        # Get current viewport
        try:
            viewport = await self.browser.page.viewport_size()
            observation["viewport"] = viewport
        except Exception:
            pass

        return observation

    async def _plan(self, objective: str, observation: Dict) -> Dict[str, Any]:
        """Use LLM to decide next action."""
        # Build context
        context = {
            "objective": objective,
            "step": self.step_count + 1,
            "max_steps": MAX_STEPS,
            "observation": observation,
            "previous_actions": self.action_history[-5:] if self.action_history else [],
            "findings_count": len(self.findings),
        }

        prompt = f"""
Current test context:
```json
{json.dumps(context, indent=2, default=str)}
```

Based on the current page state and your objective, what is the next action to take?

Respond with a JSON object containing your chosen action.
"""

        try:
            response = llm_router.complete(
                model=UI_EXPLORER_MODEL,
                messages=[
                    {"role": "system", "content": self._build_system_prompt()},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
                max_tokens=500,
            )

            # Parse JSON from response
            content = response.content.strip()
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            action = json.loads(content)
            logger.info(
                "llm_action_decided",
                action=action.get("action"),
                reasoning=action.get("reasoning", "")[:100],
            )
            return action

        except json.JSONDecodeError as e:
            logger.error("failed_to_parse_llm_action", error=str(e), raw=response.content[:500])
            return {
                "action": "screenshot",
                "reasoning": "Failed to parse LLM response, taking screenshot for context",
                "confidence": 50,
            }
        except Exception as e:
            logger.error("llm_planning_error", error=str(e))
            return {
                "action": "complete",
                "reasoning": f"Error during planning: {e}",
                "confidence": 0,
            }

    async def _act(self, action: Dict) -> Dict[str, Any]:
        """Execute the chosen action."""
        action_type = action.get("action", "screenshot")
        result = {"success": False, "action": action_type}

        try:
            if action_type == "click":
                result = await self.browser.click(action.get("selector", ""))
            elif action_type == "fill":
                result = await self.browser.fill(
                    action.get("selector", ""), action.get("value", "")
                )
            elif action_type == "navigate":
                result = await self.browser.visit(action.get("url", ""))
            elif action_type == "assert":
                selector = action.get("selector", "")
                text = await self.browser.get_text(selector)
                result = {
                    "success": text.get("success", False),
                    "selector": selector,
                    "found_text": text.get("text", ""),
                    "expected": action.get("expected_result", ""),
                }
            elif action_type == "screenshot":
                path = f"obsidian_vault/Screenshots/{self.agent_id}_step{self.step_count}.png"
                result = await self.browser.screenshot(path)
                if result["success"]:
                    self.screenshots.append(path)
            elif action_type == "hover":
                await self.browser.page.hover(action.get("selector", ""))
                result = {"success": True, "action": "hover"}
            elif action_type == "scroll":
                result = await self.browser.scroll_to_bottom()
            elif action_type == "complete":
                result = {"success": True, "action": "complete", "completed": True}
            else:
                result = {"success": False, "error": f"Unknown action: {action_type}"}
        except Exception as e:
            logger.error("action_execution_error", action=action_type, error=str(e))
            result = {"success": False, "error": str(e)}

        return result

    async def _log(self, action: Dict, result: Dict, observation: Dict) -> None:
        """Log findings to vault."""
        # Record action in history
        self.action_history.append(
            {
                "step": self.step_count,
                "action": action,
                "result": result,
                "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z",
            }
        )

        # Record findings
        if not result.get("success", False):
            self.findings.append(
                {
                    "step": self.step_count,
                    "severity": "high" if action.get("action") != "screenshot" else "info",
                    "title": f"Action failed: {action.get('action')}",
                    "description": result.get("error", "Unknown error"),
                    "selector": action.get("selector", ""),
                }
            )

        # Update vault with progress
        try:
            self.vault.update_frontmatter(
                self.memory_node,
                {
                    "status": "active",
                    "last_action": action.get("action", "unknown"),
                    "step_count": self.step_count,
                    "progress_percent": min(self.step_count * 2, 95),
                    "findings_count": len(self.findings),
                    "screenshots": self.screenshots,
                    "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z",
                },
            )
        except Exception as e:
            logger.error("vault_update_error", error=str(e))

    async def run(self) -> None:
        """Main execution loop."""
        logger.info("ui_explorer_starting", agent_id=self.agent_id)

        # Read objective from memory node
        try:
            node = self.vault.read_node(self.memory_node)
            objective = node["frontmatter"].get("objective", "")
            logger.info("objective_loaded", objective=objective[:100])
        except Exception as e:
            logger.error("failed_to_read_objective", error=str(e))
            await self._fail(f"Cannot read objective: {e}")
            return

        # Extract URL from objective
        url = self._extract_url(objective)
        if not url:
            logger.error("no_url_in_objective")
            await self._fail("No URL found in objective")
            return

        # Start browser
        try:
            await self.browser.start()
            logger.info("browser_started", headless=self.browser.headless)
        except Exception as e:
            logger.error("browser_start_failed", error=str(e))
            await self._fail(f"Cannot start browser: {e}")
            return

        # Navigate to initial URL
        try:
            result = await self.browser.visit(url)
            if not result["success"]:
                await self._fail(f"Cannot navigate to {url}: {result.get('error')}")
                return
            logger.info("page_loaded", url=url, status=result.get("status"))
        except Exception as e:
            logger.error("navigation_failed", error=str(e))
            await self._fail(f"Navigation failed: {e}")
            return

        # Main observe-plan-act loop
        try:
            while self.step_count < MAX_STEPS:
                # Check timeout
                elapsed = (datetime.now(timezone.utc) - self.start_time).total_seconds()
                if elapsed > MAX_DURATION_SECONDS:
                    logger.warning("max_duration_reached", elapsed=elapsed)
                    break

                self.step_count += 1
                logger.info("step_start", step=self.step_count)

                # Observe
                observation = await self._observe()

                # Plan
                action = await self._plan(objective, observation)

                # Check for completion
                if action.get("action") == "complete":
                    logger.info("objective_complete", step=self.step_count)
                    break

                # Act
                result = await self._act(action)

                # Log
                await self._log(action, result, observation)

                # Small delay between actions
                await asyncio.sleep(0.5)

            # Generate final report
            await self._complete()

        except Exception as e:
            logger.error("execution_error", error=str(e))
            await self._fail(str(e))
        finally:
            await self.browser.close()
            logger.info("browser_closed")

    def _extract_url(self, text: str) -> Optional[str]:
        """Extract URL from text."""
        import re

        match = re.search(r'https?://[^\s<>"{}|\\^`\[\]]+', text)
        if match:
            return match.group(0).rstrip(".,;:!?)")
        return None

    async def _complete(self) -> None:
        """Mark task as completed."""
        # Calculate confidence based on findings
        confidence = 100 - (len(self.findings) * 5)
        confidence = max(0, min(100, confidence))

        # Determine result
        result = (
            "pass" if len(self.findings) == 0 else "warning" if len(self.findings) < 3 else "fail"
        )

        # Build final report content
        report_content = f"""# UI Explorer Report

## Objective
{self.vault.read_node(self.memory_node)["frontmatter"].get("objective", "")}

## Execution Summary
- **Steps Executed**: {self.step_count}
- **Findings**: {len(self.findings)}
- **Confidence Score**: {confidence}%
- **Result**: {result.upper()}

## Actions Taken
"""
        for action in self.action_history:
            report_content += f"\n### Step {action['step']}: {action['action']['action']}\n"
            report_content += f"- **Reasoning**: {action['action'].get('reasoning', 'N/A')}\n"
            report_content += f"- **Result**: {'✅ Success' if action['result'].get('success') else '❌ Failed'}\n"
            if action["action"].get("selector"):
                report_content += f"- **Selector**: `{action['action']['selector']}`\n"

        if self.findings:
            report_content += "\n## Findings\n\n"
            for finding in self.findings:
                severity_emoji = {
                    "critical": "🔴",
                    "high": "🟠",
                    "medium": "🟡",
                    "low": "🔵",
                    "info": "⚪",
                }
                emoji = severity_emoji.get(finding["severity"], "⚪")
                report_content += f"- {emoji} **{finding['title']}**: {finding['description']}\n"

        if self.screenshots:
            report_content += "\n## Screenshots\n\n"
            for ss in self.screenshots:
                report_content += f"- `{ss}`\n"

        # Update memory node
        try:
            node = self.vault.read_node(self.memory_node)
            self.vault.write_node(
                self.memory_node,
                content=node["content"] + "\n\n" + report_content,
                frontmatter={
                    **node["frontmatter"],
                    "status": "completed",
                    "result": result,
                    "end_time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z",
                    "step_count": self.step_count,
                    "findings_count": len(self.findings),
                    "screenshots": self.screenshots,
                    "confidence_score": confidence,
                    "progress_percent": 100,
                },
            )
            logger.info("task_completed", result=result, confidence=confidence)
        except Exception as e:
            logger.error("completion_error", error=str(e))

    async def _fail(self, error: str) -> None:
        """Mark task as failed."""
        try:
            self.vault.update_frontmatter(
                self.memory_node,
                {
                    "status": "failed",
                    "result": "fail",
                    "error": error,
                    "end_time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z",
                    "progress_percent": 100,
                },
            )
            logger.error("task_failed", error=error)
        except Exception as e:
            logger.error("fail_update_error", error=str(e))


async def run_agent(agent_id: str, memory_node: str):
    """Entry point for agent worker."""
    explorer = LLMDrivenUIExplorer(agent_id, memory_node)
    await explorer.run()


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python worker_llm.py <agent_id> <memory_node_path>")
        sys.exit(1)

    agent_id = sys.argv[1]
    memory_node = sys.argv[2]

    asyncio.run(run_agent(agent_id, memory_node))
