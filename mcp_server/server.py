"""
MCP Server Implementation for Obsidian-backed Multi-Agent Testing Framework
Supports stdio and SSE transports for MCP protocol communication.
Includes health checks, state persistence, and graceful shutdown.
"""

import json
import sys
import asyncio
import argparse
from datetime import datetime, timezone
from typing import Any, Dict

import structlog

from mcp_server.tools import execute_tool, get_vault, get_spawner
from mcp_server.state_manager import get_state_manager

logger = structlog.get_logger()


class MCPServer:
    """Model Context Protocol Server for agent tool execution."""

    def __init__(self, transport: str = "stdio"):
        self.transport = transport
        self.request_id = 0
        self.state_manager = get_state_manager()

    async def handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Handle incoming MCP request."""
        method = request.get("method")
        params = request.get("params", {})
        req_id = request.get("id", 0)

        if method == "tools/list":
            from mcp_server.tools import TOOLS

            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "tools": [
                        {
                            "name": name,
                            "description": spec["description"],
                            "parameters": spec["parameters"],
                        }
                        for name, spec in TOOLS.items()
                    ]
                },
            }

        elif method == "tools/call":
            tool_name = params.get("name")
            tool_params = params.get("arguments", {})
            result = execute_tool(tool_name, tool_params)
            return {"jsonrpc": "2.0", "id": req_id, "result": result}

        elif method == "agents/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"agents": get_spawner().get_active_agents()},
            }

        elif method == "vault/nodes":
            directory = params.get("directory", ".")
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"nodes": get_vault().list_nodes(directory)},
            }

        else:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"},
            }

    async def run_stdio(self):
        """Run MCP server over stdio transport."""
        # Register signal handlers
        self.state_manager.register_signal_handlers()

        # Restore state from previous session
        orphaned = self.state_manager.restore_state()
        if orphaned:
            logger.info("orphaned_agents_detected", count=len(orphaned))

        while True:
            try:
                line = await asyncio.get_event_loop().run_in_executor(None, sys.stdin.readline)
                if not line:
                    break

                request = json.loads(line.strip())
                response = await self.handle_request(request)

                print(json.dumps(response), flush=True)

            except json.JSONDecodeError:
                continue
            except Exception as e:
                error_response = {
                    "jsonrpc": "2.0",
                    "id": 0,
                    "error": {"code": -32700, "message": str(e)},
                }
                print(json.dumps(error_response), flush=True)

    def run_sse(self, host: str = "0.0.0.0", port: int = 8080):
        """Run MCP server with SSE transport using FastAPI.

        Note: This is a regular (non-async) method because uvicorn.run()
        creates and manages its own event loop. Wrapping it in asyncio.run()
        would create a nested event loop, which causes RuntimeError.
        """
        from fastapi import FastAPI, Request
        from fastapi.responses import StreamingResponse, JSONResponse
        import uvicorn

        app = FastAPI(title="Vectra QA MCP Server")

        # Register signal handlers
        self.state_manager.register_signal_handlers()

        # Restore state on startup
        orphaned = self.state_manager.restore_state()
        if orphaned:
            logger.info("orphaned_agents_detected", count=len(orphaned))

        @app.on_event("startup")
        async def startup_event():
            logger.info("mcp_server_starting", host=host, port=port)

        @app.on_event("shutdown")
        async def shutdown_event():
            logger.info("mcp_server_shutting_down")
            self.state_manager.save_state()

        @app.get("/health")
        async def health_check():
            """Basic health check endpoint."""
            return {
                "status": "healthy",
                "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z",
                "service": "vectra-qa-mcp",
            }

        @app.get("/ready")
        async def readiness_check():
            """Readiness check - verifies vault is writable."""
            try:
                # Test vault write
                get_vault().write_node(".health_check", "ok")
                get_vault().read_node(".health_check")

                return {
                    "status": "ready",
                    "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z",
                    "vault": "writable",
                    "service": "vectra-qa-mcp",
                }
            except Exception as e:
                logger.error("readiness_check_failed", error=str(e))
                return JSONResponse(
                    status_code=503,
                    content={"status": "not_ready", "error": str(e), "service": "vectra-qa-mcp"},
                )

        @app.get("/metrics")
        async def metrics():
            """Prometheus-compatible metrics endpoint."""
            agents = get_spawner().get_active_agents()
            running = sum(1 for a in agents if a["status"] == "running")
            exited = sum(1 for a in agents if a["status"] == "exited")

            # Get orphaned agents
            orphaned = self.state_manager.check_orphaned_agents()

            return {
                "active_agents_total": len(agents),
                "active_agents_running": running,
                "active_agents_exited": exited,
                "orphaned_agents": len(orphaned),
                "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z",
            }

        @app.post("/mcp")
        async def handle_mcp(request: Request):
            body = await request.json()
            response = await self.handle_request(body)
            return response

        @app.get("/mcp/sse")
        async def sse_endpoint():
            async def event_stream():
                while True:
                    # Send periodic updates about active agents
                    agents = get_spawner().get_active_agents()
                    data = json.dumps({"type": "agent_update", "agents": agents})
                    yield f"data: {data}\n\n"
                    await asyncio.sleep(2)

            return StreamingResponse(event_stream(), media_type="text/event-stream")

        @app.get("/mcp/tools")
        async def list_tools():
            from mcp_server.tools import TOOLS

            return {
                "tools": [
                    {
                        "name": name,
                        "description": spec["description"],
                        "parameters": spec["parameters"],
                    }
                    for name, spec in TOOLS.items()
                ]
            }

        uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Vectra QA MCP Server")
    parser.add_argument("--transport", choices=["stdio", "sse"], default="stdio")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()

    server = MCPServer(transport=args.transport)

    if args.transport == "stdio":
        asyncio.run(server.run_stdio())
    else:
        server.run_sse(args.host, args.port)
