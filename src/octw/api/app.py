from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from prometheus_client import make_asgi_app

from octw.api.routers import (
    app_router,
    auth_router,
    internal_router,
    provision_router,
    runtime_router,
    secrets_router,
    tenants_router,
)
from octw.db.engine import engine, ensure_schema

WEB_ROOT = Path(__file__).resolve().parent.parent / "web" / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    await ensure_schema(engine)
    yield
    await engine.dispose()


app = FastAPI(title="OCTW API", version="0.1.0", lifespan=lifespan)

app.include_router(auth_router.router, prefix="/api/v1")
app.include_router(tenants_router.router, prefix="/api/v1")
app.include_router(secrets_router.router, prefix="/api/v1")
app.include_router(runtime_router.router, prefix="/api/v1")
app.include_router(provision_router.router, prefix="/api/v1")
app.include_router(app_router.router)
app.include_router(internal_router.router)

app.mount("/app/static", StaticFiles(directory=WEB_ROOT), name="app-static")

metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)


@app.get("/app")
@app.get("/app/")
@app.get("/app/chat")
async def app_shell():
    return FileResponse(WEB_ROOT / "index.html")


@app.get("/health")
async def health():
    return {"status": "ok"}
