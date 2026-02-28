from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

from sqlalchemy import select

from octw.common.config import settings
from octw.common.logging import get_logger
from octw.db.engine import async_session
from octw.db.tables import TenantRow
from octw.models.tenant import TenantStatus
from octw.orchestrator.docker_orch import DockerOrchestrator

log = get_logger(__name__)


class HibernationScheduler:
    def __init__(self, orch: DockerOrchestrator) -> None:
        self._orch = orch
        self._running = False

    async def run(self, interval_seconds: int = 60) -> None:
        self._running = True
        log.info("hibernation_scheduler_started")
        while self._running:
            try:
                await self._check_idle_tenants()
            except Exception:
                log.exception("hibernation_check_error")
            await asyncio.sleep(interval_seconds)

    def stop(self) -> None:
        self._running = False

    async def _check_idle_tenants(self) -> None:
        now = datetime.utcnow()
        pause_threshold = now - timedelta(seconds=settings.idle_pause_seconds)
        stop_threshold = now - timedelta(seconds=settings.idle_stop_seconds)

        async with async_session() as session:
            running = (
                await session.execute(
                    select(TenantRow).where(TenantRow.status == TenantStatus.RUNNING.value)
                )
            ).scalars().all()

            for row in running:
                last = row.last_activity_at or row.created_at
                if last < stop_threshold:
                    log.info("stopping_idle_tenant", tenant_id=str(row.tenant_id))
                    self._orch.stop_container(row.tenant_id)
                    row.status = TenantStatus.STOPPED.value
                    row.container_id = None
                elif last < pause_threshold:
                    log.info("pausing_idle_tenant", tenant_id=str(row.tenant_id))
                    self._orch.pause_container(row.tenant_id)
                    row.status = TenantStatus.PAUSED.value

            paused = (
                await session.execute(
                    select(TenantRow).where(TenantRow.status == TenantStatus.PAUSED.value)
                )
            ).scalars().all()

            for row in paused:
                last = row.last_activity_at or row.created_at
                if last < stop_threshold:
                    log.info("stopping_paused_tenant", tenant_id=str(row.tenant_id))
                    self._orch.stop_container(row.tenant_id)
                    row.status = TenantStatus.STOPPED.value
                    row.container_id = None

            await session.commit()
