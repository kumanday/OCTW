# OCTW — OpenClaw (multi-)Tenant Wrapper

OCTW is a multi-tenant abstraction layer that provisions and operates multiple independent [OpenClaw](https://github.com/openclaw/openclaw) installations on a single host VM with strong isolation, encrypted secret handling, and predictable performance.

**Key principle:** OCTW uses the upstream OpenClaw container image without forking. Each tenant gets its own OpenClaw gateway process, network, filesystem, and credentials — following OpenClaw's own security guidance of separating trust boundaries with separate gateways.

## Functional Overview

### What OCTW Does

- **Tenant provisioning** — allocate a tenant with a stable ID and DNS-safe slug, create isolated runtime resources (container, network, volumes), and initialize OpenClaw state.
- **Tenant lifecycle** — start, stop, pause, and wake-on-request. Idle tenants are automatically paused after 30 minutes and stopped after 8 hours to reclaim host resources.
- **Secure secret storage** — all tenant secrets (provider API keys, channel tokens) are encrypted at rest using AES-256-GCM envelope encryption and injected into containers via environment variables at startup. Secrets are never written to config files.
- **Multi-tenant API** — a REST API (`/api/v1`) for tenant management, RBAC membership, secret lifecycle, and runtime control.
- **Edge proxy** — a reverse proxy that terminates TLS, authenticates users, routes to the correct tenant by subdomain or path, and wakes sleeping tenants on first request.
- **RBAC** — role-based access control with `tenant_admin`, `tenant_user`, and `tenant_viewer` roles enforced on every API and proxy request.
- **Audit logging** — all sensitive actions (tenant create/delete, secret set/rotate, container start/stop, membership changes) are recorded with tenant and actor context.
- **Backup and restore** — per-tenant filesystem backup and restore tooling.
- **Observability** — Prometheus metrics with `tenant_id` labels for container health, proxy latency, wake events, and secret operations.

### What OCTW Does Not Do

- Modify or fork OpenClaw source code.
- Treat a single OpenClaw gateway as a multi-tenant security boundary.
- Replace the OpenClaw Control UI (tenants access it directly through the proxy).

## Architecture

```
                    Internet / VPN / Tailnet
                             |
                             v
                    +-----------------+
                    |    octw-edge    |
                    | TLS + Auth + WoR|
                    +--------+--------+
                             |
               +-------------+--------------+
               |                            |
               v                            v
    +--------------------+        +--------------------+
    | tenant net: T1     |        | tenant net: T2     |
    | +---------------+  |        | +---------------+  |
    | | openclaw T1   |  |        | | openclaw T2   |  |
    | | port 18789    |  |        | | port 18789    |  |
    | +---------------+  |        | +---------------+  |
    +--------------------+        +--------------------+

Control plane (host internal):
+----------+   +---------+   +-------+
| octw-api |---| octw-db |---| redis |
+----------+   +---------+   +-------+
     |
     v
+----------------+
| orchestrator   |
| (Docker API)   |
+----------------+
```

### Components

| Component | Role |
|---|---|
| **octw-api** | FastAPI REST API for tenant management, RBAC, secrets, and runtime control |
| **octw-edge** | Reverse proxy with tenant routing (subdomain and path), JWT auth, wake-on-request |
| **octw-db** | PostgreSQL for metadata, memberships, audit logs, and encrypted secret storage |
| **octw-cache** | Redis for sessions, rate limiting, and orchestration locks |
| **orchestrator** | Docker API wrapper for container lifecycle, network isolation, and resource limits |
| **vault** | Envelope encryption service (KEK → per-tenant DEK → secret values) |
| **CLI** | Operator command-line tool for tenant and secret management |

### Isolation Model

Each tenant container runs with:

- **Dedicated Docker network** — no inter-tenant connectivity by default
- **Dedicated volumes** — separate state and workspace directories with `0700` permissions
- **Non-root execution** — UID 1000, all Linux capabilities dropped, `no-new-privileges`
- **Resource limits** — configurable memory (default 1.5 GB), CPU quota, PID limit (512)
- **No host port publishing** — only the edge proxy can reach tenant gateways
- **Optional hardened runtime** — gVisor (`runsc`) support per tenant

### Secret Strategy

```
Master KEK (file or env, outside DB)
  └─► encrypts per-tenant DEK (stored in DB as ciphertext)
        └─► encrypts each secret value (AES-256-GCM, unique nonce)
```

Secrets are decrypted only when starting a tenant and injected as environment variables. OpenClaw `SecretRef` is preferred over `${VAR}` substitution to avoid config-file leakage.

## Getting Started

### Prerequisites

- Docker (with compose plugin)
- [uv](https://docs.astral.sh/uv/)

### Quick Start (Docker Compose)

This is the recommended way to run OCTW. A single command brings up the full stack: database, cache, API server, and edge proxy.

```bash
git clone https://github.com/kumanday/OCTW.git && cd OCTW

# Prepare host directories and master encryption key
sudo mkdir -p /var/lib/octw /etc/octw
sudo chown $USER /var/lib/octw
sudo python3 -c "import os; open('/etc/octw/master.key','wb').write(os.urandom(32))"
sudo chown $USER /etc/octw/master.key
sudo chmod 600 /etc/octw/master.key

# Generate secrets and launch
export OCTW_KEK=$(python3 -c "import os; open('/etc/octw/master.key','rb').read().hex()" | tr -d '[:space:]')
export OCTW_JWT_SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
docker compose up -d
```

This starts:

| Service | Port | Description |
|---|---|---|
| **octw-db** | 5432 | PostgreSQL for metadata, RBAC, audit logs, encrypted secrets |
| **octw-cache** | 6379 | Redis for sessions and orchestration locks |
| **octw-api** | 8000 | REST API for tenant management and runtime control |
| **octw-edge** | 8443 | Reverse proxy with tenant routing and wake-on-request |

### CLI Operations

Install the project locally, then use `uv run octw` to manage tenants:

```bash
uv sync

# Create a tenant
uv run octw tenant create --slug acme --name "Acme Corp"

# List tenants
uv run octw tenant list

# Start a tenant
uv run octw tenant start <tenant-id>

# Check tenant status
uv run octw tenant status <tenant-id>

# Pause / stop a tenant
uv run octw tenant pause <tenant-id>
uv run octw tenant stop <tenant-id>

# Manage secrets
uv run octw secret set <tenant-id> --name OPENAI_API_KEY --env-var OPENAI_API_KEY
uv run octw secret list <tenant-id>

# Delete a tenant
uv run octw tenant delete <tenant-id> --yes
```

### API Endpoints

All endpoints are under `/api/v1` and require a Bearer token (except auth).

| Method | Path | Description |
|---|---|---|
| POST | `/auth/login` | Request magic link |
| POST | `/auth/verify` | Exchange token for session |
| POST | `/tenants` | Create tenant |
| GET | `/tenants` | List user's tenants |
| GET | `/tenants/{id}` | Get tenant details |
| DELETE | `/tenants/{id}` | Delete tenant |
| POST | `/tenants/{id}/members` | Add member |
| PUT | `/tenants/{id}/secrets/{name}` | Set secret |
| GET | `/tenants/{id}/secrets` | List secret metadata |
| POST | `/tenants/{id}/runtime/start` | Start tenant |
| POST | `/tenants/{id}/runtime/stop` | Stop tenant |
| POST | `/tenants/{id}/runtime/pause` | Pause tenant |
| POST | `/tenants/{id}/runtime/wake` | Wake tenant |
| GET | `/tenants/{id}/runtime/logs` | Get container logs |

### Development Setup

To run services individually outside Docker Compose (e.g. for debugging):

```bash
uv sync

# Start only infrastructure
docker compose up -d octw-db octw-cache

# Run the API server
uv run octw server api

# In another terminal, run the edge proxy
uv run octw server edge
```

### Running Tests

```bash
uv run pytest tests/ -v
```

## Configuration

All settings are controlled via environment variables with the `OCTW_` prefix:

| Variable | Default | Description |
|---|---|---|
| `OCTW_DB_URL` | `postgresql+asyncpg://octw:octw@localhost:5432/octw` | Database connection |
| `OCTW_REDIS_URL` | `redis://localhost:6379/0` | Redis connection |
| `OCTW_KEK` | — | Master encryption key (hex, 32 bytes) |
| `OCTW_KEK_PATH` | `/etc/octw/master.key` | Path to KEK file (alternative to env) |
| `OCTW_JWT_SECRET` | — | JWT signing secret |
| `OCTW_OPENCLAW_IMAGE` | `ghcr.io/openclaw/openclaw:latest` | OpenClaw image |
| `OCTW_OPENCLAW_DIGEST` | — | Pin image by digest |
| `OCTW_EDGE_DOMAIN` | `octw.example.com` | Domain for subdomain routing |
| `OCTW_DEFAULT_MEM_LIMIT` | `1536m` | Default tenant memory limit |
| `OCTW_DEFAULT_PIDS_LIMIT` | `512` | Default tenant PID limit |
| `OCTW_IDLE_PAUSE_SECONDS` | `1800` | Pause after inactivity (30 min) |
| `OCTW_IDLE_STOP_SECONDS` | `28800` | Stop after inactivity (8 hours) |

## License

See [LICENSE](LICENSE).
