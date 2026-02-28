from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from prometheus_client import make_asgi_app

from octw.api.routers import (
    auth_router,
    internal_router,
    provision_router,
    runtime_router,
    secrets_router,
    tenants_router,
)
from octw.db.engine import engine
from octw.db.tables import Base


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


app = FastAPI(title="OCTW API", version="0.1.0", lifespan=lifespan)

app.include_router(auth_router.router, prefix="/api/v1")
app.include_router(tenants_router.router, prefix="/api/v1")
app.include_router(secrets_router.router, prefix="/api/v1")
app.include_router(runtime_router.router, prefix="/api/v1")
app.include_router(provision_router.router, prefix="/api/v1")
app.include_router(internal_router.router)

metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)


@app.get("/health")
async def health():
    return {"status": "ok"}
