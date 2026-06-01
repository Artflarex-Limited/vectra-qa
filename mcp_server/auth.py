"""
RBAC authentication middleware for Vectra QA MCP Server.
API key auth via X-API-Key header.
"""

import os
from typing import Optional, Set, Dict
from enum import Enum

from fastapi import Request, HTTPException, status
from fastapi.security import APIKeyHeader
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

# API key configuration
API_KEY_NAME = "X-API-Key"
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "vectra-qa-admin-key-change-me")
TESTER_API_KEY = os.getenv("TESTER_API_KEY", "vectra-qa-tester-key")
VIEWER_API_KEY = os.getenv("VIEWER_API_KEY", "vectra-qa-viewer-key")

# Role -> API key mapping
ROLE_KEYS = {
    "admin": ADMIN_API_KEY,
    "tester": TESTER_API_KEY,
    "viewer": VIEWER_API_KEY,
}

# API key -> role mapping
KEY_ROLES = {v: k for k, v in ROLE_KEYS.items()}

# Public paths (no auth required)
PUBLIC_PATHS = {
    "/health",
    "/ready",
    "/metrics",
    "/docs",
    "/openapi.json",
    "/",
}


class Role(Enum):
    ADMIN = "admin"
    TESTER = "tester"
    VIEWER = "viewer"


def get_role_from_key(api_key: str) -> Optional[str]:
    """Get role from API key."""
    return KEY_ROLES.get(api_key)


def has_permission(role: str, method: str, path: str) -> bool:
    """Check if role has permission for method/path."""
    if role == "admin":
        return True
    
    # All roles can read
    if method == "GET":
        return True
    
    # Tester can POST (run tests, spawn agents)
    if role == "tester" and method == "POST":
        return True
    
    # Viewer has no write permissions
    return False


class AuthMiddleware(BaseHTTPMiddleware):
    """Middleware that checks API key on all non-public endpoints."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        
        # Skip auth for public paths
        if path in PUBLIC_PATHS or path.startswith("/docs") or path.startswith("/openapi"):
            return await call_next(request)
        
        # Check for API key
        api_key = request.headers.get(API_KEY_NAME)
        
        if not api_key:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"error": "Unauthorized", "detail": f"Missing {API_KEY_NAME} header"}
            )
        
        role = get_role_from_key(api_key)
        if not role:
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"error": "Forbidden", "detail": "Invalid API key"}
            )
        
        # Check permission
        if not has_permission(role, request.method, path):
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"error": "Forbidden", "detail": f"Role '{role}' cannot perform '{request.method}' on '{path}'"}
            )
        
        # Attach role to request state
        request.state.role = role
        request.state.api_key = api_key
        
        return await call_next(request)


def require_role(required_role: str):
    """Dependency for requiring specific role."""
    async def check_role(request: Request):
        if not hasattr(request.state, "role"):
            raise HTTPException(status_code=401, detail="Not authenticated")
        if request.state.role != required_role and request.state.role != "admin":
            raise HTTPException(status_code=403, detail=f"Requires '{required_role}' role")
        return request.state.role
    return check_role


# Role-based access matrix
ACCESS_MATRIX = {
    "/mcp": {"GET": ["viewer", "tester", "admin"], "POST": ["tester", "admin"]},
    "/mcp/tools": {"GET": ["viewer", "tester", "admin"]},
    "/mcp/sse": {"GET": ["tester", "admin"]},
    "/agents/list": {"GET": ["viewer", "tester", "admin"]},
    "/vault/nodes": {"GET": ["viewer", "tester", "admin"]},
}
