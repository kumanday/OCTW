from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from octw.api.auth import TokenPayload, get_current_user
from octw.api.deps import get_tenant_service, get_vault_service
from octw.api.routers.tenants_router import _require_member
from octw.db.engine import get_session
from octw.models.secret import SecretCreate
from octw.models.tenant import Role
from octw.orchestrator.tenant_service import TenantService
from octw.vault.service import VaultService

router = APIRouter(prefix="/tenants/{tenant_id}/secrets", tags=["secrets"])


@router.get("")
async def list_secrets(
    tenant_id: uuid.UUID,
    user: TokenPayload = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    svc: TenantService = Depends(get_tenant_service),
    vault_svc: VaultService = Depends(get_vault_service),
):
    await _require_member(tenant_id, user, session, svc)
    metadata = await vault_svc.list_secret_metadata(session, tenant_id)
    return [m.model_dump(mode="json") for m in metadata]


@router.put("/{name}")
async def set_secret(
    tenant_id: uuid.UUID,
    name: str,
    req: SecretCreate,
    user: TokenPayload = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    svc: TenantService = Depends(get_tenant_service),
    vault_svc: VaultService = Depends(get_vault_service),
):
    await _require_member(tenant_id, user, session, svc, min_role=Role.TENANT_ADMIN)
    meta = await vault_svc.store_secret(
        session, tenant_id, name, req.value,
        secret_type=req.type,
        target_env_var=req.target_env_var,
    )
    await session.commit()
    return meta.model_dump(mode="json")


@router.delete("/{name}", status_code=204)
async def delete_secret(
    tenant_id: uuid.UUID,
    name: str,
    user: TokenPayload = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    svc: TenantService = Depends(get_tenant_service),
    vault_svc: VaultService = Depends(get_vault_service),
):
    await _require_member(tenant_id, user, session, svc, min_role=Role.TENANT_ADMIN)
    deleted = await vault_svc.delete_secret(session, tenant_id, name)
    if not deleted:
        raise HTTPException(status_code=404, detail="Secret not found")
    await session.commit()
    return None


@router.post("/rotate")
async def rotate_secret(
    tenant_id: uuid.UUID,
    body: dict,
    user: TokenPayload = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    svc: TenantService = Depends(get_tenant_service),
    vault_svc: VaultService = Depends(get_vault_service),
):
    await _require_member(tenant_id, user, session, svc, min_role=Role.TENANT_ADMIN)
    name = body.get("name")
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    # Rotation just re-encrypts with current DEK; caller must provide new value
    new_value = body.get("value")
    if not new_value:
        raise HTTPException(status_code=400, detail="value is required for rotation")
    await vault_svc.store_secret(session, tenant_id, name, new_value)
    await session.commit()
    return {"status": "rotated", "name": name}
