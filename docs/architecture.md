# Architecture

## Overview

OCTW runs one OpenClaw gateway container per tenant. All tenants share a common control plane (API, database, cache, edge proxy) but are isolated at the container, network, and filesystem levels.

```
                    Internet / VPN / Tailnet
                             |
                             v
                    +-----------------+
                    |    octw-edge    |
                    |  /<slug>/...    |
                    | Auth + Wake-on  |
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

## Components

| Component | Technology | Role |
|---|---|---|
| **octw-api** | FastAPI (Python) | REST API for provisioning, tenant CRUD, RBAC, secrets, runtime control |
| **octw-edge** | FastAPI + httpx | Reverse proxy: path-based tenant routing (`/<slug>/`), JWT auth, wake-on-request |
| **octw-db** | PostgreSQL 16 | Metadata, memberships, audit logs, encrypted secret ciphertext, tenant DEKs |
| **octw-cache** | Redis 7 | Sessions, rate limiting, orchestration locks |
| **orchestrator** | Docker SDK for Python | Container lifecycle, network creation, resource limits, init jobs |
| **vault** | cryptography (Python) | AES-256-GCM envelope encryption for secrets at rest |
| **CLI** | Click | Operator tool for tenant and secret management |

## Data Flow

### One-Click Provisioning

```
Web App
  │
  ├─► POST /api/v1/provision { slug, name, provider }
  │
  ▼
octw-api
  ├─ 1. Create tenant row in DB
  ├─ 2. Create filesystem dirs (/var/lib/octw/tenants/<id>/)
  ├─ 3. Create isolated Docker network
  ├─ 4. Run init container (openclaw onboard --non-interactive)
  │     └─ Provider API key + model injected via env vars
  ├─ 5. Patch openclaw.json (webchat, gateway bind, model config)
  ├─ 6. Start tenant container with secrets injected
  └─ 7. Return { tenant_id, slug, url, provider, model }
```

### Request Routing

```
User request: https://octw.example.com/acme/chat
  │
  ▼
octw-edge
  ├─ Extract slug "acme" from path
  ├─ Authenticate (JWT Bearer or session cookie)
  ├─ Resolve slug → tenant_id → container IP
  │   └─ If stopped/paused: call ensure-running, wait for container
  ├─ Proxy to http://<container-ip>:18789/chat
  └─ Return response
```

## Isolation Model

Each tenant container runs with:

- **Dedicated Docker network** — per-tenant bridge network, `internal=true`. No inter-tenant connectivity.
- **Dedicated volumes** — separate state and workspace directories at `/var/lib/octw/tenants/<id>/`, permissions `0700`.
- **Non-root execution** — UID 1000:1000, all Linux capabilities dropped, `no-new-privileges`.
- **Resource limits** — configurable memory (default 1.5 GB), CPU quota, PID limit (512).
- **No host port publishing** — tenant containers are not reachable from the host network; only octw-edge connects.
- **Optional hardened runtime** — gVisor (`runsc`) per tenant via `isolation_mode: hardened`.

## Idle Hibernation

To conserve host resources when running many tenants:

| Trigger | Action | Effect |
|---|---|---|
| 30 min idle | Pause container | Memory retained, CPU released |
| 8 hours idle | Stop container | Memory and CPU fully reclaimed |
| First request after stop/pause | Wake-on-request | Edge proxy triggers ensure-running, waits, then proxies |

Activity is defined as HTTP/WS traffic through octw-edge to the tenant.

## Database Schema

Key tables:

- **tenants** — id, slug, name, plan, status, provider, resource_limits, container_id, network_id
- **users** — id, email
- **memberships** — tenant_id, user_id, role (tenant_admin / tenant_user / tenant_viewer)
- **secrets** — tenant_id, name, ciphertext, nonce, algorithm, key_version, target_env_var
- **tenant_deks** — tenant_id, encrypted_dek, dek_nonce, kek_version
- **audit_events** — tenant_id, user_id, action, detail, timestamp
- **image_pins** — image_ref, version, digest, is_default
