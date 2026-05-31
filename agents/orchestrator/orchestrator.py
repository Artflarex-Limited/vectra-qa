"""
Real Orchestrator for Vectra QA

Uses LLM planning to decompose test objectives into discrete tasks,
spawn specialized agents, monitor their progress, and compile reports.

Reads soul.md and agents.md for behavioral context.
"""

import os
import json
import asyncio
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

# Import MCP tools for agent spawning
from mcp_server.tools import get_vault, get_spawner
from mcp_server.llm_router import llm_router

logger = structlog.get_logger()

VAULT_PATH = Path(os.getenv("OBSIDIAN_VAULT_PATH", "/app/obsidian_vault"))
ORCHESTRATOR_MODEL = os.getenv("ORCHESTRATOR_MODEL", "openai/gpt-4o")


class Orchestrator:
    """
    The Orchestrator is the brain of Vectra QA.

    It receives high-level test objectives, uses LLM reasoning to plan
    and decompose tasks, spawns specialized agents, monitors their
    execution, and compiles comprehensive reports.
    """

    def __init__(self):
        self.vault = get_vault()
        self.spawner = get_spawner()
        self.soul = self._load_persona("soul.md")
        self.agents_context = self._load_persona("agents.md")
        logger.info("orchestrator_initialized")

    def _load_persona(self, filename: str) -> str:
        """Load orchestrator persona files."""
        persona_path = VAULT_PATH / ".." / "agents" / "orchestrator" / filename
        # Try multiple paths
        paths = [
            persona_path,
            Path("/app/agents/orchestrator") / filename,
            Path("agents/orchestrator") / filename,
            Path(__file__).parent.parent / "agents" / "orchestrator" / filename,
        ]

        for path in paths:
            if path.exists():
                return path.read_text(encoding="utf-8")

        logger.warning(
            "persona_file_not_found", filename=filename, checked_paths=[str(p) for p in paths]
        )
        return ""

    def _build_system_prompt(self) -> str:
        """Build system prompt from soul and agents context."""
        return f"""{self.soul}

## Agent Context
{self.agents_context}

## Current Time
{datetime.now(timezone.utc).isoformat()}Z

You are the Orchestrator. Your job is to plan tests and coordinate agents.
"""

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
    async def plan_tests(self, objective: str, url: str) -> Dict[str, Any]:
        """
        Use LLM to plan tests based on objective.

        Returns a structured test plan with discrete tasks.
        """
        prompt = f"""
Analyze this testing objective and create a detailed test plan.

Objective: {objective}
Target URL: {url}

Create a test plan with discrete, executable tasks. Each task should be completable by a single agent.

Respond in JSON format:
{{
    "test_plan_id": "unique-id",
    "summary": "Brief description of what will be tested",
    "tasks": [
        {{
            "task_id": "task-1",
            "role": "ui_explorer|data_validator|auth_tester|visual_regression_tester|performance_tester|api_contract_tester|accessibility_tester|multi_browser_tester",
            "objective": "Specific, actionable objective for this agent",
            "memory_node": "Runs/Descriptive_Name.md",
            "depends_on": ["task-id-or-null"],
            "estimated_duration_seconds": 60,
            "success_criteria": "How to determine if this task passed"
        }}
    ],
    "parallel_groups": [["task-1", "task-2"], ["task-3"]],
    "overall_success_criteria": "How to determine if the entire test run passed"
}}

Guidelines:
- Break down into 3-7 discrete tasks
- Tasks should be specific and actionable
- Identify dependencies between tasks
- Group parallelizable tasks together
- Include clear success criteria
"""

        try:
            response = llm_router.complete(
                model=ORCHESTRATOR_MODEL,
                messages=[
                    {"role": "system", "content": self._build_system_prompt()},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=2000,
            )

            # Parse JSON from response
            content = response.content.strip()
            # Handle markdown code blocks
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            plan = json.loads(content)
            logger.info(
                "test_plan_generated",
                plan_id=plan.get("test_plan_id"),
                task_count=len(plan.get("tasks", [])),
            )
            return plan

        except json.JSONDecodeError as e:
            logger.error(
                "failed_to_parse_test_plan", error=str(e), raw_response=response.content[:500]
            )
            # Fallback: create a simple single-task plan
            return {
                "test_plan_id": f"fallback-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
                "summary": f"Direct test of {url}",
                "tasks": [
                    {
                        "task_id": "task-1",
                        "role": "ui_explorer",
                        "objective": objective,
                        "memory_node": f"Runs/Direct_Test_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}.md",
                        "depends_on": None,
                        "estimated_duration_seconds": 120,
                        "success_criteria": "Page loads and basic checks pass",
                    }
                ],
                "parallel_groups": [["task-1"]],
                "overall_success_criteria": "Basic page functionality verified",
            }
        except Exception as e:
            logger.error("test_plan_generation_failed", error=str(e))
            raise

    async def execute_test_plan(self, objective: str, url: str) -> Dict[str, Any]:
        """
        Execute a complete test plan.

        1. Generate test plan via LLM
        2. Initialize Test_Run_Master
        3. Execute tasks in dependency order
        4. Monitor agent progress
        5. Compile final report
        """
        # Generate plan
        plan = await self.plan_tests(objective, url)
        plan_id = plan["test_plan_id"]

        # Initialize Test_Run_Master
        await self._initialize_run_master(plan_id, objective, url, plan)

        # Execute tasks by parallel groups
        completed_tasks = {}
        failed_tasks = {}

        for group_idx, group in enumerate(plan["parallel_groups"]):
            logger.info("executing_parallel_group", group_index=group_idx, tasks=group)

            # Spawn agents for this group
            spawned_agents = []
            for task_id in group:
                task = next((t for t in plan["tasks"] if t["task_id"] == task_id), None)
                if not task:
                    continue

                # Check dependencies
                if task.get("depends_on"):
                    for dep in task["depends_on"]:
                        if dep not in completed_tasks:
                            logger.warning("dependency_not_met", task=task_id, dependency=dep)
                            failed_tasks[task_id] = {"reason": f"Dependency {dep} not met"}
                            continue

                # Spawn agent
                try:
                    result = self.spawner.spawn_agent(
                        role=task["role"],
                        objective=task["objective"],
                        memory_node=task["memory_node"],
                    )

                    if result["status"] == "active":
                        spawned_agents.append(
                            {
                                "task_id": task_id,
                                "agent_id": result["agent_id"],
                                "memory_node": task["memory_node"],
                            }
                        )
                        logger.info("agent_spawned", task=task_id, agent_id=result["agent_id"])
                    else:
                        logger.error("agent_spawn_failed", task=task_id, error=result.get("error"))
                        failed_tasks[task_id] = {"reason": result.get("error", "Unknown error")}

                except Exception as e:
                    logger.error("spawn_exception", task=task_id, error=str(e))
                    failed_tasks[task_id] = {"reason": str(e)}

            # Wait for all agents in this group to complete
            if spawned_agents:
                await self._wait_for_agents(spawned_agents, completed_tasks, failed_tasks)

        # Compile final report
        report = await self._compile_report(plan_id, plan, completed_tasks, failed_tasks)

        return report

    async def _initialize_run_master(
        self, plan_id: str, objective: str, url: str, plan: Dict
    ) -> None:
        """Initialize the Test_Run_Master node."""
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z"

        self.vault.write_node(
            "Global/Test_Run_Master.md",
            content=f"""# Test Run: {plan_id}

## Objective
{objective}

## Target URL
{url}

## Plan Summary
{plan['summary']}

## Tasks
{chr(10).join(f'- **{t["task_id"]}**: {t["objective"]} (via {t["role"]})' for t in plan['tasks'])}

## Status
- **Started**: {timestamp}
- **Status**: running

## Orchestrator Notes
- Test plan generated and execution started
""",
            frontmatter={
                "test_plan_id": plan_id,
                "status": "running",
                "phase": "execution",
                "objective": objective,
                "url": url,
                "started_at": timestamp,
                "task_count": len(plan["tasks"]),
                "completed_tasks": 0,
                "failed_tasks": 0,
            },
        )

        logger.info("test_run_master_initialized", plan_id=plan_id)

    async def _wait_for_agents(
        self, agents: List[Dict], completed: Dict, failed: Dict, timeout: int = 600
    ) -> None:
        """Wait for spawned agents to complete."""
        pending = {a["agent_id"]: a for a in agents}
        start_time = asyncio.get_event_loop().time()

        while pending:
            # Check timeout
            if asyncio.get_event_loop().time() - start_time > timeout:
                for agent_id, agent_info in pending.items():
                    failed[agent_info["task_id"]] = {"reason": "Timeout waiting for agent"}
                    logger.error("agent_timeout", agent_id=agent_id, task=agent_info["task_id"])
                break

            # Check each pending agent
            for agent_id, agent_info in list(pending.items()):
                try:
                    # Read agent's memory node
                    node = self.vault.read_node(agent_info["memory_node"])
                    status = node["frontmatter"].get("status", "unknown")
                    result = node["frontmatter"].get("result", "pending")

                    if status in ["completed", "failed", "terminated"]:
                        if result == "pass" or status == "completed":
                            completed[agent_info["task_id"]] = {
                                "agent_id": agent_id,
                                "status": status,
                                "result": result,
                            }
                            logger.info(
                                "agent_completed",
                                agent_id=agent_id,
                                task=agent_info["task_id"],
                                result=result,
                            )
                        else:
                            failed[agent_info["task_id"]] = {
                                "agent_id": agent_id,
                                "status": status,
                                "result": result,
                                "reason": node["frontmatter"].get("error", "Unknown error"),
                            }
                            logger.warning(
                                "agent_failed", agent_id=agent_id, task=agent_info["task_id"]
                            )

                        del pending[agent_id]

                except Exception as e:
                    logger.error("error_checking_agent", agent_id=agent_id, error=str(e))

            if pending:
                await asyncio.sleep(5)  # Poll every 5 seconds

        logger.info("agent_group_complete", completed=len(completed), failed=len(failed))

    async def _compile_report(
        self, plan_id: str, plan: Dict, completed: Dict, failed: Dict
    ) -> Dict[str, Any]:
        """Compile final test report."""
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z"
        total_tasks = len(plan["tasks"])
        completed_count = len(completed)
        failed_count = len(failed)

        # Determine overall result
        if failed_count == 0:
            overall_result = "pass"
        elif completed_count == 0:
            overall_result = "fail"
        else:
            overall_result = "partial"

        # Update Test_Run_Master
        self.vault.update_frontmatter(
            "Global/Test_Run_Master.md",
            {
                "status": "completed",
                "phase": "reporting",
                "overall_result": overall_result,
                "completed_tasks": completed_count,
                "failed_tasks": failed_count,
                "completed_at": timestamp,
            },
        )

        # Append report to Test_Run_Master
        report_content = f"""

## Final Report

### Execution Summary
- **Plan ID**: {plan_id}
- **Completed**: {timestamp}
- **Overall Result**: {overall_result.upper()}
- **Tasks Completed**: {completed_count}/{total_tasks}
- **Tasks Failed**: {failed_count}/{total_tasks}

### Completed Tasks
{chr(10).join(f'- ✅ **{task_id}**: Agent {info["agent_id"]} - {info["result"]}' for task_id, info in completed.items()) or "_None_"}

### Failed Tasks
{chr(10).join(f'- ❌ **{task_id}**: {info.get("reason", "Unknown error")}' for task_id, info in failed.items()) or "_None_"}

### Findings
_TODO: Aggregate findings from all agent reports_

### Recommendations
_TODO: Generate recommendations based on findings_
"""

        node = self.vault.read_node("Global/Test_Run_Master.md")
        self.vault.write_node(
            "Global/Test_Run_Master.md",
            content=node["content"] + report_content,
            frontmatter=node["frontmatter"],
        )

        logger.info("report_compiled", plan_id=plan_id, overall_result=overall_result)

        return {
            "plan_id": plan_id,
            "status": "completed",
            "overall_result": overall_result,
            "completed_tasks": completed_count,
            "failed_tasks": failed_count,
            "total_tasks": total_tasks,
            "completed_at": timestamp,
        }


# Global orchestrator instance
_orchestrator_instance: Optional[Orchestrator] = None


def get_orchestrator() -> Orchestrator:
    """Get or create the Orchestrator instance."""
    global _orchestrator_instance
    if _orchestrator_instance is None:
        _orchestrator_instance = Orchestrator()
    return _orchestrator_instance


async def execute_test_plan(objective: str, url: str) -> Dict[str, Any]:
    """Convenience function to execute a test plan."""
    orchestrator = get_orchestrator()
    return await orchestrator.execute_test_plan(objective, url)
