from __future__ import annotations

import os
import stat
import subprocess
import textwrap
import time
import uuid
from pathlib import Path

from docker.errors import NotFound
from docker.types import Mount

import docker
from octw.common.config import settings
from octw.common.logging import get_logger
from octw.models.tenant import ContainerState, IsolationMode, Tenant

log = get_logger(__name__)

OPENCLAW_GATEWAY_PORT = 18789
OPENCLAW_CANVAS_PORT = 18790
CONTAINER_HOME = "/home/node"
CONTAINER_STATE_DIR = f"{CONTAINER_HOME}/.openclaw"
CONTAINER_WORKSPACE_DIR = f"{CONTAINER_HOME}/.openclaw/workspace"

WS_PROBE_SCRIPT = textwrap.dedent(
    """
    import asyncio
    import json
    import sys
    import websockets

    async def main() -> int:
        uri, origin, email = sys.argv[1:4]
        async with websockets.connect(
            uri,
            additional_headers={
                "Origin": origin,
                "x-octw-user-email": email,
                "x-forwarded-for": "127.0.0.1",
                "x-forwarded-proto": "https",
                "x-forwarded-host": origin.replace("https://", "").replace("http://", ""),
            },
            open_timeout=10,
            close_timeout=5,
            max_size=1_000_000,
        ) as ws:
            req = {
                "type": "req",
                "id": "octw-probe",
                "method": "connect",
                "params": {
                    "minProtocol": 3,
                    "maxProtocol": 3,
                    "client": {
                        "id": "openclaw-control-ui",
                        "version": "control-ui",
                        "platform": "linux",
                        "mode": "webchat",
                    },
                    "role": "operator",
                    "scopes": ["operator.admin", "operator.approvals", "operator.pairing"],
                    "caps": ["tool-events"],
                    "locale": "en-US",
                    "userAgent": "octw-probe",
                },
            }
            await ws.send(json.dumps(req))
            while True:
                response = json.loads(await ws.recv())
                if response.get("type") == "event":
                    continue
                if response.get("type") != "res" or response.get("id") != "octw-probe":
                    continue
                if not response.get("ok"):
                    raise RuntimeError(json.dumps(response))
                break
            payload = response.get("payload") or {}
            if payload.get("type") != "hello-ok":
                raise RuntimeError(json.dumps(response))
            await ws.send(json.dumps({
                "type": "req",
                "id": "octw-status",
                "method": "health",
                "params": {},
            }))
            health = json.loads(await ws.recv())
            if health.get("type") != "res" or not health.get("ok"):
                raise RuntimeError(json.dumps(health))
        return 0

    raise SystemExit(asyncio.run(main()))
    """
).strip()


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

    def _edge_container(self):
        return self._client.containers.get(settings.edge_container_name)

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
                os.chmod(d, stat.S_IRWXU)
                if os.getuid() == 0:
                    os.chown(d, 1000, 1000)
            except OSError:
                pass
        log.info("tenant_dirs_created", tenant_id=str(tenant_id), dirs=dirs)
        return dirs

    def remove_tenant_dirs(self, tenant_id: uuid.UUID) -> None:
        import shutil

        base = self._tenant_dir(tenant_id)
        if not base.exists():
            return
        try:
            shutil.rmtree(base)
        except PermissionError:
            subprocess.run(["sudo", "rm", "-rf", str(base)], check=True, capture_output=True)
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

    def connect_edge_to_network(
        self, tenant_id: uuid.UUID, edge_container: str | None = None
    ) -> str | None:
        name = self._network_name(tenant_id)
        target = edge_container or settings.edge_container_name
        try:
            net = self._client.networks.get(name)
            net.reload()
            connected = net.attrs.get("Containers", {}) or {}
            edge = self._client.containers.get(target)
            if edge.id not in connected:
                net.connect(edge)
                log.info("edge_connected", tenant_id=str(tenant_id), edge_container=edge.name)
            return self.get_named_container_ip(target, name)
        except Exception as e:
            log.warning("edge_connect_failed", tenant_id=str(tenant_id), error=str(e))
            return None

    def get_named_container_ip(self, container_name: str, network_name: str) -> str | None:
        try:
            container = self._client.containers.get(container_name)
        except NotFound:
            return None
        nets = container.attrs.get("NetworkSettings", {}).get("Networks", {})
        info = nets.get(network_name)
        if info:
            return info.get("IPAddress")
        return None

    # --- Init / Onboarding ---

    def run_init_job(
        self,
        tenant: Tenant,
        provider_env_var: str | None = None,
        provider_model: str | None = None,
        env_secrets: dict[str, str] | None = None,
        timeout: int = 120,
    ) -> str:
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

    def tenant_config_exists(self, tenant_id: uuid.UUID) -> bool:
        state_dir = Path(settings.tenant_base_dir) / str(tenant_id) / "state"
        return (state_dir / "openclaw.json").exists()

    def configure_tenant(
        self,
        tenant_id: uuid.UUID,
        provider_spec: object | None = None,
    ) -> None:
        state_dir = Path(settings.tenant_base_dir) / str(tenant_id) / "state"
        config_path = state_dir / "openclaw.json"
        if not config_path.exists():
            log.warning("config_not_found", tenant_id=str(tenant_id))
            return

        import json

        from octw.models.provider import ProviderSpec

        spec: ProviderSpec | None = provider_spec  # type: ignore[assignment]

        config = json.loads(config_path.read_text())

        config["gateway"] = config.get("gateway", {})
        config["gateway"]["bind"] = "lan"
        config["gateway"]["port"] = OPENCLAW_GATEWAY_PORT
        edge_ip = self.connect_edge_to_network(tenant_id)
        config["gateway"]["trustedProxies"] = [ip for ip in [edge_ip] if ip]
        config["gateway"]["auth"] = config["gateway"].get("auth", {})
        config["gateway"]["auth"]["mode"] = "trusted-proxy"
        config["gateway"]["auth"]["trustedProxy"] = {
            "userHeader": "x-octw-user-email",
            "requiredHeaders": ["x-forwarded-proto", "x-forwarded-host"],
        }
        control_ui = config["gateway"].get("controlUi", {})
        control_ui["allowedOrigins"] = [settings.public_base_url.rstrip("/")]
        control_ui.pop("dangerouslyAllowHostHeaderOriginFallback", None)
        control_ui.pop("allowInsecureAuth", None)
        control_ui.pop("dangerouslyDisableDeviceAuth", None)
        config["gateway"]["controlUi"] = control_ui

        if spec:
            config["agents"] = config.get("agents", {})
            config["agents"]["defaults"] = config["agents"].get("defaults", {})
            config["agents"]["defaults"]["model"] = {"primary": spec.model_id}

            if spec.builtin:
                providers = config.get("models", {}).get("providers", {})
                providers.pop(spec.provider_name, None)
            else:
                config["models"] = config.get("models", {})
                config["models"]["mode"] = "merge"
                providers = config["models"].get("providers", {})
                provider_entry: dict[str, object] = {"apiKey": f"${{{spec.env_var}}}"}
                if spec.base_url:
                    provider_entry["baseUrl"] = spec.base_url
                if spec.api_type:
                    provider_entry["api"] = spec.api_type
                provider_entry["models"] = [{"id": spec.model_name, "name": spec.display_name}]
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
        if provider_env_var:
            api_key = settings.get_provider_api_key(provider_env_var)
            if api_key:
                env[provider_env_var] = api_key
        if env_secrets:
            env.update(env_secrets)

        mounts = [
            Mount(target=CONTAINER_STATE_DIR, source=dirs["state"], type="bind"),
            Mount(target=CONTAINER_WORKSPACE_DIR, source=dirs["workspace"], type="bind"),
        ]

        runtime = "runsc" if tenant.isolation_mode == IsolationMode.HARDENED else None
        security_opt = ["no-new-privileges:true"]
        try:
            existing = self._client.containers.get(name)
            if existing.status == "paused":
                existing.unpause()
                self.connect_edge_to_network(tenant.tenant_id)
                log.info("container_unpaused", tenant_id=str(tenant.tenant_id))
                return existing.id
            if existing.status == "exited":
                existing.remove()
            elif existing.status == "running":
                self.connect_edge_to_network(tenant.tenant_id)
                return existing.id
            else:
                existing.remove(force=True)
        except NotFound:
            pass

        network_name = self._network_name(tenant.tenant_id)
        self.create_network(tenant.tenant_id)
        self.connect_edge_to_network(tenant.tenant_id)

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
                "interval": 30_000_000_000,
                "timeout": 5_000_000_000,
                "retries": 3,
                "start_period": 10_000_000_000,
            },
        )
        log.info("container_started", tenant_id=str(tenant.tenant_id), container_id=container.id)
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
                self.connect_edge_to_network(tenant_id)
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
            kwargs: dict[str, object] = {"tail": tail, "timestamps": True}
            if since:
                kwargs["since"] = since
            return container.logs(**kwargs).decode(errors="replace")
        except NotFound:
            return ""

    def get_container_ip(self, tenant_id: uuid.UUID) -> str | None:
        return self.get_named_container_ip(
            self._container_name(tenant_id), self._network_name(tenant_id)
        )

    def wait_for_gateway_health(self, tenant_id: uuid.UUID, timeout: int = 45) -> None:
        deadline = time.time() + timeout
        ip: str | None = None
        while time.time() < deadline:
            ip = self.get_container_ip(tenant_id)
            if not ip:
                time.sleep(1)
                continue
            result = self._edge_container().exec_run([
                "curl", "-fsS", f"http://{ip}:{OPENCLAW_GATEWAY_PORT}/health"
            ])
            if result.exit_code == 0:
                return
            time.sleep(1)
        raise RuntimeError(f"Gateway health check failed for tenant {tenant_id} (last ip={ip})")

    def verify_gateway_ws(self, tenant_id: uuid.UUID, email: str, timeout: int = 45) -> None:
        deadline = time.time() + timeout
        ip: str | None = None
        last_output = ""
        while time.time() < deadline:
            ip = self.get_container_ip(tenant_id)
            if not ip:
                time.sleep(1)
                continue
            result = self._edge_container().exec_run([
                "/app/.venv/bin/python",
                "-c",
                WS_PROBE_SCRIPT,
                f"ws://{ip}:{OPENCLAW_GATEWAY_PORT}",
                settings.public_base_url.rstrip("/"),
                email,
            ])
            if isinstance(result.output, (bytes, bytearray)):
                output = result.output.decode(errors="replace")
            else:
                output = str(result.output)
            last_output = output.strip()
            if result.exit_code == 0:
                return
            time.sleep(1)
        raise RuntimeError(
            "Gateway websocket verification failed for tenant "
            f"{tenant_id}: {last_output or 'unknown error'}"
        )

    def cleanup_tenant(self, tenant_id: uuid.UUID) -> None:
        self.stop_container(tenant_id)
        self.remove_network(tenant_id)
        self.remove_tenant_dirs(tenant_id)
        log.info("tenant_cleaned_up", tenant_id=str(tenant_id))
