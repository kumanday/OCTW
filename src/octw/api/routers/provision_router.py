"""One-click tenant provisioning endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from octw.api.auth import TokenPayload, get_current_user
from octw.api.deps import get_orchestrator, get_tenant_service, get_vault_service
from octw.common.config import settings
from octw.common.logging import get_logger
from octw.db.engine import get_session
from octw.db.tables import TenantRow
from octw.models.provider import PROVIDERS, get_provider
from octw.models.tenant import TenantCreate, TenantPlan
from octw.orchestrator.docker_orch import DockerOrchestrator
from octw.orchestrator.tenant_service import TenantService
from octw.vault.service import VaultService

log = get_logger(__name__)

router = APIRouter(prefix="/provision", tags=["provision"])


class ProvisionRequest(BaseModel):
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9\-]{1,48}[a-z0-9]$")
    name: str = Field(min_length=1, max_length=200)
    provider: str = Field(
        default="zai",
        description="Provider key: zai, moonshot, or minimax",
    )
    secrets: dict[str, str] | None = None


class ProvisionResponse(BaseModel):
    tenant_id: str
    slug: str
    status: str
    provider: str
    model: str
    url: str


@router.get("/providers")
async def list_providers():
    """List available providers and their models."""
    return [
        {
            "key": spec.key.value,
            "display_name": spec.display_name,
            "model": spec.model_id,
            "configured": settings.get_provider_api_key(spec.env_var) is not None,
        }
        for spec in PROVIDERS.values()
    ]


@router.post("", response_model=ProvisionResponse)
async def provision_tenant(
    req: ProvisionRequest,
    user: TokenPayload = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    svc: TenantService = Depends(get_tenant_service),
    orch: DockerOrchestrator = Depends(get_orchestrator),
    vault_svc: VaultService = Depends(get_vault_service),
):
    """
    One-click tenant provisioning:
    1. Validate provider and check API key is configured
    2. Create tenant metadata and resources
    3. Store any provided secrets
    4. Run OpenClaw onboarding init job
    5. Configure webchat + model provider
    6. Start the tenant container
    7. Return the access URL
    """
    # 0. Validate provider
    try:
        provider_spec = get_provider(req.provider)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    api_key = settings.get_provider_api_key(provider_spec.env_var)
    if not api_key:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Provider '{provider_spec.display_name}' is not configured. "
                f"Set OCTW_{provider_spec.env_var} on the server."
            ),
        )

    existing = await svc.get_tenant_by_slug(session, req.slug)
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Tenant with slug '{req.slug}' already exists",
        )

    # 1. Create tenant
    tenant_req = TenantCreate(
        slug=req.slug,
        name=req.name,
        plan=TenantPlan.STANDARD,
        trusted_proxy_auth=True,
    )
    tenant = await svc.create_tenant(session, tenant_req, creator_user_id=user.user_id)
    await session.flush()

    # Store the provider choice on the tenant row
    await session.execute(
        update(TenantRow)
        .where(TenantRow.tenant_id == tenant.tenant_id)
        .values(provider=provider_spec.key.value)
    )
    await session.flush()

    # 2. Store per-tenant secrets (if any beyond the shared provider key)
    if req.secrets:
        for secret_name, secret_value in req.secrets.items():
            await vault_svc.store_secret(
                session, tenant.tenant_id, secret_name, secret_value,
                target_env_var=secret_name,
            )
        await session.flush()

    # 3. Run OpenClaw onboarding init job
    try:
        env_secrets = await vault_svc.get_decrypted_secrets(session, tenant.tenant_id)
        orch.run_init_job(
            tenant,
            provider_env_var=provider_spec.env_var,
            provider_model=provider_spec.model_id,
            env_secrets=env_secrets,
        )
    except RuntimeError as e:
        log.error(
            "provision_init_failed",
            tenant_id=str(tenant.tenant_id),
            error=str(e),
        )
        raise HTTPException(status_code=500, detail=f"Onboarding failed: {e}") from e

    # 4. Configure webchat + model provider in openclaw.json
    orch.configure_tenant(
        tenant.tenant_id,
        provider_env_var=provider_spec.env_var,
        provider_model=provider_spec.model_id,
    )

    # 5. Start the tenant container
    await svc.start_tenant(session, tenant.tenant_id)
    await session.commit()

    # 6. Build access URL
    base_url = settings.edge_domain.rstrip("/")
    url = f"https://{base_url}/{req.slug}/"

    log.info(
        "tenant_provisioned",
        tenant_id=str(tenant.tenant_id),
        slug=req.slug,
        provider=provider_spec.key.value,
        model=provider_spec.model_id,
        url=url,
    )

    return ProvisionResponse(
        tenant_id=str(tenant.tenant_id),
        slug=req.slug,
        status="running",
        provider=provider_spec.key.value,
        model=provider_spec.model_id,
        url=url,
    )
