from __future__ import annotations

from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode


class OCTWSettings(BaseSettings):
    model_config = {"env_prefix": "OCTW_"}

    db_url: str = "postgresql+asyncpg://octw:octw@localhost:5432/octw"
    redis_url: str = "redis://localhost:6379/0"

    tenant_base_dir: str = "/var/lib/octw/tenants"
    openclaw_image: str = "ghcr.io/openclaw/openclaw:latest"
    openclaw_digest: str | None = None

    edge_listen_host: str = "0.0.0.0"
    edge_listen_port: int = 8443
    edge_domain: str = "octw.example.com"
    edge_container_name: str = "octw-edge"
    api_internal_base_url: str = "http://octw-api:8000"
    public_base_url: str = "https://octw.example.com"

    jwt_secret: str = "CHANGE-ME-IN-PRODUCTION"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    kek_path: str = "/etc/octw/master.key"

    default_mem_limit: str = "1536m"
    default_cpu_quota: int = 100000  # microseconds per period
    default_cpu_period: int = 100000
    default_pids_limit: int = 512
    default_provider: str = "zai"

    idle_pause_seconds: int = 1800  # 30 min
    idle_stop_seconds: int = 28800  # 8 hours

    # Shared provider API keys (set on the host, used for all tenants).
    zai_api_key: str | None = None
    moonshot_api_key: str | None = None
    minimax_api_key: str | None = None

    # Browser auth via reverse proxy.
    trusted_proxy_enabled: bool = False
    trusted_proxy_user_header: str = "X-Forwarded-Email"
    trusted_proxy_ips: Annotated[list[str], NoDecode] = Field(default_factory=list)

    # WebChat is enabled by default during onboarding.
    webchat_port: int = 18790

    log_level: str = "INFO"

    @field_validator("trusted_proxy_ips", mode="before")
    @classmethod
    def _parse_proxy_ips(cls, value):
        if value in (None, "", []):
            return []
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    def get_provider_api_key(self, env_var: str) -> str | None:
        mapping = {
            "ZAI_API_KEY": self.zai_api_key,
            "MOONSHOT_API_KEY": self.moonshot_api_key,
            "MINIMAX_API_KEY": self.minimax_api_key,
        }
        return mapping.get(env_var)


settings = OCTWSettings()
