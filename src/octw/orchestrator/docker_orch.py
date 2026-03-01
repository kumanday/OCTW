from __future__ import annotations

import os
import stat
import uuid
from pathlib import Path

import docker
from docker.errors import NotFound
from docker.types import Mount

from octw.common.config import settings
from octw.common.logging import get_logger
from octw.models.tenant import ContainerState, IsolationMode, Tenant

log = get_logger(__name__)

OPENCLAW_GATEWAY_PORT = 18789
OPENCLAW_CANVAS_PORT = 18790
CONTAINER_HOME = "/home/node"
CONTAINER_STATE_DIR = f"{CONTAINER_HOME}/.openclaw"
CONTAINER_WORKSPACE_DIR = f"{CONTAINER_HOME}/.openclaw/workspace"


class DockerOrchestrator:
    def __init__(self) -> None:
        self._client = docker.from_env()

    def _tenant_dir(self, tenant_id: uuid.UUID) -> Path:
        return Path(settings.tenant_base_dir) / str(tenant_id)

    def _container_name(self, tenant_id: uuid.UUID) -> str:
        return f"octw_tenant_{tenant_id}"

    def _network_name(self, tenant_id: uuid.UUID) -> str:
        return f"octw_tenant_{tenant_id}"

    def _image_ref(self, tenant: Tenant) -> str:
        if tenant.openclaw_digest:
            base = tenant.openclaw_image or settings.openclaw_image
            ref = base.split("@")[0].split(":")[0]
            return f"{ref}@{tenant.openclaw_digest}"
        return tenant.openclaw_image or settings.openclaw_image

    # --- Filesystem ---

    def create_tenant_dirs(self, tenant_id: uuid.UUID) -> dict[str, str]:
        base = self._tenant_dir(tenant_id)
        dirs = {
            "state": str(base / "state"),
            "workspace": str(base / "workspace"),
            "logs": str(base / "logs"),
        }
        for d in dirs.values():
            try:
                os.makedirs(d, exist_ok=True)
            except PermissionError:
                raise RuntimeError(
                    f"Cannot create tenant directory '{d}'. "
                    f"Run: sudo mkdir -p {settings.tenant_base_dir} && "
                    f"sudo chown $USER {settings.tenant_base_dir}"
                ) from None
            try:
                os.chmod(d, stat.S_IRWXU)  # 0700
                if os.getuid() == 0:
                    os.chown(d, 1000, 1000)
            except OSError:
                pass  # already exists with correct permissions
        log.info("tenant_dirs_created", tenant_id=str(tenant_id), dirs=dirs)
        return dirs

    def remove_tenant_dirs(self, tenant_id: uuid.UUID) -> None:
        import shutil

        base = self._tenant_dir(tenant_id)
        if base.exists():
            shutil.rmtree(base)
            log.info("tenant_dirs_removed", tenant_id=str(tenant_id))

    # --- Network ---

    def create_network(self, tenant_id: uuid.UUID) -> str:
        name = self._network_name(tenant_id)
        try:
            net = self._client.networks.get(name)
            return net.id
        except NotFound:
            pass
        net = self._client.networks.create(
            name=name,
            driver="bridge",
            internal=True,
            labels={"octw.tenant_id": str(tenant_id)},
        )
        log.info("network_created", tenant_id=str(tenant_id), network_id=net.id)
        return net.id

    def remove_network(self, tenant_id: uuid.UUID) -> None:
        name = self._network_name(tenant_id)
        try:
            net = self._client.networks.get(name)
            net.remove()
            log.info("network_removed", tenant_id=str(tenant_id))
        except NotFound:
            pass

    def connect_edge_to_network(self, tenant_id: uuid.UUID, edge_container: str) -> None:
        name = self._network_name(tenant_id)
        try:
            net = self._client.networks.get(name)
            net.connect(edge_container)
        except Exception as e:
            log.warning("edge_connect_failed", tenant_id=str(tenant_id), error=str(e))

    # --- Init / Onboarding ---

    def run_init_job(
        self,
        tenant: Tenant,
        provider_env_var: str | None = None,
        provider_model: str | None = None,
        env_secrets: dict[str, str] | None = None,
        timeout: int = 120,
    ) -> str:
        """Run a one-shot container to onboard OpenClaw for this tenant."""
        init_name = f"octw_init_{tenant.tenant_id}"
        image = self._image_ref(tenant)
        dirs = self.create_tenant_dirs(tenant.tenant_id)

        env: dict[str, str] = {}
        if provider_env_var:
            api_key = settings.get_provider_api_key(provider_env_var)
            if api_key:
                env[provider_env_var] = api_key
        if provider_model:
            env["OPENCLAW_DEFAULT_MODEL"] = provider_model
        if env_secrets:
            env.update(env_secrets)

        mounts = [
            Mount(target=CONTAINER_STATE_DIR, source=dirs["state"], type="bind"),
            Mount(target=CONTAINER_WORKSPACE_DIR, source=dirs["workspace"], type="bind"),
        ]

        try:
            old = self._client.containers.get(init_name)
            old.remove(force=True)
        except NotFound:
            pass

        onboard_cmd = [
            "node", "openclaw.mjs", "onboard",
            "--non-interactive",
            "--mode", "local",
            "--flow", "quickstart",
            "--secret-input-mode", "ref",
            "--accept-risk",
        ]

        log.info("init_job_starting", tenant_id=str(tenant.tenant_id))
        container = self._client.containers.run(
            image=image,
            name=init_name,
            entrypoint=[],
            command=onboard_cmd,
            working_dir="/app",
            detach=True,
            environment=env,
            mounts=mounts,
            user="1000:1000",
            labels={"octw.tenant_id": str(tenant.tenant_id), "octw.role": "init"},
        )

        result = container.wait(timeout=timeout)
        output = container.logs().decode(errors="replace")
        exit_code = result.get("StatusCode", -1)
        container.remove()

        # The onboard command writes config/workspace then tries to start the
        # gateway and connect via WebSocket. In a one-shot init container the
        # gateway isn't running, so it exits 1 with a WS close error. This is
        # expected -- check that the config file was actually created.
        config_created = "Updated" in output and "openclaw.json" in output
        if exit_code != 0 and not config_created:
            log.error(
                "init_job_failed",
                tenant_id=str(tenant.tenant_id),
                exit_code=exit_code,
                output=output[-2000:],
            )
            raise RuntimeError(
                f"OpenClaw onboarding failed (exit {exit_code}): {output[-500:]}"
            )

        if exit_code != 0:
            log.info(
                "init_job_partial_success",
                tenant_id=str(tenant.tenant_id),
                detail="Config written; gateway connection expected to fail in init container",
            )

        log.info("init_job_completed", tenant_id=str(tenant.tenant_id))
        return output

    def configure_tenant(
        self,
        tenant_id: uuid.UUID,
        provider_spec: object | None = None,
    ) -> None:
        """Configure gateway and model provider in OpenClaw config."""
        state_dir = Path(settings.tenant_base_dir) / str(tenant_id) / "state"
        config_path = state_dir / "openclaw.json"
        if not config_path.exists():
            log.warning("config_not_found", tenant_id=str(tenant_id))
            return

        import json

        from octw.models.provider import ProviderSpec

        spec: ProviderSpec | None = provider_spec  # type: ignore[assignment]

        config = json.loads(config_path.read_text())

        # Gateway: bind to LAN so edge proxy can reach it
        config["gateway"] = config.get("gateway", {})
        config["gateway"]["bind"] = "lan"
        config["gateway"]["port"] = OPENCLAW_GATEWAY_PORT

        # Model provider
        if spec:
            # Set primary model in agents.defaults.model
            config["agents"] = config.get("agents", {})
            config["agents"]["defaults"] = config["agents"].get("defaults", {})
            config["agents"]["defaults"]["model"] = {
                "primary": spec.model_id,
            }

            if spec.builtin:
                # Built-in providers only need the env var set (done at
                # container start) and the model selection above.
                # Remove any stale custom providers entry for this provider.
                providers = config.get("models", {}).get("providers", {})
                providers.pop(spec.provider_name, None)
            else:
                # Custom provider: write full models.providers entry
                config["models"] = config.get("models", {})
                config["models"]["mode"] = "merge"
                providers = config["models"].get("providers", {})
                provider_entry: dict = {
                    "apiKey": f"${{{spec.env_var}}}",
                }
                if spec.base_url:
                    provider_entry["baseUrl"] = spec.base_url
                if spec.api_type:
                    provider_entry["api"] = spec.api_type
                provider_entry["models"] = [
                    {"id": spec.model_name, "name": spec.display_name},
                ]
                providers[spec.provider_name] = provider_entry
                config["models"]["providers"] = providers

        config_path.write_text(json.dumps(config, indent=2))
        log.info(
            "tenant_configured",
            tenant_id=str(tenant_id),
            provider=spec.model_id if spec else None,
        )

    # --- Container lifecycle ---

    def start_container(
        self,
        tenant: Tenant,
        env_secrets: dict[str, str] | None = None,
        provider_env_var: str | None = None,
    ) -> str:
        name = self._container_name(tenant.tenant_id)
        image = self._image_ref(tenant)
        dirs = self.create_tenant_dirs(tenant.tenant_id)
        limits = tenant.resource_limits

        env = {
            "OPENCLAW_GATEWAY_BIND": "lan",
            "OPENCLAW_GATEWAY_PORT": str(OPENCLAW_GATEWAY_PORT),
            "OPENCLAW_CANVAS_PORT": str(OPENCLAW_CANVAS_PORT),
        }
        # Inject the selected provider's API key from server config
        if provider_env_var:
            api_key = settings.get_provider_api_key(provider_env_var)
            if api_key:
                env[provider_env_var] = api_key
        if env_secrets:
            env.update(env_secrets)

        mounts = [
            Mount(
                target=CONTAINER_STATE_DIR,
                source=dirs["state"],
                type="bind",
            ),
            Mount(
                target=CONTAINER_WORKSPACE_DIR,
                source=dirs["workspace"],
                type="bind",
            ),
        ]

        runtime = None
        if tenant.isolation_mode == IsolationMode.HARDENED:
            runtime = "runsc"

        security_opt = ["no-new-privileges:true"]
        try:
            existing = self._client.containers.get(name)
            if existing.status == "paused":
                existing.unpause()
                log.info("container_unpaused", tenant_id=str(tenant.tenant_id))
                return existing.id
            if existing.status == "exited":
                existing.remove()
            elif existing.status == "running":
                return existing.id
            else:
                existing.remove(force=True)
        except NotFound:
            pass

        network_name = self._network_name(tenant.tenant_id)
        self.create_network(tenant.tenant_id)

        container = self._client.containers.run(
            image=image,
            name=name,
            detach=True,
            environment=env,
            mounts=mounts,
            network=network_name,
            runtime=runtime,
            security_opt=security_opt,
            cap_drop=["ALL"],
            mem_limit=limits.mem_limit,
            cpu_quota=limits.cpu_quota,
            cpu_period=limits.cpu_period,
            pids_limit=limits.pids_limit,
            user="1000:1000",
            labels={
                "octw.tenant_id": str(tenant.tenant_id),
                "octw.tenant_slug": tenant.slug,
            },
            restart_policy={"Name": "unless-stopped"},
            healthcheck={
                "test": ["CMD", "curl", "-sf", f"http://localhost:{OPENCLAW_GATEWAY_PORT}/health"],
                "interval": 30_000_000_000,  # 30s in ns
                "timeout": 5_000_000_000,
                "retries": 3,
                "start_period": 10_000_000_000,
            },
        )
        log.info(
            "container_started",
            tenant_id=str(tenant.tenant_id),
            container_id=container.id,
        )
        return container.id

    def stop_container(self, tenant_id: uuid.UUID, timeout: int = 30) -> None:
        name = self._container_name(tenant_id)
        try:
            container = self._client.containers.get(name)
            container.stop(timeout=timeout)
            container.remove()
            log.info("container_stopped", tenant_id=str(tenant_id))
        except NotFound:
            log.debug("container_not_found_for_stop", tenant_id=str(tenant_id))

    def pause_container(self, tenant_id: uuid.UUID) -> None:
        name = self._container_name(tenant_id)
        try:
            container = self._client.containers.get(name)
            if container.status == "running":
                container.pause()
                log.info("container_paused", tenant_id=str(tenant_id))
        except NotFound:
            log.debug("container_not_found_for_pause", tenant_id=str(tenant_id))

    def unpause_container(self, tenant_id: uuid.UUID) -> None:
        name = self._container_name(tenant_id)
        try:
            container = self._client.containers.get(name)
            if container.status == "paused":
                container.unpause()
                log.info("container_unpaused", tenant_id=str(tenant_id))
        except NotFound:
            pass

    def get_container_state(self, tenant_id: uuid.UUID) -> ContainerState:
        name = self._container_name(tenant_id)
        try:
            container = self._client.containers.get(name)
            status = container.status
            if status == "running":
                return ContainerState.RUNNING
            if status == "paused":
                return ContainerState.PAUSED
            if status in ("exited", "created"):
                return ContainerState.STOPPED
            return ContainerState.ERROR
        except NotFound:
            return ContainerState.NOT_FOUND

    def get_container_logs(
        self, tenant_id: uuid.UUID, since: int | None = None, tail: int = 200
    ) -> str:
        name = self._container_name(tenant_id)
        try:
            container = self._client.containers.get(name)
            kwargs: dict = {"tail": tail, "timestamps": True}
            if since:
                kwargs["since"] = since
            return container.logs(**kwargs).decode(errors="replace")
        except NotFound:
            return ""

    def get_container_ip(self, tenant_id: uuid.UUID) -> str | None:
        name = self._container_name(tenant_id)
        network_name = self._network_name(tenant_id)
        try:
            container = self._client.containers.get(name)
            nets = container.attrs.get("NetworkSettings", {}).get("Networks", {})
            net_info = nets.get(network_name)
            if net_info:
                return net_info.get("IPAddress")
        except NotFound:
            pass
        return None

    def cleanup_tenant(self, tenant_id: uuid.UUID) -> None:
        self.stop_container(tenant_id)
        self.remove_network(tenant_id)
        self.remove_tenant_dirs(tenant_id)
        log.info("tenant_cleaned_up", tenant_id=str(tenant_id))
