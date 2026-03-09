from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from octw.api.app_logic import (
    build_user_tenant_name,
    build_user_tenant_slug,
    provision_tenant,
    tenant_chat_url,
)
from octw.api.auth import create_access_token, get_browser_user, set_session_cookie
from octw.api.deps import get_orchestrator, get_tenant_service, get_vault_service
from octw.common.config import settings
from octw.db.engine import get_session
from octw.models.tenant import VerificationStatus
from octw.orchestrator.docker_orch import DockerOrchestrator
from octw.orchestrator.tenant_service import TenantService
from octw.vault.service import VaultService

router = APIRouter(prefix="/api/v1/app", tags=["app"])


class AppTenantInfo(BaseModel):
    tenant_id: str
    slug: str
    status: str
    verification_status: str
    verification_error: str | None = None
    chat_url: str


class AppSessionResponse(BaseModel):
    user_id: str
    email: str
    tenant: AppTenantInfo | None = None


class DeployOrResumeResponse(BaseModel):
    created: bool
    tenant: AppTenantInfo


async def _browser_auth(
    request: Request,
    response: Response,
    session: AsyncSession,
):
    user, issued = await get_browser_user(request, session)
    if issued:
        await session.commit()
        set_session_cookie(response, create_access_token(user.user_id, user.email))
    return user


async def _tenant_info(session: AsyncSession, svc: TenantService, user_id):
    tenant = await svc.get_owner_tenant(session, user_id)
    if not tenant:
        return None
    return AppTenantInfo(
        tenant_id=str(tenant.tenant_id),
        slug=tenant.slug,
        status=tenant.status.value,
        verification_status=tenant.verification_status.value,
        verification_error=tenant.verification_error,
        chat_url=tenant_chat_url(tenant.slug),
    )


@router.get("/session", response_model=AppSessionResponse)
async def get_app_session(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
    svc: TenantService = Depends(get_tenant_service),
):
    user = await _browser_auth(request, response, session)
    tenant = await _tenant_info(session, svc, user.user_id)
    return AppSessionResponse(user_id=str(user.user_id), email=user.email, tenant=tenant)


@router.post("/deploy-or-resume", response_model=DeployOrResumeResponse)
async def deploy_or_resume(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
    svc: TenantService = Depends(get_tenant_service),
    orch: DockerOrchestrator = Depends(get_orchestrator),
    vault_svc: VaultService = Depends(get_vault_service),
):
    user = await _browser_auth(request, response, session)
    tenant = await svc.get_owner_tenant(session, user.user_id)
    created = False

    if tenant is None:
        try:
            provisioned = await provision_tenant(
                session=session,
                svc=svc,
                orch=orch,
                vault_svc=vault_svc,
                user=user,
                slug=build_user_tenant_slug(user.user_id),
                name=build_user_tenant_name(user.email),
                provider_key=settings.default_provider,
            )
        except Exception as exc:
            await session.rollback()
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        created = True
        tenant_info = AppTenantInfo(
            tenant_id=provisioned.tenant_id,
            slug=provisioned.slug,
            status=provisioned.status,
            verification_status=provisioned.verification_status,
            verification_error=provisioned.verification_error,
            chat_url=tenant_chat_url(provisioned.slug),
        )
        return DeployOrResumeResponse(created=created, tenant=tenant_info)

    try:
        await svc.wake_tenant(session, tenant.tenant_id)
        if tenant.verification_status != VerificationStatus.VERIFIED:
            await svc.verify_tenant(session, tenant.tenant_id)
        await session.commit()
    except Exception as exc:
        await session.rollback()
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    refreshed = await svc.get_tenant(session, tenant.tenant_id)
    if not refreshed:
        raise HTTPException(status_code=404, detail="Tenant disappeared")
    tenant_info = AppTenantInfo(
        tenant_id=str(refreshed.tenant_id),
        slug=refreshed.slug,
        status=refreshed.status.value,
        verification_status=refreshed.verification_status.value,
        verification_error=refreshed.verification_error,
        chat_url=tenant_chat_url(refreshed.slug),
    )
    return DeployOrResumeResponse(created=created, tenant=tenant_info)
