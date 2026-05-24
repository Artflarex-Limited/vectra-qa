"""
MCP Server Implementation for Obsidian-backed Multi-Agent Testing Framework
Supports stdio and SSE transports for MCP protocol communication.
"""

import json
import sys
import asyncio
import argparse
from typing import Any, Dict
from mcp_server.tools import execute_tool, vault, spawner


class MCPServer:
    """Model Context Protocol Server for agent tool execution."""
    
    def __init__(self, transport: str = "stdio"):
        self.transport = transport
        self.request_id = 0
        
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
                            "parameters": spec["parameters"]
                        }
                        for name, spec in TOOLS.items()
                    ]
                }
            }
        
        elif method == "tools/call":
            tool_name = params.get("name")
            tool_params = params.get("arguments", {})
            result = execute_tool(tool_name, tool_params)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": result
            }
        
        elif method == "agents/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "agents": spawner.get_active_agents()
                }
            }
        
        elif method == "vault/nodes":
            directory = params.get("directory", ".")
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "nodes": vault.list_nodes(directory)
                }
            }
        
        else:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {
                    "code": -32601,
                    "message": f"Method not found: {method}"
                }
            }
    
    async def run_stdio(self):
        """Run MCP server over stdio transport."""
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
                    "error": {"code": -32700, "message": str(e)}
                }
                print(json.dumps(error_response), flush=True)
    
    def run_sse(self, host: str = "0.0.0.0", port: int = 8080):
        """Run MCP server with SSE transport using FastAPI.
        
        Note: This is a regular (non-async) method because uvicorn.run()
        creates and manages its own event loop. Wrapping it in asyncio.run()
        would create a nested event loop, which causes RuntimeError.
        """
        from fastapi import FastAPI, Request
        from fastapi.responses import StreamingResponse
        import uvicorn
        
        app = FastAPI(title="Obsidian MCP Server")
        
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
                    agents = spawner.get_active_agents()
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
                        "parameters": spec["parameters"]
                    }
                    for name, spec in TOOLS.items()
                ]
            }
        
        @app.get("/debug/file-check")
        async def debug_file_check():
            import os
            import subprocess
            path = "/app/agents/ui_explorer/worker.py"
            result = {
                "path": path,
                "exists": os.path.exists(path),
                "isfile": os.path.isfile(path),
                "readable": os.access(path, os.R_OK),
                "cwd": os.getcwd(),
                "ls": subprocess.run(["ls", "-la", path], capture_output=True, text=True).stdout.strip().split("\n") if os.path.exists(path) else []
            }
            if os.path.exists(path):
                try:
                    with open(path, 'r') as f:
                        result["first_line"] = f.readline().strip()
                except Exception as e:
                    result["read_error"] = str(e)
            return result
        
        uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Obsidian MCP Server")
    parser.add_argument("--transport", choices=["stdio", "sse"], default="stdio")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    
    server = MCPServer(transport=args.transport)
    
    if args.transport == "stdio":
        asyncio.run(server.run_stdio())
    else:
        server.run_sse(args.host, args.port)
