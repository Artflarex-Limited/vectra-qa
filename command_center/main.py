"""
Command Center Backend - FastAPI + HTMX + SSE
Dark Mode Dashboard for Obsidian-backed Multi-Agent Testing
"""

import json
import asyncio
from datetime import datetime
from typing import AsyncGenerator
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from obsidian_reader import reader

app = FastAPI(title="Vectra QA Command Center")

# CORS for HTMX
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Serve the main dashboard HTML."""
    with open("static/index.html", "r") as f:
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
        
        yield f"data: {json.dumps(data)}\n\n"
        await asyncio.sleep(2)


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
            yield f"data: {json.dumps(data)}\n\n"
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
            yield f"data: {json.dumps(data)}\n\n"
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
