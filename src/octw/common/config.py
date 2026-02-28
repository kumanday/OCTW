from __future__ import annotations

from pydantic_settings import BaseSettings


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

    jwt_secret: str = "CHANGE-ME-IN-PRODUCTION"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    kek_path: str = "/etc/octw/master.key"

    default_mem_limit: str = "1536m"
    default_cpu_quota: int = 100000  # microseconds per period
    default_cpu_period: int = 100000
    default_pids_limit: int = 512

    idle_pause_seconds: int = 1800  # 30 min
    idle_stop_seconds: int = 28800  # 8 hours

    log_level: str = "INFO"


settings = OCTWSettings()
