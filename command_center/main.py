"""
Command Center Backend - FastAPI + HTMX + SSE
Dark Mode Dashboard for Obsidian-backed Multi-Agent Testing
"""

import json
import asyncio
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Dict, List, Optional, cast
from fastapi import FastAPI, Request, Form
from fastapi.responses import StreamingResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from pathlib import Path
from command_center.obsidian_reader import reader
from command_center.chatbot import chat_engine, TEST_TYPES

# MCP Server Configuration
import os

MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8080")

app = FastAPI(title="Vectra QA Command Center")


@app.get("/health")
async def health_check():
    """Health check endpoint for Docker."""
    return {"status": "ok"}


@app.get("/ready")
async def readiness_check():
    """Readiness check endpoint."""
    return {"status": "ready"}


async def call_mcp_tool(tool_name: str, params: dict) -> dict:
    """Call an MCP tool on the MCP server via HTTP."""
    import httpx

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{MCP_SERVER_URL}/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": tool_name, "arguments": params},
            },
            timeout=30.0,
        )
        result = response.json()
        # MCP wraps the result in result.result
        if "result" in result:
            return cast(Dict[str, Any], result["result"])
        return {"status": "error", "error": result.get("error", "Unknown error")}


def json_serialize(obj):
    """Custom JSON serializer that handles datetime objects from YAML frontmatter."""
    if isinstance(obj, datetime):
        return obj.strftime("%Y-%m-%dT%H:%M:%S") + "Z"
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


# CORS for HTMX
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files
app.mount("/static", StaticFiles(directory="command_center/static"), name="static")

# Ensure screenshots directory exists
screenshots_dir = Path("obsidian_vault/Screenshots")
screenshots_dir.mkdir(parents=True, exist_ok=True)
app.mount("/screenshots", StaticFiles(directory=str(screenshots_dir)), name="screenshots")


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Serve the main dashboard HTML."""
    with open("command_center/static/index.html", "r") as f:
        return f.read()


@app.get("/api/orchestrator/status")
async def orchestrator_status():
    """Get current orchestrator status."""
    return reader.get_orchestrator_status()


@app.get("/api/agents/active")
async def active_agents():
    """Get list of currently active agents."""
    return {"agents": reader.get_active_agents()}


@app.get("/api/nodes/global")
async def global_nodes():
    """Get all global memory nodes."""
    nodes = reader.get_global_nodes()
    return {name: node.to_dict() if node else None for name, node in nodes.items()}


@app.get("/api/nodes/{node_path:path}")
async def read_node(node_path: str):
    """Read a specific Obsidian node."""
    node = reader.read_node(node_path)
    if not node:
        return {"error": "Node not found"}
    return node.to_dict()


async def event_generator() -> AsyncGenerator[str, None]:
    """Generate SSE events for live updates."""
    while True:
        # Get current state
        orchestrator = reader.get_orchestrator_status()
        agents = reader.get_active_agents()
        nodes = reader.get_global_nodes()

        data = {
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z",
            "orchestrator": orchestrator,
            "agents": agents,
            "nodes": {name: node.to_dict() if node else None for name, node in nodes.items()},
        }

        yield f"data: {json.dumps(data, default=json_serialize)}\n\n"
        await asyncio.sleep(2)


@app.post("/api/tests/run")
async def run_test(url: str = Form(...), test_type: str = Form(...)):
    """Run a test against a target URL by spawning agents."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")

    test_configs = {
        "homepage": {
            "role": "ui_explorer",
            "objective": f"Test the homepage at {url}. Verify page loads, check hero section, navigation, CTAs, footer, and console errors.",
            "memory_node": f"Runs/Homepage_Test_{timestamp}.md",
        },
        "navigation": {
            "role": "ui_explorer",
            "objective": f"Test navigation on {url}. Click all menu items, verify no 404s, check page titles, test mobile menu.",
            "memory_node": f"Runs/Navigation_Test_{timestamp}.md",
        },
        "contact": {
            "role": "ui_explorer",
            "objective": f"Test contact form on {url}. Verify form fields, test validation, check accessibility.",
            "memory_node": f"Runs/Contact_UI_Test_{timestamp}.md",
        },
        "api": {
            "role": "data_validator",
            "objective": f"Monitor API calls on {url}. Intercept requests, check response codes, validate payloads, verify headers.",
            "memory_node": f"Runs/API_Test_{timestamp}.md",
        },
        "accessibility": {
            "role": "ui_explorer",
            "objective": f"Accessibility audit of {url}. Test keyboard navigation, check ARIA labels, verify alt text, check color contrast.",
            "memory_node": f"Runs/Accessibility_Test_{timestamp}.md",
        },
        "responsive": {
            "role": "ui_explorer",
            "objective": f"Test responsive design of {url} on desktop (1920x1080), tablet (768x1024), and mobile (375x667).",
            "memory_node": f"Runs/Responsive_Test_{timestamp}.md",
        },
        "full": {
            "role": "ui_explorer",
            "objective": f"Comprehensive test of {url}. Homepage, navigation, forms, responsive design, and basic accessibility checks.",
            "memory_node": f"Runs/Full_Test_{timestamp}.md",
        },
    }

    if test_type not in test_configs:
        return JSONResponse(
            status_code=400,
            content={
                "error": f"Unknown test type: {test_type}. Available: {list(test_configs.keys())}"
            },
        )

    config = test_configs[test_type]

    try:
        result = await call_mcp_tool(
            "spawn_agent",
            {
                "role": config["role"],
                "objective": config["objective"],
                "memory_node": config["memory_node"],
            },
        )

        if result.get("status") == "success":
            spawn_result = result.get("result", {})
            return {
                "status": "success",
                "message": f"Test '{test_type}' initiated for {url}",
                "agent_id": spawn_result.get("agent_id"),
                "memory_node": config["memory_node"],
                "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z",
            }
        else:
            return JSONResponse(
                status_code=500, content={"error": result.get("error", "Failed to spawn agent")}
            )
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/api/tests/types")
async def get_test_types():
    """Get available test types."""
    return {
        "types": [
            {
                "id": "homepage",
                "name": "Homepage",
                "description": "Test homepage structure and content",
            },
            {
                "id": "navigation",
                "name": "Navigation",
                "description": "Test all navigation links and page transitions",
            },
            {
                "id": "contact",
                "name": "Contact Form",
                "description": "Test contact form functionality",
            },
            {"id": "api", "name": "API Monitoring", "description": "Monitor backend API calls"},
            {
                "id": "accessibility",
                "name": "Accessibility",
                "description": "WCAG compliance audit",
            },
            {
                "id": "responsive",
                "name": "Responsive Design",
                "description": "Test on multiple viewports",
            },
            {"id": "full", "name": "Full Suite", "description": "Comprehensive test coverage"},
        ]
    }


@app.get("/api/results")
async def list_results():
    """List all test runs (active + completed), sorted by date desc."""
    runs = []
    for node in reader.get_run_nodes():
        if node and node.frontmatter:
            fm = node.frontmatter
            runs.append(
                {
                    "agent_id": fm.get("agent_id", "unknown"),
                    "role": fm.get("agent_role", "unknown"),
                    "status": fm.get("status", "unknown"),
                    "result": fm.get("result", "pending"),
                    "objective": fm.get("objective", ""),
                    "node_path": node.path,
                    "progress_percent": fm.get("progress_percent", 0),
                    "screenshots": fm.get("screenshots", []),
                    "spawned_at": fm.get("spawned_at", ""),
                    "end_time": fm.get("end_time", ""),
                    "timestamp": fm.get("timestamp", ""),
                }
            )

    # Sort by spawned_at desc (newest first)
    runs.sort(key=lambda x: x.get("spawned_at", ""), reverse=True)
    return {"results": runs, "count": len(runs)}


@app.get("/api/results/{agent_id}")
async def get_result(agent_id: str):
    """Get full test result data for a specific agent."""
    # Find the node by agent_id
    for node in reader.get_run_nodes():
        if node and node.frontmatter and node.frontmatter.get("agent_id") == agent_id:
            fm = node.frontmatter
            content = node.content

            # Extract structured report data
            sections = _extract_sections(content)
            recommendations = _extract_recommendations(content)
            summary = _extract_summary(content)

            return {
                "agent_id": fm.get("agent_id", "unknown"),
                "role": fm.get("agent_role", "unknown"),
                "status": fm.get("status", "unknown"),
                "result": fm.get("result", "pending"),
                "objective": fm.get("objective", ""),
                "node_path": node.path,
                "progress_percent": fm.get("progress_percent", 0),
                "screenshots": fm.get("screenshots", []),
                "spawned_at": fm.get("spawned_at", ""),
                "end_time": fm.get("end_time", ""),
                "timestamp": fm.get("timestamp", ""),
                "last_action": fm.get("last_action", ""),
                "content": content,
                "findings": _extract_findings(content),
                "sections": sections,
                "recommendations": recommendations,
                "summary": summary,
            }

    return JSONResponse(status_code=404, content={"error": "Test result not found"})


def _extract_findings(content: str) -> List[Dict[str, Any]]:
    """Parse findings from markdown content."""
    findings: List[Dict[str, Any]] = []
    lines = content.split("\n")
    current_finding: Optional[Dict[str, Any]] = None

    for line in lines:
        line = line.strip()
        if line.startswith("## ["):
            # New timestamped section
            if current_finding:
                findings.append(current_finding)
            current_finding = {
                "timestamp": line.split("]")[0].replace("## [", ""),
                "title": line.split("]")[1].strip() if "]" in line else "",
                "items": [],
            }
        elif line.startswith("- **") and current_finding:
            current_finding["items"].append(line)
        elif line.startswith("## ") and not line.startswith("## ["):
            # Section headers
            if current_finding:
                findings.append(current_finding)
                current_finding = None

    if current_finding:
        findings.append(current_finding)

    return findings


def _extract_sections(content: str) -> list:
    """Parse structured report sections from markdown content."""
    sections: List[Dict[str, Any]] = []
    lines = content.split("\n")
    current_section: Optional[Dict[str, Any]] = None
    current_findings: List[Dict[str, Any]] = []
    current_metrics: Dict[str, Any] = {}
    in_metrics = False

    for line in lines:
        line_stripped = line.strip()

        # Detect section headers (## ✅ Title or ## ❌ Title, etc.)
        if (
            line_stripped.startswith("## ")
            and not line_stripped.startswith("## [")
            and not line_stripped.startswith("## Test Report")
        ):
            # Save previous section
            if current_section:
                current_section["findings"] = current_findings
                current_section["metrics"] = current_metrics
                sections.append(current_section)

            # Parse status from emoji
            status = "info"
            title = line_stripped[3:]
            if title.startswith("✅ "):
                status = "pass"
                title = title[2:].strip()
            elif title.startswith("❌ "):
                status = "fail"
                title = title[2:].strip()
            elif title.startswith("⚠️ "):
                status = "warning"
                title = title[2:].strip()
            elif title.startswith("ℹ️ "):
                status = "info"
                title = title[2:].strip()

            current_section = {"title": title, "status": status, "findings": [], "metrics": {}}
            current_findings = []
            current_metrics = {}
            in_metrics = False

        elif line_stripped.startswith("### Metrics"):
            in_metrics = True
        elif line_stripped.startswith("### Findings"):
            in_metrics = False
        elif line_stripped.startswith("- ") and current_section and not in_metrics:
            # Parse finding with severity
            finding_text = line_stripped[2:]
            severity = "info"
            title = finding_text
            description = ""

            # Check for severity emoji
            if finding_text.startswith("🔴 "):
                severity = "critical"
                finding_text = finding_text[2:]
            elif finding_text.startswith("🟠 "):
                severity = "high"
                finding_text = finding_text[2:]
            elif finding_text.startswith("🟡 "):
                severity = "medium"
                finding_text = finding_text[2:]
            elif finding_text.startswith("🔵 "):
                severity = "low"
                finding_text = finding_text[2:]
            elif finding_text.startswith("⚪ "):
                severity = "info"
                finding_text = finding_text[2:]

            # Split title and description
            if ": " in finding_text:
                parts = finding_text.split(": ", 1)
                title = parts[0].strip()
                description = parts[1].strip()
            elif "**" in finding_text:
                # Handle bold format
                import re

                match = re.search(r"\*\*(.+?)\*\*:\s*(.+)", finding_text)
                if match:
                    title = match.group(1).strip()
                    description = match.group(2).strip()
                else:
                    title = finding_text

            current_findings.append(
                {"title": title, "description": description, "severity": severity}
            )
        elif line_stripped.startswith("- **") and current_section and in_metrics:
            # Parse metric
            metric_text = line_stripped[2:]
            if "**: " in metric_text or "**:" in metric_text:
                parts = metric_text.split("**:", 1)
                key = parts[0].replace("**", "").strip()
                value = parts[1].strip() if len(parts) > 1 else ""
                current_metrics[key] = value

    # Save last section
    if current_section:
        current_section["findings"] = current_findings
        current_section["metrics"] = current_metrics
        sections.append(current_section)

    return sections


def _extract_recommendations(content: str) -> list:
    """Parse recommendations from markdown content."""
    recommendations = []
    lines = content.split("\n")
    in_recommendations = False

    for line in lines:
        line_stripped = line.strip()
        if "## 📝 Recommendations" in line_stripped or "## Recommendations" in line_stripped:
            in_recommendations = True
            continue
        elif line_stripped.startswith("## ") and in_recommendations:
            break

        if in_recommendations and (
            line_stripped.startswith("1. ")
            or line_stripped.startswith("2. ")
            or line_stripped.startswith("3. ")
            or line_stripped.startswith("4. ")
            or line_stripped.startswith("5. ")
            or line_stripped.startswith("6. ")
            or line_stripped.startswith("7. ")
            or line_stripped.startswith("8. ")
            or line_stripped.startswith("9. ")
            or line_stripped.startswith("10. ")
        ):
            recommendations.append(line_stripped[3:].strip())

    return recommendations


def _extract_summary(content: str) -> dict:
    """Parse summary stats from report content."""
    summary = {"pass": 0, "fail": 0, "warning": 0, "total": 0}
    lines = content.split("\n")

    for line in lines:
        line_stripped = line.strip()
        if "| Sections Passed |" in line_stripped:
            try:
                summary["pass"] = int(line_stripped.split("|")[2].strip())
            except Exception:
                pass
        elif "| Sections Failed |" in line_stripped:
            try:
                summary["fail"] = int(line_stripped.split("|")[2].strip())
            except Exception:
                pass
        elif "| Warnings |" in line_stripped:
            try:
                summary["warning"] = int(line_stripped.split("|")[2].strip())
            except Exception:
                pass
        elif "| Total Checks |" in line_stripped:
            try:
                summary["total"] = int(line_stripped.split("|")[2].strip())
            except Exception:
                pass

    return summary


@app.get("/results/{agent_id}", response_class=HTMLResponse)
async def result_page(agent_id: str):
    """Serve the test result page HTML."""
    try:
        with open("command_center/static/result.html", "r") as f:
            return f.read()
    except FileNotFoundError:
        return HTMLResponse(content="<h1>Result page not found</h1>", status_code=404)


@app.get("/api/sse/stream")
async def sse_stream(request: Request):
    """Server-Sent Events endpoint for live dashboard updates."""
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@app.get("/api/sse/agents")
async def agents_sse(request: Request):
    """SSE endpoint specifically for agent updates."""

    async def agent_events():
        while True:
            agents = reader.get_active_agents()
            data = {
                "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z",
                "agents": agents,
                "count": len(agents),
            }
            yield f"data: {json.dumps(data, default=json_serialize)}\n\n"
            await asyncio.sleep(3)

    return StreamingResponse(
        agent_events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@app.get("/api/sse/orchestrator")
async def orchestrator_sse(request: Request):
    """SSE endpoint specifically for orchestrator feed updates."""

    async def orchestrator_events():
        while True:
            status = reader.get_orchestrator_status()
            data = {
                "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z",
                "status": status,
            }
            yield f"data: {json.dumps(data, default=json_serialize)}\n\n"
            await asyncio.sleep(2)

    return StreamingResponse(
        orchestrator_events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@app.get("/api/sse/results/{agent_id}")
async def result_sse(request: Request, agent_id: str):
    """SSE endpoint for live updates on a specific test result."""

    async def result_events():
        last_content = ""
        while True:
            # Find the node by agent_id
            node = None
            for n in reader.get_run_nodes():
                if n and n.frontmatter and n.frontmatter.get("agent_id") == agent_id:
                    node = n
                    break

            if node:
                fm = node.frontmatter
                current_content = node.content

                # Extract structured data
                sections = _extract_sections(current_content)
                recommendations = _extract_recommendations(current_content)
                summary = _extract_summary(current_content)

                data = {
                    "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z",
                    "agent_id": agent_id,
                    "status": fm.get("status", "unknown"),
                    "result": fm.get("result", "pending"),
                    "progress_percent": fm.get("progress_percent", 0),
                    "last_action": fm.get("last_action", ""),
                    "screenshots": fm.get("screenshots", []),
                    "end_time": fm.get("end_time", ""),
                    "findings": _extract_findings(current_content),
                    "sections": sections,
                    "recommendations": recommendations,
                    "summary": summary,
                    "content_changed": current_content != last_content,
                }

                last_content = current_content
                yield f"data: {json.dumps(data, default=json_serialize)}\n\n"

                # If completed or failed, keep streaming for a bit then stop
                if fm.get("status") in ["completed", "failed"]:
                    # Send one final update, then continue with heartbeat
                    await asyncio.sleep(2)
                    yield f"data: {json.dumps(data, default=json_serialize)}\n\n"
                    # After final update, send less frequently
                    await asyncio.sleep(5)
                    continue
            else:
                yield f"data: {json.dumps({'error': 'Test not found', 'agent_id': agent_id})}\n\n"

            await asyncio.sleep(2)

    return StreamingResponse(
        result_events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


# ═══════════════════════════════════════════════════
# CHATBOT ENDPOINTS
# ═══════════════════════════════════════════════════


@app.get("/api/chat/history")
async def get_chat_history(limit: int = 50):
    """Get chat conversation history."""
    try:
        messages = chat_engine.get_history(limit=limit)
        return {"messages": messages, "count": len(messages)}
    except Exception as e:
        return JSONResponse(
            status_code=500, content={"error": f"Failed to load chat history: {str(e)}"}
        )


@app.post("/api/chat/message")
async def chat_message(message: str = Form(...), stream: bool = Form(False)):
    """Process a chat message and return Vectra's response."""
    try:
        # Save user message
        chat_engine.add_message("user", message)

        # Process the message
        result = chat_engine.process_message(message)

        # Save assistant response
        chat_engine.add_message(
            "assistant",
            result["message"],
            metadata=result.get("plan") or result.get("agent_id") or {},
        )

        return result
    except Exception as e:
        import traceback

        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": f"Chat processing error: {str(e)}"})


@app.post("/api/chat/execute")
async def execute_chat_plan(url: str = Form(...), tests: str = Form(...)):
    """Execute a test plan confirmed by the user."""
    try:
        # Parse tests (comma-separated)
        test_list = [t.strip() for t in tests.split(",")]

        # Validate tests
        valid_tests = []
        for test in test_list:
            if test in TEST_TYPES:
                valid_tests.append(test)

        if not valid_tests:
            return JSONResponse(status_code=400, content={"error": "No valid test types specified"})

        # Spawn agents for each test
        agent_ids = []
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")

        for i, test_type in enumerate(valid_tests):
            config = TEST_TYPES[test_type]
            role = config["role"]

            # Build objective
            if test_type == "full":
                objective = f"Comprehensive test of {url}. Full suite including homepage, navigation, forms, responsive design, and accessibility checks."
            elif test_type == "homepage":
                objective = f"Test the homepage at {url}. Verify page loads, check hero section, navigation, CTAs, footer, and console errors."
            elif test_type == "navigation":
                objective = f"Test navigation on {url}. Click all menu items, verify no 404s, check page titles, test mobile menu."
            elif test_type == "contact":
                objective = f"Test contact form on {url}. Verify form fields, test validation, check accessibility."
            elif test_type == "api":
                objective = f"Monitor API calls on {url}. Intercept requests, check response codes, validate payloads, verify headers."
            elif test_type == "accessibility":
                objective = f"Accessibility audit of {url}. Test keyboard navigation, check ARIA labels, verify alt text, check color contrast."
            elif test_type == "responsive":
                objective = f"Test responsive design of {url} on desktop (1920x1080), tablet (768x1024), and mobile (375x667)."
            else:
                objective = f"Test {test_type} on {url}"

            memory_node = f"Runs/Chat_{test_type.title()}_Test_{timestamp}_{i}.md"

            # Call MCP to spawn agent
            result = await call_mcp_tool(
                "spawn_agent", {"role": role, "objective": objective, "memory_node": memory_node}
            )

            if result.get("status") == "success":
                spawn_result = result.get("result", {})
                agent_ids.append(spawn_result.get("agent_id"))

        # Save system message about execution
        chat_engine.add_message(
            "system",
            f"Executed test plan: {', '.join(valid_tests)} on {url}",
            metadata={"executed": ",".join(agent_ids)},
        )

        return {
            "status": "success",
            "message": f"Launched {len(agent_ids)} test(s) on {url}",
            "agent_ids": agent_ids,
            "tests": valid_tests,
            "url": url,
        }

    except Exception as e:
        import traceback

        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": f"Execution error: {str(e)}"})


@app.get("/api/chat/sse")
async def chat_sse(request: Request, message: str):
    """SSE endpoint for streaming chat responses."""

    async def stream_events():
        try:
            # Save user message
            chat_engine.add_message("user", message)

            # Get history for context
            history = chat_engine.get_history(limit=20)

            # Stream response
            full_response = ""
            async for chunk in chat_engine.stream_response(message, history):
                full_response += chunk
                yield f"data: {json.dumps({'chunk': chunk, 'done': False})}\n\n"
                await asyncio.sleep(0.01)

            # Save complete response
            chat_engine.add_message("assistant", full_response)

            # Signal completion
            yield f"data: {json.dumps({'chunk': '', 'done': True, 'full_response': full_response})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'error': str(e), 'done': True})}\n\n"

    return StreamingResponse(
        stream_events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@app.get("/api/chat/interpret/{agent_id}")
async def interpret_test_results(agent_id: str):
    """Get LLM-interpreted results for a specific test."""
    try:
        # Find the test result
        for node in reader.get_run_nodes():
            if node and node.frontmatter and node.frontmatter.get("agent_id") == agent_id:
                fm = node.frontmatter
                content = node.content

                # Build result data
                result_data = {
                    "agent_id": fm.get("agent_id", "unknown"),
                    "role": fm.get("agent_role", "unknown"),
                    "status": fm.get("status", "unknown"),
                    "result": fm.get("result", "pending"),
                    "objective": fm.get("objective", ""),
                    "overall_status": fm.get("result", "pending"),
                    "summary": _extract_summary(content),
                    "sections": _extract_sections(content),
                    "recommendations": _extract_recommendations(content),
                    "screenshots": fm.get("screenshots", []),
                }

                # Generate interpretation
                interpretation = chat_engine.interpret_results(agent_id, result_data)

                # Save to chat log
                chat_engine.add_message("assistant", interpretation, metadata={"result": agent_id})

                return {
                    "agent_id": agent_id,
                    "interpretation": interpretation,
                    "result_data": result_data,
                }

        return JSONResponse(status_code=404, content={"error": "Test result not found"})

    except Exception as e:
        import traceback

        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": f"Interpretation error: {str(e)}"})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=3000)
