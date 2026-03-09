from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from octw.api.auth import TokenPayload
from octw.common.config import settings
from octw.common.logging import get_logger
from octw.db.tables import TenantRow
from octw.models.provider import get_provider
from octw.models.tenant import TenantCreate, TenantPlan
from octw.orchestrator.docker_orch import DockerOrchestrator
from octw.orchestrator.tenant_service import TenantService
from octw.vault.service import VaultService

log = get_logger(__name__)

_SLUG_SAFE = re.compile(r"[^a-z0-9]+")


@dataclass(slots=True)
class ProvisionedTenant:
    tenant_id: str
    slug: str
    status: str
    provider: str
    model: str
    url: str
    verification_status: str
    verification_error: str | None


def build_user_tenant_slug(user_id: uuid.UUID) -> str:
    return f"u-{user_id.hex[:20]}"


def build_user_tenant_name(email: str) -> str:
    local = email.split("@", 1)[0].strip().lower() or "user"
    safe = _SLUG_SAFE.sub(" ", local).strip()
    label = safe.title() if safe else "User"
    return f"{label} Workspace"


def tenant_chat_url(slug: str) -> str:
    return f"{settings.public_base_url.rstrip('/')}/app/chat"


async def provision_tenant(
    *,
    session: AsyncSession,
    svc: TenantService,
    orch: DockerOrchestrator,
    vault_svc: VaultService,
    user: TokenPayload,
    slug: str,
    name: str,
    provider_key: str,
    secrets: dict[str, str] | None = None,
) -> ProvisionedTenant:
    provider_spec = get_provider(provider_key)
    api_key = settings.get_provider_api_key(provider_spec.env_var)
    if not api_key:
        raise RuntimeError(
            "Provider "
            f"'{provider_spec.display_name}' is not configured. "
            f"Set OCTW_{provider_spec.env_var}."
        )

    existing = await svc.get_tenant_by_slug(session, slug)
    if existing:
        raise RuntimeError(f"Tenant with slug '{slug}' already exists")

    tenant_req = TenantCreate(
        slug=slug,
        name=name,
        plan=TenantPlan.STANDARD,
        trusted_proxy_auth=True,
    )
    tenant = await svc.create_tenant(session, tenant_req, creator_user_id=user.user_id)
    await session.flush()

    await session.execute(
        update(TenantRow)
        .where(TenantRow.tenant_id == tenant.tenant_id)
        .values(provider=provider_spec.key.value)
    )
    await session.flush()

    if secrets:
        for secret_name, secret_value in secrets.items():
            await vault_svc.store_secret(
                session, tenant.tenant_id, secret_name, secret_value,
                target_env_var=secret_name,
            )
        await session.flush()

    env_secrets = await vault_svc.get_decrypted_secrets(session, tenant.tenant_id)
    orch.run_init_job(
        tenant,
        provider_env_var=provider_spec.env_var,
        provider_model=provider_spec.model_id,
        env_secrets=env_secrets,
    )

    orch.configure_tenant(tenant.tenant_id, provider_spec=provider_spec)
    await svc.start_tenant(session, tenant.tenant_id)
    try:
        verified = await svc.verify_tenant(session, tenant.tenant_id)
    except Exception as exc:
        await svc.mark_verification_failed(session, tenant.tenant_id, str(exc))
        log.error("tenant_verification_failed", tenant_id=str(tenant.tenant_id), error=str(exc))
        raise

    await session.commit()
    return ProvisionedTenant(
        tenant_id=str(verified.tenant_id),
        slug=verified.slug,
        status=verified.status.value,
        provider=provider_spec.key.value,
        model=provider_spec.model_id,
        url=f"https://{settings.edge_domain.rstrip('/')}/{verified.slug}/",
        verification_status=verified.verification_status.value,
        verification_error=verified.verification_error,
    )
