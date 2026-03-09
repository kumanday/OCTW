from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from octw.common.config import settings
from octw.common.logging import get_logger
from octw.db.tables import AuditEventRow, MembershipRow, TenantRow, UserRow
from octw.models.secret import AuditAction
from octw.models.tenant import (
    ContainerState,
    Member,
    ResourceLimits,
    Role,
    Tenant,
    TenantCreate,
    TenantRuntimeInfo,
    TenantStatus,
    VerificationStatus,
)
from octw.orchestrator.docker_orch import DockerOrchestrator
from octw.vault.service import VaultService

log = get_logger(__name__)


class TenantService:
    def __init__(
        self, orch: DockerOrchestrator, vault_service: VaultService
    ) -> None:
        self._orch = orch
        self._vault = vault_service

    async def _emit_audit(
        self,
        session: AsyncSession,
        action: AuditAction,
        tenant_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
        detail: dict | None = None,
    ) -> None:
        session.add(AuditEventRow(
            tenant_id=tenant_id,
            user_id=user_id,
            action=action.value,
            detail=detail,
        ))
        await session.flush()

    async def create_tenant(
        self,
        session: AsyncSession,
        req: TenantCreate,
        creator_user_id: uuid.UUID | None = None,
    ) -> Tenant:
        limits = req.resource_limits or ResourceLimits()
        row = TenantRow(
            slug=req.slug,
            name=req.name,
            owner_user_id=creator_user_id,
            plan=req.plan.value,
            status=TenantStatus.PROVISIONING.value,
            verification_status=VerificationStatus.PENDING.value,
            isolation_mode=req.isolation_mode.value,
            resource_limits=limits.model_dump(),
            trusted_proxy_auth=req.trusted_proxy_auth,
            openclaw_image=settings.openclaw_image,
            openclaw_digest=settings.openclaw_digest,
        )
        session.add(row)
        await session.flush()

        tenant = self._row_to_tenant(row)

        self._orch.create_tenant_dirs(tenant.tenant_id)
        network_id = self._orch.create_network(tenant.tenant_id)
        self._orch.connect_edge_to_network(tenant.tenant_id)
        row.network_id = network_id
        row.status = TenantStatus.STOPPED.value
        await session.flush()

        await self._emit_audit(
            session, AuditAction.TENANT_CREATE,
            tenant_id=tenant.tenant_id,
            user_id=creator_user_id,
            detail={"slug": req.slug},
        )

        if creator_user_id:
            await self._ensure_membership(
                session, tenant.tenant_id, creator_user_id, Role.TENANT_ADMIN
            )

        tenant.status = TenantStatus.STOPPED
        tenant.network_id = network_id
        tenant.owner_user_id = creator_user_id
        log.info("tenant_created", tenant_id=str(tenant.tenant_id), slug=req.slug)
        return tenant

    async def get_tenant(
        self, session: AsyncSession, tenant_id: uuid.UUID
    ) -> Tenant | None:
        row = await session.get(TenantRow, tenant_id)
        return self._row_to_tenant(row) if row else None

    async def get_tenant_by_slug(
        self, session: AsyncSession, slug: str
    ) -> Tenant | None:
        result = await session.execute(
            select(TenantRow).where(TenantRow.slug == slug)
        )
        row = result.scalar_one_or_none()
        return self._row_to_tenant(row) if row else None

    async def get_owner_tenant(
        self, session: AsyncSession, owner_user_id: uuid.UUID
    ) -> Tenant | None:
        result = await session.execute(
            select(TenantRow).where(TenantRow.owner_user_id == owner_user_id)
        )
        row = result.scalar_one_or_none()
        return self._row_to_tenant(row) if row else None

    async def list_tenants(
        self, session: AsyncSession, user_id: uuid.UUID | None = None
    ) -> list[Tenant]:
        if user_id:
            q = (
                select(TenantRow)
                .join(MembershipRow, MembershipRow.tenant_id == TenantRow.tenant_id)
                .where(MembershipRow.user_id == user_id)
            )
        else:
            q = select(TenantRow)
        rows = (await session.execute(q)).scalars().all()
        return [self._row_to_tenant(r) for r in rows]

    async def delete_tenant(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID | None = None,
    ) -> None:
        row = await session.get(TenantRow, tenant_id)
        if not row:
            return
        row.status = TenantStatus.DELETING.value
        await session.flush()

        self._orch.cleanup_tenant(tenant_id)

        await self._emit_audit(
            session, AuditAction.TENANT_DELETE,
            tenant_id=tenant_id, user_id=user_id,
        )
        await session.delete(row)
        await session.flush()
        log.info("tenant_deleted", tenant_id=str(tenant_id))

    async def start_tenant(
        self, session: AsyncSession, tenant_id: uuid.UUID
    ) -> str:
        tenant = await self.get_tenant(session, tenant_id)
        if not tenant:
            raise ValueError(f"Tenant {tenant_id} not found")

        secrets = await self._vault.get_decrypted_secrets(session, tenant_id)

        provider_spec = None
        provider_env_var: str | None = None
        if tenant.provider:
            from octw.models.provider import get_provider
            provider_spec = get_provider(tenant.provider)
            provider_env_var = provider_spec.env_var

        if self._orch.tenant_config_exists(tenant_id):
            self._orch.configure_tenant(tenant_id, provider_spec=provider_spec)

        container_id = self._orch.start_container(
            tenant, env_secrets=secrets, provider_env_var=provider_env_var,
        )

        await session.execute(
            update(TenantRow)
            .where(TenantRow.tenant_id == tenant_id)
            .values(
                status=TenantStatus.RUNNING.value,
                container_id=container_id,
                last_activity_at=datetime.utcnow(),
            )
        )
        await session.flush()

        await self._emit_audit(session, AuditAction.CONTAINER_START, tenant_id=tenant_id)
        return container_id

    async def stop_tenant(
        self, session: AsyncSession, tenant_id: uuid.UUID
    ) -> None:
        self._orch.stop_container(tenant_id)
        await session.execute(
            update(TenantRow)
            .where(TenantRow.tenant_id == tenant_id)
            .values(status=TenantStatus.STOPPED.value, container_id=None)
        )
        await session.flush()
        await self._emit_audit(session, AuditAction.CONTAINER_STOP, tenant_id=tenant_id)

    async def pause_tenant(
        self, session: AsyncSession, tenant_id: uuid.UUID
    ) -> None:
        self._orch.pause_container(tenant_id)
        await session.execute(
            update(TenantRow)
            .where(TenantRow.tenant_id == tenant_id)
            .values(status=TenantStatus.PAUSED.value)
        )
        await session.flush()
        await self._emit_audit(session, AuditAction.CONTAINER_PAUSE, tenant_id=tenant_id)

    async def wake_tenant(
        self, session: AsyncSession, tenant_id: uuid.UUID
    ) -> str:
        state = self._orch.get_container_state(tenant_id)
        if state == ContainerState.RUNNING:
            self._orch.connect_edge_to_network(tenant_id)
            await self._touch_activity(session, tenant_id)
            tenant = await self.get_tenant(session, tenant_id)
            return tenant.container_id or ""
        if state == ContainerState.PAUSED:
            self._orch.unpause_container(tenant_id)
            await session.execute(
                update(TenantRow)
                .where(TenantRow.tenant_id == tenant_id)
                .values(status=TenantStatus.RUNNING.value, last_activity_at=datetime.utcnow())
            )
            await session.flush()
            await self._emit_audit(session, AuditAction.CONTAINER_WAKE, tenant_id=tenant_id)
            tenant = await self.get_tenant(session, tenant_id)
            return tenant.container_id or ""
        return await self.start_tenant(session, tenant_id)

    async def verify_tenant(self, session: AsyncSession, tenant_id: uuid.UUID) -> Tenant:
        tenant = await self.get_tenant(session, tenant_id)
        if not tenant:
            raise ValueError(f"Tenant {tenant_id} not found")
        if not tenant.owner_user_id:
            raise ValueError(f"Tenant {tenant_id} has no owner for verification")

        owner = await session.get(UserRow, tenant.owner_user_id)
        if not owner:
            raise ValueError(f"Tenant {tenant_id} owner not found")
        if not self._orch.tenant_config_exists(tenant_id):
            raise RuntimeError(f"Tenant {tenant.slug} is missing openclaw.json")

        self._orch.wait_for_gateway_health(tenant_id)
        self._orch.verify_gateway_ws(tenant_id, owner.email)

        await session.execute(
            update(TenantRow)
            .where(TenantRow.tenant_id == tenant_id)
            .values(
                verification_status=VerificationStatus.VERIFIED.value,
                verification_error=None,
                verified_at=datetime.utcnow(),
            )
        )
        await session.flush()
        refreshed = await self.get_tenant(session, tenant_id)
        if not refreshed:
            raise ValueError(f"Tenant {tenant_id} disappeared after verification")
        return refreshed

    async def mark_verification_failed(
        self, session: AsyncSession, tenant_id: uuid.UUID, error: str
    ) -> None:
        await session.execute(
            update(TenantRow)
            .where(TenantRow.tenant_id == tenant_id)
            .values(
                verification_status=VerificationStatus.FAILED.value,
                verification_error=error,
            )
        )
        await session.flush()

    async def get_runtime_info(
        self, session: AsyncSession, tenant_id: uuid.UUID
    ) -> TenantRuntimeInfo:
        tenant = await self.get_tenant(session, tenant_id)
        if not tenant:
            raise ValueError(f"Tenant {tenant_id} not found")
        state = self._orch.get_container_state(tenant_id)
        return TenantRuntimeInfo(
            tenant_id=tenant_id,
            state=state,
            container_id=tenant.container_id,
            last_activity_at=tenant.last_activity_at,
            limits=tenant.resource_limits,
        )

    async def touch_activity(
        self, session: AsyncSession, tenant_id: uuid.UUID
    ) -> None:
        await self._touch_activity(session, tenant_id)

    async def _touch_activity(
        self, session: AsyncSession, tenant_id: uuid.UUID
    ) -> None:
        await session.execute(
            update(TenantRow)
            .where(TenantRow.tenant_id == tenant_id)
            .values(last_activity_at=datetime.utcnow())
        )
        await session.flush()

    async def _ensure_membership(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        role: Role,
    ) -> None:
        session.add(MembershipRow(
            tenant_id=tenant_id, user_id=user_id, role=role.value
        ))
        await session.flush()

    async def add_member(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        email: str,
        role: Role,
        actor_user_id: uuid.UUID | None = None,
    ) -> Member:
        user_row = (
            await session.execute(select(UserRow).where(UserRow.email == email))
        ).scalar_one_or_none()
        if not user_row:
            user_row = UserRow(email=email)
            session.add(user_row)
            await session.flush()

        membership = MembershipRow(
            tenant_id=tenant_id, user_id=user_row.user_id, role=role.value
        )
        session.add(membership)
        await session.flush()

        await self._emit_audit(
            session, AuditAction.MEMBER_ADD,
            tenant_id=tenant_id, user_id=actor_user_id,
            detail={"email": email, "role": role.value},
        )
        return Member(
            user_id=user_row.user_id,
            tenant_id=tenant_id,
            email=email,
            role=role,
        )

    async def list_members(
        self, session: AsyncSession, tenant_id: uuid.UUID
    ) -> list[Member]:
        rows = (
            await session.execute(
                select(MembershipRow, UserRow)
                .join(UserRow, UserRow.user_id == MembershipRow.user_id)
                .where(MembershipRow.tenant_id == tenant_id)
            )
        ).all()
        return [
            Member(
                user_id=m.user_id,
                tenant_id=m.tenant_id,
                email=u.email,
                role=Role(m.role),
                created_at=m.created_at,
            )
            for m, u in rows
        ]

    async def remove_member(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        actor_user_id: uuid.UUID | None = None,
    ) -> None:
        row = (
            await session.execute(
                select(MembershipRow).where(
                    MembershipRow.tenant_id == tenant_id,
                    MembershipRow.user_id == user_id,
                )
            )
        ).scalar_one_or_none()
        if row:
            await session.delete(row)
            await session.flush()
            await self._emit_audit(
                session, AuditAction.MEMBER_REMOVE,
                tenant_id=tenant_id, user_id=actor_user_id,
                detail={"removed_user_id": str(user_id)},
            )

    async def check_membership(
        self, session: AsyncSession, tenant_id: uuid.UUID, user_id: uuid.UUID
    ) -> Role | None:
        row = (
            await session.execute(
                select(MembershipRow).where(
                    MembershipRow.tenant_id == tenant_id,
                    MembershipRow.user_id == user_id,
                )
            )
        ).scalar_one_or_none()
        return Role(row.role) if row else None

    @staticmethod
    def _row_to_tenant(row: TenantRow) -> Tenant:
        limits = ResourceLimits(**(row.resource_limits or {}))
        return Tenant(
            tenant_id=row.tenant_id,
            slug=row.slug,
            name=row.name,
            owner_user_id=row.owner_user_id,
            plan=row.plan,
            status=row.status,
            verification_status=row.verification_status,
            verification_error=row.verification_error,
            verified_at=row.verified_at,
            isolation_mode=row.isolation_mode,
            resource_limits=limits,
            trusted_proxy_auth=row.trusted_proxy_auth,
            container_id=row.container_id,
            network_id=row.network_id,
            openclaw_image=row.openclaw_image,
            openclaw_digest=row.openclaw_digest,
            provider=row.provider,
            last_activity_at=row.last_activity_at,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
