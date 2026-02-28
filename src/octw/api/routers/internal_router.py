"""Internal orchestrator API endpoints (mTLS only in production)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from octw.api.deps import get_orchestrator, get_tenant_service
from octw.db.engine import get_session
from octw.orchestrator.docker_orch import DockerOrchestrator
from octw.orchestrator.tenant_service import TenantService

router = APIRouter(prefix="/internal/v1/tenants", tags=["internal"])


@router.post("/{tenant_id}/ensure-running")
async def ensure_running(
    tenant_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    svc: TenantService = Depends(get_tenant_service),
):
    container_id = await svc.wake_tenant(session, tenant_id)
    await session.commit()
    return {"status": "running", "containerId": container_id}


@router.post("/{tenant_id}/pause-if-idle")
async def pause_if_idle(
    tenant_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    svc: TenantService = Depends(get_tenant_service),
):
    await svc.pause_tenant(session, tenant_id)
    await session.commit()
    return {"status": "paused"}


@router.post("/{tenant_id}/stop-if-idle")
async def stop_if_idle(
    tenant_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    svc: TenantService = Depends(get_tenant_service),
):
    await svc.stop_tenant(session, tenant_id)
    await session.commit()
    return {"status": "stopped"}


@router.get("/{tenant_id}/status")
async def get_status(
    tenant_id: uuid.UUID,
    orch: DockerOrchestrator = Depends(get_orchestrator),
):
    state = orch.get_container_state(tenant_id)
    ip = orch.get_container_ip(tenant_id)
    return {"state": state.value, "ip": ip}
