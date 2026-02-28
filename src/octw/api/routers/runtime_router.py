from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from octw.api.auth import TokenPayload, get_current_user
from octw.api.deps import get_orchestrator, get_tenant_service
from octw.api.routers.tenants_router import _require_member
from octw.db.engine import get_session
from octw.models.tenant import Role
from octw.orchestrator.docker_orch import DockerOrchestrator
from octw.orchestrator.tenant_service import TenantService

router = APIRouter(prefix="/tenants/{tenant_id}/runtime", tags=["runtime"])


@router.get("")
async def get_runtime(
    tenant_id: uuid.UUID,
    user: TokenPayload = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    svc: TenantService = Depends(get_tenant_service),
):
    await _require_member(tenant_id, user, session, svc)
    info = await svc.get_runtime_info(session, tenant_id)
    return info.model_dump(mode="json")


@router.post("/start")
async def start_runtime(
    tenant_id: uuid.UUID,
    user: TokenPayload = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    svc: TenantService = Depends(get_tenant_service),
):
    await _require_member(tenant_id, user, session, svc, min_role=Role.TENANT_USER)
    container_id = await svc.start_tenant(session, tenant_id)
    await session.commit()
    return {"status": "started", "containerId": container_id}


@router.post("/stop")
async def stop_runtime(
    tenant_id: uuid.UUID,
    user: TokenPayload = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    svc: TenantService = Depends(get_tenant_service),
):
    await _require_member(tenant_id, user, session, svc, min_role=Role.TENANT_USER)
    await svc.stop_tenant(session, tenant_id)
    await session.commit()
    return {"status": "stopped"}


@router.post("/pause")
async def pause_runtime(
    tenant_id: uuid.UUID,
    user: TokenPayload = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    svc: TenantService = Depends(get_tenant_service),
):
    await _require_member(tenant_id, user, session, svc, min_role=Role.TENANT_USER)
    await svc.pause_tenant(session, tenant_id)
    await session.commit()
    return {"status": "paused"}


@router.post("/wake")
async def wake_runtime(
    tenant_id: uuid.UUID,
    user: TokenPayload = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    svc: TenantService = Depends(get_tenant_service),
):
    await _require_member(tenant_id, user, session, svc, min_role=Role.TENANT_USER)
    container_id = await svc.wake_tenant(session, tenant_id)
    await session.commit()
    return {"status": "running", "containerId": container_id}


@router.get("/logs")
async def get_logs(
    tenant_id: uuid.UUID,
    since: int | None = Query(None),
    tail: int = Query(200, le=5000),
    user: TokenPayload = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    svc: TenantService = Depends(get_tenant_service),
    orch: DockerOrchestrator = Depends(get_orchestrator),
):
    await _require_member(tenant_id, user, session, svc)
    logs = orch.get_container_logs(tenant_id, since=since, tail=tail)
    return {"logs": logs}
