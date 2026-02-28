from __future__ import annotations

import asyncio
import json
import uuid

import click


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


@click.group()
def cli():
    """OCTW - OpenClaw Multi-Tenant Wrapper CLI"""
    pass


@cli.group()
def tenant():
    """Manage tenants."""
    pass


@tenant.command("create")
@click.option("--slug", required=True, help="DNS-safe tenant slug")
@click.option("--name", required=True, help="Tenant display name")
@click.option("--plan", default="standard", help="Tenant plan")
@click.option("--isolation", default="standard", type=click.Choice(["standard", "hardened"]))
@click.option("--no-trusted-proxy", is_flag=True, default=False)
def tenant_create(slug, name, plan, isolation, no_trusted_proxy):
    """Create a new tenant."""
    async def _create():
        from octw.db.engine import async_session, engine
        from octw.db.tables import Base
        from octw.models.tenant import IsolationMode, TenantCreate, TenantPlan
        from octw.orchestrator.docker_orch import DockerOrchestrator
        from octw.orchestrator.tenant_service import TenantService
        from octw.vault.envelope import EnvelopeVault
        from octw.vault.service import VaultService

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        orch = DockerOrchestrator()
        vault = EnvelopeVault()
        vault_svc = VaultService(vault)
        svc = TenantService(orch, vault_svc)

        req = TenantCreate(
            slug=slug,
            name=name,
            plan=TenantPlan(plan),
            isolation_mode=IsolationMode(isolation),
            trusted_proxy_auth=not no_trusted_proxy,
        )
        async with async_session() as session:
            tenant = await svc.create_tenant(session, req)
            await session.commit()
            click.echo(json.dumps({
                "tenantId": str(tenant.tenant_id),
                "slug": tenant.slug,
                "status": tenant.status.value,
                "networkId": tenant.network_id,
            }, indent=2))
        await engine.dispose()

    _run(_create())


@tenant.command("list")
def tenant_list():
    """List all tenants."""
    async def _list():
        from octw.db.engine import async_session, engine
        from octw.db.tables import Base
        from octw.orchestrator.docker_orch import DockerOrchestrator
        from octw.orchestrator.tenant_service import TenantService
        from octw.vault.envelope import EnvelopeVault
        from octw.vault.service import VaultService

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        orch = DockerOrchestrator()
        vault = EnvelopeVault()
        vault_svc = VaultService(vault)
        svc = TenantService(orch, vault_svc)

        async with async_session() as session:
            tenants = await svc.list_tenants(session)
            for t in tenants:
                state = orch.get_container_state(t.tenant_id)
                click.echo(
                    f"{t.slug:20s}  {t.tenant_id}  "
                    f"status={t.status.value:15s}  container={state.value}"
                )
        await engine.dispose()

    _run(_list())


@tenant.command("start")
@click.argument("tenant_id")
def tenant_start(tenant_id):
    """Start a tenant container."""
    async def _start():
        from octw.db.engine import async_session, engine
        from octw.db.tables import Base
        from octw.orchestrator.docker_orch import DockerOrchestrator
        from octw.orchestrator.tenant_service import TenantService
        from octw.vault.envelope import EnvelopeVault
        from octw.vault.service import VaultService

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        orch = DockerOrchestrator()
        vault = EnvelopeVault()
        vault_svc = VaultService(vault)
        svc = TenantService(orch, vault_svc)

        tid = uuid.UUID(tenant_id)
        async with async_session() as session:
            cid = await svc.start_tenant(session, tid)
            await session.commit()
            click.echo(f"Started tenant {tenant_id}, container={cid}")
        await engine.dispose()

    _run(_start())


@tenant.command("stop")
@click.argument("tenant_id")
def tenant_stop(tenant_id):
    """Stop a tenant container."""
    async def _stop():
        from octw.db.engine import async_session, engine
        from octw.db.tables import Base
        from octw.orchestrator.docker_orch import DockerOrchestrator
        from octw.orchestrator.tenant_service import TenantService
        from octw.vault.envelope import EnvelopeVault
        from octw.vault.service import VaultService

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        orch = DockerOrchestrator()
        vault = EnvelopeVault()
        vault_svc = VaultService(vault)
        svc = TenantService(orch, vault_svc)

        tid = uuid.UUID(tenant_id)
        async with async_session() as session:
            await svc.stop_tenant(session, tid)
            await session.commit()
            click.echo(f"Stopped tenant {tenant_id}")
        await engine.dispose()

    _run(_stop())


@tenant.command("pause")
@click.argument("tenant_id")
def tenant_pause(tenant_id):
    """Pause a tenant container."""
    async def _pause():
        from octw.db.engine import async_session, engine
        from octw.db.tables import Base
        from octw.orchestrator.docker_orch import DockerOrchestrator
        from octw.orchestrator.tenant_service import TenantService
        from octw.vault.envelope import EnvelopeVault
        from octw.vault.service import VaultService

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        orch = DockerOrchestrator()
        vault = EnvelopeVault()
        vault_svc = VaultService(vault)
        svc = TenantService(orch, vault_svc)

        tid = uuid.UUID(tenant_id)
        async with async_session() as session:
            await svc.pause_tenant(session, tid)
            await session.commit()
            click.echo(f"Paused tenant {tenant_id}")
        await engine.dispose()

    _run(_pause())


@tenant.command("status")
@click.argument("tenant_id")
def tenant_status(tenant_id):
    """Get tenant runtime status."""
    async def _status():
        from octw.db.engine import async_session, engine
        from octw.db.tables import Base
        from octw.orchestrator.docker_orch import DockerOrchestrator
        from octw.orchestrator.tenant_service import TenantService
        from octw.vault.envelope import EnvelopeVault
        from octw.vault.service import VaultService

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        orch = DockerOrchestrator()
        vault = EnvelopeVault()
        vault_svc = VaultService(vault)
        svc = TenantService(orch, vault_svc)

        tid = uuid.UUID(tenant_id)
        async with async_session() as session:
            info = await svc.get_runtime_info(session, tid)
            click.echo(json.dumps(info.model_dump(mode="json"), indent=2))
        await engine.dispose()

    _run(_status())


@tenant.command("delete")
@click.argument("tenant_id")
@click.option("--yes", is_flag=True, help="Skip confirmation")
def tenant_delete(tenant_id, yes):
    """Delete a tenant and all its resources."""
    if not yes:
        click.confirm(f"Delete tenant {tenant_id} and all data?", abort=True)

    async def _delete():
        from octw.db.engine import async_session, engine
        from octw.db.tables import Base
        from octw.orchestrator.docker_orch import DockerOrchestrator
        from octw.orchestrator.tenant_service import TenantService
        from octw.vault.envelope import EnvelopeVault
        from octw.vault.service import VaultService

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        orch = DockerOrchestrator()
        vault = EnvelopeVault()
        vault_svc = VaultService(vault)
        svc = TenantService(orch, vault_svc)

        tid = uuid.UUID(tenant_id)
        async with async_session() as session:
            await svc.delete_tenant(session, tid)
            await session.commit()
            click.echo(f"Deleted tenant {tenant_id}")
        await engine.dispose()

    _run(_delete())


@cli.group()
def secret():
    """Manage tenant secrets."""
    pass


@secret.command("set")
@click.argument("tenant_id")
@click.option("--name", required=True, help="Secret name")
@click.option("--value", required=True, prompt=True, hide_input=True, help="Secret value")
@click.option("--env-var", default=None, help="Target environment variable name")
def secret_set(tenant_id, name, value, env_var):
    """Set a tenant secret."""
    async def _set():
        from octw.db.engine import async_session, engine
        from octw.db.tables import Base
        from octw.vault.envelope import EnvelopeVault
        from octw.vault.service import VaultService

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        vault = EnvelopeVault()
        vault_svc = VaultService(vault)

        tid = uuid.UUID(tenant_id)
        async with async_session() as session:
            await vault_svc.store_secret(
                session, tid, name, value, target_env_var=env_var
            )
            await session.commit()
            click.echo(f"Secret '{name}' stored for tenant {tenant_id}")
        await engine.dispose()

    _run(_set())


@secret.command("list")
@click.argument("tenant_id")
def secret_list(tenant_id):
    """List tenant secrets (metadata only)."""
    async def _list():
        from octw.db.engine import async_session, engine
        from octw.db.tables import Base
        from octw.vault.envelope import EnvelopeVault
        from octw.vault.service import VaultService

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        vault = EnvelopeVault()
        vault_svc = VaultService(vault)

        tid = uuid.UUID(tenant_id)
        async with async_session() as session:
            metadata = await vault_svc.list_secret_metadata(session, tid)
            for m in metadata:
                click.echo(
                    f"  {m.name:30s}  type={m.type.value:10s}  "
                    f"env={m.target_env_var or '-'}"
                )
        await engine.dispose()

    _run(_list())


@cli.group()
def server():
    """Run OCTW services."""
    pass


@server.command("api")
@click.option("--host", default="0.0.0.0")
@click.option("--port", default=8000, type=int)
def run_api(host, port):
    """Run the OCTW API server."""
    import uvicorn
    uvicorn.run("octw.api.app:app", host=host, port=port, reload=False)


@server.command("edge")
@click.option("--host", default="0.0.0.0")
@click.option("--port", default=8443, type=int)
def run_edge(host, port):
    """Run the OCTW edge proxy."""
    import uvicorn
    uvicorn.run("octw.edge.proxy:edge_app", host=host, port=port, reload=False)


if __name__ == "__main__":
    cli()
