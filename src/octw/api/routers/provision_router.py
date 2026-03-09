"""One-click tenant provisioning endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from octw.api.app_logic import provision_tenant as provision_tenant_impl
from octw.api.auth import TokenPayload, get_current_user
from octw.api.deps import get_orchestrator, get_tenant_service, get_vault_service
from octw.common.config import settings
from octw.common.logging import get_logger
from octw.db.engine import get_session
from octw.models.provider import PROVIDERS, get_provider
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
    verification_status: str
    verification_error: str | None = None


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
        get_provider(req.provider)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    provider_spec = get_provider(req.provider)
    api_key = settings.get_provider_api_key(provider_spec.env_var)
    if not api_key:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Provider '{provider_spec.display_name}' is not configured. "
                f"Set OCTW_{provider_spec.env_var} on the server."
            ),
        )

    try:
        provisioned = await provision_tenant_impl(
            session=session,
            svc=svc,
            orch=orch,
            vault_svc=vault_svc,
            user=user,
            slug=req.slug,
            name=req.name,
            provider_key=req.provider,
            secrets=req.secrets,
        )
    except RuntimeError as e:
        log.error(
            "provision_init_failed",
            slug=req.slug,
            error=str(e),
        )
        raise HTTPException(status_code=500, detail=f"Onboarding failed: {e}") from e

    log.info(
        "tenant_provisioned",
        tenant_id=provisioned.tenant_id,
        slug=provisioned.slug,
        provider=provisioned.provider,
        model=provisioned.model,
        url=provisioned.url,
    )

    return ProvisionResponse(
        tenant_id=provisioned.tenant_id,
        slug=provisioned.slug,
        status=provisioned.status,
        provider=provisioned.provider,
        model=provisioned.model,
        url=provisioned.url,
        verification_status=provisioned.verification_status,
        verification_error=provisioned.verification_error,
    )
