"""
Command Center Backend - FastAPI + HTMX + SSE
Dark Mode Dashboard for Obsidian-backed Multi-Agent Testing
"""

import json
import asyncio
from datetime import datetime
from typing import AsyncGenerator
from fastapi import FastAPI, Request, Form
from fastapi.responses import StreamingResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from command_center.obsidian_reader import reader

# Import MCP tools for spawning agents
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from mcp_server.tools import execute_tool

app = FastAPI(title="Vectra QA Command Center")


def json_serialize(obj):
    """Custom JSON serializer that handles datetime objects from YAML frontmatter."""
    if isinstance(obj, datetime):
        return obj.isoformat() + "Z"
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
    return {
        name: node.to_dict() if node else None
        for name, node in nodes.items()
    }


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
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "orchestrator": orchestrator,
            "agents": agents,
            "nodes": {
                name: node.to_dict() if node else None
                for name, node in nodes.items()
            }
        }
        
        yield f"data: {json.dumps(data, default=json_serialize)}\n\n"
        await asyncio.sleep(2)


@app.post("/api/tests/run")
async def run_test(url: str = Form(...), test_type: str = Form(...)):
    """Run a test against a target URL by spawning agents."""
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    
    test_configs = {
        "homepage": {
            "role": "ui_explorer",
            "objective": f"Test the homepage at {url}. Verify page loads, check hero section, navigation, CTAs, footer, and console errors.",
            "memory_node": f"Runs/Homepage_Test_{timestamp}.md"
        },
        "navigation": {
            "role": "ui_explorer",
            "objective": f"Test navigation on {url}. Click all menu items, verify no 404s, check page titles, test mobile menu.",
            "memory_node": f"Runs/Navigation_Test_{timestamp}.md"
        },
        "contact": {
            "role": "ui_explorer",
            "objective": f"Test contact form on {url}. Verify form fields, test validation, check accessibility.",
            "memory_node": f"Runs/Contact_UI_Test_{timestamp}.md"
        },
        "api": {
            "role": "data_validator",
            "objective": f"Monitor API calls on {url}. Intercept requests, check response codes, validate payloads, verify headers.",
            "memory_node": f"Runs/API_Test_{timestamp}.md"
        },
        "accessibility": {
            "role": "ui_explorer",
            "objective": f"Accessibility audit of {url}. Test keyboard navigation, check ARIA labels, verify alt text, check color contrast.",
            "memory_node": f"Runs/Accessibility_Test_{timestamp}.md"
        },
        "responsive": {
            "role": "ui_explorer",
            "objective": f"Test responsive design of {url} on desktop (1920x1080), tablet (768x1024), and mobile (375x667).",
            "memory_node": f"Runs/Responsive_Test_{timestamp}.md"
        },
        "full": {
            "role": "ui_explorer",
            "objective": f"Comprehensive test of {url}. Homepage, navigation, forms, responsive design, and basic accessibility checks.",
            "memory_node": f"Runs/Full_Test_{timestamp}.md"
        }
    }
    
    if test_type not in test_configs:
        return JSONResponse(
            status_code=400,
            content={"error": f"Unknown test type: {test_type}. Available: {list(test_configs.keys())}"}
        )
    
    config = test_configs[test_type]
    
    try:
        result = execute_tool("spawn_agent", {
            "role": config["role"],
            "objective": config["objective"],
            "memory_node": config["memory_node"]
        })
        
        if result["status"] == "success":
            return {
                "status": "success",
                "message": f"Test '{test_type}' initiated for {url}",
                "agent_id": result["result"]["agent_id"],
                "memory_node": config["memory_node"],
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
        else:
            return JSONResponse(
                status_code=500,
                content={"error": result.get("error", "Failed to spawn agent")}
            )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )


@app.get("/api/tests/types")
async def get_test_types():
    """Get available test types."""
    return {
        "types": [
            {"id": "homepage", "name": "Homepage", "description": "Test homepage structure and content"},
            {"id": "navigation", "name": "Navigation", "description": "Test all navigation links and page transitions"},
            {"id": "contact", "name": "Contact Form", "description": "Test contact form functionality"},
            {"id": "api", "name": "API Monitoring", "description": "Monitor backend API calls"},
            {"id": "accessibility", "name": "Accessibility", "description": "WCAG compliance audit"},
            {"id": "responsive", "name": "Responsive Design", "description": "Test on multiple viewports"},
            {"id": "full", "name": "Full Suite", "description": "Comprehensive test coverage"}
        ]
    }


@app.get("/api/sse/stream")
async def sse_stream(request: Request):
    """Server-Sent Events endpoint for live dashboard updates."""
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


@app.get("/api/sse/agents")
async def agents_sse(request: Request):
    """SSE endpoint specifically for agent updates."""
    async def agent_events():
        while True:
            agents = reader.get_active_agents()
            data = {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "agents": agents,
                "count": len(agents)
            }
            yield f"data: {json.dumps(data, default=json_serialize)}\n\n"
            await asyncio.sleep(3)
    
    return StreamingResponse(
        agent_events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


@app.get("/api/sse/orchestrator")
async def orchestrator_sse(request: Request):
    """SSE endpoint specifically for orchestrator feed updates."""
    async def orchestrator_events():
        while True:
            status = reader.get_orchestrator_status()
            data = {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "status": status
            }
            yield f"data: {json.dumps(data, default=json_serialize)}\n\n"
            await asyncio.sleep(2)
    
    return StreamingResponse(
        orchestrator_events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3000)
