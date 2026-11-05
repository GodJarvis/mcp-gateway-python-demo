from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from mcp.server.transport_security import TransportSecuritySettings
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.api.routes import router
from app.config import get_settings
from app.database import init_database
from app.mcp_gateway import mcp_server
from app.security import is_valid_mcp_authorization


settings = get_settings()

transport_security = TransportSecuritySettings(
    allowed_hosts=settings.mcp_allowed_hosts,
    allowed_origins=settings.mcp_allowed_origins,
)
mcp_http_app = mcp_server.streamable_http_app(
    streamable_http_path="/mcp",
    json_response=True,
    stateless_http=True,
    transport_security=transport_security,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    del app
    init_database()
    async with mcp_server.session_manager.run():
        yield


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
)


class McpAuthenticationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path.rstrip("/") == "/mcp" and request.method != "OPTIONS":
            if not is_valid_mcp_authorization(request.headers.get("authorization")):
                return JSONResponse(
                    status_code=401,
                    content={"detail": "MCP 客户端认证失败"},
                    headers={"WWW-Authenticate": "Bearer"},
                )
        return await call_next(request)


app.add_middleware(McpAuthenticationMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(set(settings.frontend_origins + settings.mcp_allowed_origins)),
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "Last-Event-ID",
        "Mcp-Method",
        "Mcp-Name",
        "Mcp-Protocol-Version",
        "Mcp-Session-Id",
    ],
    expose_headers=["Mcp-Session-Id"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name}


app.include_router(router)

# 管理 API 路由必须先注册，根挂载的 MCP ASGI 应用放在最后。
app.mount("/", mcp_http_app)

