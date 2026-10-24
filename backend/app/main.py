from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
import hmac
from urllib.parse import urlsplit

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi import Request
from fastapi.responses import JSONResponse

from backend.app.api.catalog import router as catalog_router
from backend.app.api.admin import router as admin_router
from backend.app.api.auth import router as auth_router
from backend.app.api.conversations import router as conversations_router
from backend.app.api.data_admin import router as data_admin_router
from backend.app.api.health import router as health_router
from backend.app.api.messages import router as messages_router
from backend.app.api.reports import router as reports_router
from backend.app.api.teams import router as teams_router
from backend.app.core.config import ROOT, settings
from backend.app.core.database import init_db
from backend.app.core.runtime import (
    new_request_context,
    reset_request_context,
)
from backend.app.services.mcp.server import get_mcp_server


def create_app(*, init_database: bool = True) -> FastAPI:
    mcp_app = get_mcp_server().http_app(path="/", stateless_http=True)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if init_database:
            init_db()
        async with mcp_app.lifespan(mcp_app):
            yield

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def verify_browser_origin(request: Request, call_next):
        context, token = new_request_context(request)
        try:
            if settings.app_env == "production" and request.url.path.startswith("/mcp"):
                expected_mcp = settings.mcp_access_token.strip()
                supplied = request.headers.get("authorization", "")
                if not expected_mcp or not hmac.compare_digest(
                    supplied,
                    f"Bearer {expected_mcp}",
                ):
                    response = JSONResponse(
                        status_code=401,
                        content={"detail": "MCP 访问令牌无效"},
                    )
                else:
                    response = await call_next(request)
            elif (
                settings.app_env == "production"
                and request.url.path.startswith("/api/")
                and request.method not in {"GET", "HEAD", "OPTIONS"}
            ):
                origin = request.headers.get("origin", "").rstrip("/")
                expected = settings.allowed_origin.rstrip("/")
                request_host = request.headers.get("host", "")
                origin_host = urlsplit(origin).netloc if origin else ""
                same_host = bool(origin_host and origin_host == request_host)
                if not origin or (origin != expected and not same_host):
                    response = JSONResponse(
                        status_code=403,
                        content={"detail": "请求来源不受信任"},
                    )
                else:
                    response = await call_next(request)
            else:
                response = await call_next(request)
            response.headers["X-Request-ID"] = context.request_id
            return response
        finally:
            reset_request_context(token)
    app.include_router(conversations_router)
    app.include_router(data_admin_router)
    app.include_router(auth_router)
    app.include_router(admin_router)
    app.include_router(catalog_router)
    app.include_router(health_router)
    app.include_router(messages_router)
    app.include_router(reports_router)
    app.include_router(teams_router)

    app.mount("/mcp", mcp_app)

    frontend_dist = ROOT / "frontend" / "dist"
    assets_dir = frontend_dist / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/", include_in_schema=False)
    def index():
        index_file = frontend_dist / "index.html"
        if index_file.exists():
            return FileResponse(index_file)
        return {"message": "东煌纪竞品情报 ChatBI API", "docs": "/docs"}

    return app


app = create_app()
