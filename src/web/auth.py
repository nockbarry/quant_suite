"""Bearer token authentication middleware."""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from src.web.config import web_config


class AuthMiddleware(BaseHTTPMiddleware):
    """Simple bearer token auth. Disabled when auth_token is empty."""

    async def dispatch(self, request: Request, call_next):
        # Skip auth if no token configured
        if not web_config.auth_token:
            return await call_next(request)

        # Skip auth for static files and health check
        if request.url.path.startswith("/static") or request.url.path == "/api/health":
            return await call_next(request)

        # Check Authorization header
        auth = request.headers.get("Authorization", "")
        if auth == f"Bearer {web_config.auth_token}":
            return await call_next(request)

        # Check HX-Auth header (for HTMX requests)
        hx_auth = request.headers.get("HX-Auth", "")
        if hx_auth == web_config.auth_token:
            return await call_next(request)

        # Check query param (for WebSocket)
        token = request.query_params.get("token", "")
        if token == web_config.auth_token:
            return await call_next(request)

        return JSONResponse(
            status_code=401,
            content={"detail": "Unauthorized"},
        )
