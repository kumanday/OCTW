# Configuration

OCTW reads settings from environment variables with the `OCTW_` prefix. Start with [`.env.example`](/Users/magos/dev/kumanday/OCTW/.env.example) and adjust only what you need.

## Core Control Plane

| Variable | Default | Description |
|---|---|---|
| `OCTW_DB_URL` | `postgresql+asyncpg://octw:octw@localhost:5432/octw` | PostgreSQL connection string |
| `OCTW_REDIS_URL` | `redis://localhost:6379/0` | Redis connection string |
| `OCTW_LOG_LEVEL` | `INFO` | API and edge log level |
| `OCTW_PUBLIC_BASE_URL` | `https://octw.example.com` | Public HTTPS origin used by the browser app and Control UI origin checks |
| `OCTW_EDGE_DOMAIN` | `octw.example.com` | Hostname used when building legacy tenant URLs |
| `OCTW_EDGE_LISTEN_HOST` | `0.0.0.0` | Bind host for the standalone edge server |
| `OCTW_EDGE_LISTEN_PORT` | `8443` | Bind port for the standalone edge server |
| `OCTW_API_INTERNAL_BASE_URL` | `http://octw-api:8000` | Internal API base URL used by `octw-edge` |
| `OCTW_EDGE_CONTAINER_NAME` | `octw-edge` | Docker container name trusted by tenant networks |

## Secrets and Session Signing

| Variable | Default | Description |
|---|---|---|
| `OCTW_KEK` | none | Hex-encoded 32-byte master key for envelope encryption |
| `OCTW_KEK_PATH` | `/etc/octw/master.key` | Fallback path for the KEK if `OCTW_KEK` is unset |
| `OCTW_JWT_SECRET` | `CHANGE-ME-IN-PRODUCTION` | Signing key for API bearer tokens and the `octw_session` cookie |
| `OCTW_JWT_ALGORITHM` | `HS256` | JWT algorithm |
| `OCTW_JWT_EXPIRE_MINUTES` | `60` | Expiry for OCTW bearer tokens and `octw_session` |

## Shared Provider API Keys

At least one provider key must be present for one-click provisioning.

| Variable | Provider | Model |
|---|---|---|
| `OCTW_ZAI_API_KEY` | Z.ai | `zai/glm-5` |
| `OCTW_MOONSHOT_API_KEY` | Moonshot AI | `kimi-coding/k2p5` |
| `OCTW_MINIMAX_API_KEY` | MiniMax | `minimax-coding/MiniMax-M2.5` |
| `OCTW_DEFAULT_PROVIDER` | `zai` | Provider key used by `/api/v1/app/deploy-or-resume` |

## OpenClaw Runtime

| Variable | Default | Description |
|---|---|---|
| `OCTW_OPENCLAW_IMAGE` | `ghcr.io/openclaw/openclaw:latest` | OpenClaw image used for tenants |
| `OCTW_OPENCLAW_DIGEST` | none | Optional image digest pin |
| `OCTW_WEBCHAT_PORT` | `18790` | WebChat port enabled during onboarding |
| `OCTW_TENANT_BASE_DIR` | `/var/lib/octw/tenants` | Base directory for tenant state and workspace data |

## Resource Limits and Idle Control

| Variable | Default | Description |
|---|---|---|
| `OCTW_DEFAULT_MEM_LIMIT` | `1536m` | Default container memory limit |
| `OCTW_DEFAULT_CPU_QUOTA` | `100000` | Default CPU quota in microseconds |
| `OCTW_DEFAULT_CPU_PERIOD` | `100000` | CPU period in microseconds |
| `OCTW_DEFAULT_PIDS_LIMIT` | `512` | Default PID limit per tenant |
| `OCTW_IDLE_PAUSE_SECONDS` | `1800` | Idle pause threshold |
| `OCTW_IDLE_STOP_SECONDS` | `28800` | Idle stop threshold |

## Browser Auth and Trusted Proxy

These settings control the browser-first `/app` flow.

| Variable | Default | Description |
|---|---|---|
| `OCTW_TRUSTED_PROXY_ENABLED` | `false` | Allow the API to bootstrap browser sessions from a forwarded identity header |
| `OCTW_TRUSTED_PROXY_USER_HEADER` | `X-Forwarded-Email` | Header that carries the authenticated user email from Nginx/oauth2-proxy |
| `OCTW_TRUSTED_PROXY_IPS` | empty | Comma-separated list of IPs or CIDRs allowed to send that header |

`OCTW_TRUSTED_PROXY_ENABLED` should only be enabled when the API is behind `octw-proxy` or another trusted reverse proxy that injects the configured header.

## Containerized OIDC Ingress

`docker-compose.yml` now runs `oauth2-proxy` inside the `octw-oidc` service. The service loads [configs/oauth2-proxy/oauth2-proxy.cfg](/Users/magos/dev/kumanday/OCTW/configs/oauth2-proxy/oauth2-proxy.cfg) and accepts provider-specific overrides from the environment.

| Variable | Default | Description |
|---|---|---|
| `OCTW_SERVER_NAME` | `octw.example.com` | Nginx `server_name` and certificate CN fallback |
| `OCTW_OIDC_CONFIG_FILE` | `oauth2-proxy.cfg` | Config file under `configs/oauth2-proxy/` loaded by `octw-oidc` |
| `OCTW_OIDC_PROVIDER` | `oidc` | `oauth2-proxy` provider, typically `oidc`, `keycloak-oidc`, or `google` |
| `OCTW_OIDC_ISSUER_URL` | empty | Required for generic OIDC and Keycloak providers |
| `OCTW_OIDC_CLIENT_ID` | none | OIDC client ID |
| `OCTW_OIDC_CLIENT_SECRET` | none | OIDC client secret |
| `OCTW_OIDC_COOKIE_SECRET` | none | 16/24/32-byte `oauth2-proxy` cookie secret, raw or base64-encoded |
| `OCTW_OIDC_EMAIL_DOMAINS` | `*` | Allowed email domains passed to `oauth2-proxy` |
| `OCTW_OIDC_WHITELIST_DOMAINS` | empty | Redirect domains allowed by `oauth2-proxy` |

Provider-specific references:

- Keycloak: [configs/oauth2-proxy/keycloak.example.cfg](/Users/magos/dev/kumanday/OCTW/configs/oauth2-proxy/keycloak.example.cfg)
- Google Workspace: [configs/oauth2-proxy/google-workspace.example.cfg](/Users/magos/dev/kumanday/OCTW/configs/oauth2-proxy/google-workspace.example.cfg)

For Google Group enforcement, mount an Admin SDK service-account JSON at `configs/oauth2-proxy/credentials/google-admin-sdk.json`.
