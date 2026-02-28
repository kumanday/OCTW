# Configuration

All settings are controlled via environment variables with the `OCTW_` prefix.

## Core Settings

| Variable | Default | Description |
|---|---|---|
| `OCTW_DB_URL` | `postgresql+asyncpg://octw:octw@localhost:5432/octw` | Database connection string |
| `OCTW_REDIS_URL` | `redis://localhost:6379/0` | Redis connection string |
| `OCTW_JWT_SECRET` | `CHANGE-ME-IN-PRODUCTION` | JWT signing secret (use a strong random value) |
| `OCTW_JWT_ALGORITHM` | `HS256` | JWT algorithm |
| `OCTW_JWT_EXPIRE_MINUTES` | `60` | JWT token expiry |
| `OCTW_LOG_LEVEL` | `INFO` | Log level |

## Encryption

| Variable | Default | Description |
|---|---|---|
| `OCTW_KEK` | — | Master encryption key as hex string (32 bytes = 64 hex chars) |
| `OCTW_KEK_PATH` | `/etc/octw/master.key` | Path to 32-byte KEK file (used if `OCTW_KEK` is not set) |

The KEK encrypts per-tenant Data Encryption Keys (DEKs), which in turn encrypt individual secret values. See [security.md](security.md) for details.

## Provider API Keys

| Variable | Provider | Model |
|---|---|---|
| `OCTW_ZAI_API_KEY` | Z.ai GLM Coding Plan | `zai-coding/glm-5` |
| `OCTW_MOONSHOT_API_KEY` | Moonshot AI Kimi Coding Plan | `kimi-coding/k2p5` |
| `OCTW_MINIMAX_API_KEY` | MiniMax Coding Plan | `minimax-coding/MiniMax-M2.5` |

At least one provider key is required for provisioning. See [providers.md](providers.md) for details.

## OpenClaw Image

| Variable | Default | Description |
|---|---|---|
| `OCTW_OPENCLAW_IMAGE` | `ghcr.io/openclaw/openclaw:latest` | OpenClaw container image |
| `OCTW_OPENCLAW_DIGEST` | — | Pin image by digest (recommended for production) |

## Networking

| Variable | Default | Description |
|---|---|---|
| `OCTW_EDGE_LISTEN_HOST` | `0.0.0.0` | Edge proxy listen address |
| `OCTW_EDGE_LISTEN_PORT` | `8443` | Edge proxy listen port |
| `OCTW_EDGE_DOMAIN` | `octw.example.com` | Domain used for building tenant URLs |
| `OCTW_WEBCHAT_PORT` | `18790` | Port for OpenClaw webchat inside tenant containers |

## Tenant Defaults

| Variable | Default | Description |
|---|---|---|
| `OCTW_TENANT_BASE_DIR` | `/var/lib/octw/tenants` | Base directory for tenant state and workspace volumes |
| `OCTW_DEFAULT_MEM_LIMIT` | `1536m` | Default memory limit per tenant container |
| `OCTW_DEFAULT_CPU_QUOTA` | `100000` | CPU quota in microseconds per period |
| `OCTW_DEFAULT_CPU_PERIOD` | `100000` | CPU period in microseconds |
| `OCTW_DEFAULT_PIDS_LIMIT` | `512` | Maximum PIDs per tenant container |

## Hibernation

| Variable | Default | Description |
|---|---|---|
| `OCTW_IDLE_PAUSE_SECONDS` | `1800` | Pause container after 30 minutes of inactivity |
| `OCTW_IDLE_STOP_SECONDS` | `28800` | Stop container after 8 hours of inactivity |
