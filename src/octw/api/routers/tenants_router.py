from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from octw.api.auth import TokenPayload, get_current_user
from octw.api.deps import get_tenant_service
from octw.db.engine import get_session
from octw.models.tenant import MemberCreate, Role, TenantCreate
from octw.orchestrator.tenant_service import TenantService

router = APIRouter(prefix="/tenants", tags=["tenants"])


async def _require_member(
    tenant_id: uuid.UUID,
    user: TokenPayload,
    session: AsyncSession,
    svc: TenantService,
    min_role: Role = Role.TENANT_VIEWER,
) -> Role:
    role = await svc.check_membership(session, tenant_id, user.user_id)
    if role is None:
        raise HTTPException(status_code=403, detail="Not a member of this tenant")
    role_order = {Role.TENANT_VIEWER: 0, Role.TENANT_USER: 1, Role.TENANT_ADMIN: 2}
    if role_order.get(role, 0) < role_order.get(min_role, 0):
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    return role


@router.post("", status_code=201)
async def create_tenant(
    req: TenantCreate,
    user: TokenPayload = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    svc: TenantService = Depends(get_tenant_service),
):
    tenant = await svc.create_tenant(session, req, creator_user_id=user.user_id)
    await session.commit()
    return {"tenantId": str(tenant.tenant_id), "slug": tenant.slug, "status": tenant.status.value}


@router.get("")
async def list_tenants(
    user: TokenPayload = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    svc: TenantService = Depends(get_tenant_service),
):
    tenants = await svc.list_tenants(session, user_id=user.user_id)
    return [
        {"tenantId": str(t.tenant_id), "slug": t.slug, "name": t.name, "status": t.status.value}
        for t in tenants
    ]


@router.get("/{tenant_id}")
async def get_tenant(
    tenant_id: uuid.UUID,
    user: TokenPayload = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    svc: TenantService = Depends(get_tenant_service),
):
    await _require_member(tenant_id, user, session, svc)
    tenant = await svc.get_tenant(session, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant.model_dump(mode="json")


@router.patch("/{tenant_id}")
async def update_tenant(
    tenant_id: uuid.UUID,
    body: dict,
    user: TokenPayload = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    svc: TenantService = Depends(get_tenant_service),
):
    await _require_member(tenant_id, user, session, svc, min_role=Role.TENANT_ADMIN)
    tenant = await svc.get_tenant(session, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    # Minimal patch support for name
    from sqlalchemy import update

    from octw.db.tables import TenantRow

    allowed = {"name"}
    updates = {k: v for k, v in body.items() if k in allowed}
    if updates:
        await session.execute(
            update(TenantRow).where(TenantRow.tenant_id == tenant_id).values(**updates)
        )
        await session.commit()
    return {"status": "updated"}


@router.delete("/{tenant_id}", status_code=204)
async def delete_tenant(
    tenant_id: uuid.UUID,
    user: TokenPayload = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    svc: TenantService = Depends(get_tenant_service),
):
    await _require_member(tenant_id, user, session, svc, min_role=Role.TENANT_ADMIN)
    await svc.delete_tenant(session, tenant_id, user_id=user.user_id)
    await session.commit()
    return None


# --- Members ---


@router.get("/{tenant_id}/members")
async def list_members(
    tenant_id: uuid.UUID,
    user: TokenPayload = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    svc: TenantService = Depends(get_tenant_service),
):
    await _require_member(tenant_id, user, session, svc)
    members = await svc.list_members(session, tenant_id)
    return [m.model_dump(mode="json") for m in members]


@router.post("/{tenant_id}/members", status_code=201)
async def add_member(
    tenant_id: uuid.UUID,
    req: MemberCreate,
    user: TokenPayload = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    svc: TenantService = Depends(get_tenant_service),
):
    await _require_member(tenant_id, user, session, svc, min_role=Role.TENANT_ADMIN)
    member = await svc.add_member(
        session, tenant_id, req.email, req.role, actor_user_id=user.user_id
    )
    await session.commit()
    return member.model_dump(mode="json")


@router.delete("/{tenant_id}/members/{user_id}", status_code=204)
async def remove_member(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    user: TokenPayload = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    svc: TenantService = Depends(get_tenant_service),
):
    await _require_member(tenant_id, user, session, svc, min_role=Role.TENANT_ADMIN)
    await svc.remove_member(session, tenant_id, user_id, actor_user_id=user.user_id)
    await session.commit()
    return None
