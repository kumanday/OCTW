"""Internal orchestrator API endpoints (mTLS only in production)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from octw.api.deps import get_orchestrator, get_tenant_service
from octw.db.engine import get_session
from octw.orchestrator.docker_orch import DockerOrchestrator
from octw.orchestrator.tenant_service import TenantService

router = APIRouter(prefix="/internal/v1/tenants", tags=["internal"])


async def _resolve_tenant_id(
    identifier: str,
    session: AsyncSession,
    svc: TenantService,
) -> uuid.UUID:
    try:
        return uuid.UUID(identifier)
    except ValueError:
        pass
    tenant = await svc.get_tenant_by_slug(session, identifier)
    if not tenant:
        raise HTTPException(status_code=404, detail=f"Tenant '{identifier}' not found")
    return tenant.tenant_id


@router.post("/{identifier}/ensure-running")
async def ensure_running(
    identifier: str,
    session: AsyncSession = Depends(get_session),
    svc: TenantService = Depends(get_tenant_service),
):
    tenant_id = await _resolve_tenant_id(identifier, session, svc)
    container_id = await svc.wake_tenant(session, tenant_id)
    await session.commit()
    return {"status": "running", "containerId": container_id}


@router.get("/{identifier}/access/{user_id}")
async def check_access(
    identifier: str,
    user_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    svc: TenantService = Depends(get_tenant_service),
):
    tenant_id = await _resolve_tenant_id(identifier, session, svc)
    role = await svc.check_membership(session, tenant_id, user_id)
    if role is None:
        raise HTTPException(status_code=403, detail="Forbidden")
    return {"allowed": True, "role": role.value, "tenant_id": str(tenant_id)}


@router.post("/{identifier}/pause-if-idle")
async def pause_if_idle(
    identifier: str,
    session: AsyncSession = Depends(get_session),
    svc: TenantService = Depends(get_tenant_service),
):
    tenant_id = await _resolve_tenant_id(identifier, session, svc)
    await svc.pause_tenant(session, tenant_id)
    await session.commit()
    return {"status": "paused"}


@router.post("/{identifier}/stop-if-idle")
async def stop_if_idle(
    identifier: str,
    session: AsyncSession = Depends(get_session),
    svc: TenantService = Depends(get_tenant_service),
):
    tenant_id = await _resolve_tenant_id(identifier, session, svc)
    await svc.stop_tenant(session, tenant_id)
    await session.commit()
    return {"status": "stopped"}


@router.get("/{identifier}/status")
async def get_status(
    identifier: str,
    session: AsyncSession = Depends(get_session),
    svc: TenantService = Depends(get_tenant_service),
    orch: DockerOrchestrator = Depends(get_orchestrator),
):
    tenant_id = await _resolve_tenant_id(identifier, session, svc)
    state = orch.get_container_state(tenant_id)
    ip = orch.get_container_ip(tenant_id)
    return {"state": state.value, "ip": ip}
