# API Reference

Base URL: `http://localhost:8000/api/v1`

All endpoints require a Bearer token except auth endpoints. Obtain a token via the login/verify flow.

## Authentication

### POST `/auth/login`

Request a magic link token.

```json
{ "email": "user@example.com" }
```

Response (202):
```json
{ "message": "Check your email for a login link", "dev_token": "..." }
```

In development, `dev_token` is returned directly. In production, the token would be sent via email.

### POST `/auth/verify`

Exchange a magic link token for a session JWT.

```json
{ "token": "<dev_token>" }
```

Response:
```json
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "user_id": "...",
  "email": "user@example.com"
}
```

### POST `/auth/logout`

Response: 204 No Content

---

## Provisioning

### GET `/provision/providers`

List available providers and whether they are configured on the server.

Response:
```json
[
  {
    "key": "zai",
    "display_name": "Z.ai GLM Coding Plan",
    "model": "zai-coding/glm-5",
    "configured": true
  }
]
```

### POST `/provision`

One-click tenant provisioning. Creates tenant, runs OpenClaw onboarding, configures webchat and model, starts container.

Request:
```json
{
  "slug": "acme",
  "name": "Acme Corp",
  "provider": "zai",
  "secrets": {}
}
```

- `slug` — DNS-safe identifier (3-50 chars, lowercase alphanumeric and hyphens)
- `name` — display name
- `provider` — one of `zai`, `moonshot`, `minimax` (default: `zai`)
- `secrets` — optional additional per-tenant secrets

Response (200):
```json
{
  "tenant_id": "550e8400-...",
  "slug": "acme",
  "status": "running",
  "provider": "zai",
  "model": "zai-coding/glm-5",
  "url": "https://octw.example.com/acme/"
}
```

Error responses:
- 400 — invalid provider or provider not configured on server
- 409 — slug already exists

---

## Tenants

### POST `/tenants`

Create a tenant without provisioning OpenClaw (use `/provision` for the full flow).

```json
{
  "slug": "acme",
  "name": "Acme Corp",
  "plan": "standard",
  "isolation_mode": "standard",
  "trusted_proxy_auth": true
}
```

Response (201):
```json
{ "tenantId": "...", "slug": "acme", "status": "stopped" }
```

### GET `/tenants`

List tenants the authenticated user belongs to.

### GET `/tenants/{tenantId}`

Get tenant details. Requires membership.

### PATCH `/tenants/{tenantId}`

Update tenant (currently supports `name`). Requires `tenant_admin` role.

### DELETE `/tenants/{tenantId}`

Delete tenant and all resources. Requires `tenant_admin` role. Response: 204.

---

## Members

### GET `/tenants/{tenantId}/members`

List tenant members and their roles.

### POST `/tenants/{tenantId}/members`

Add a member. Requires `tenant_admin` role.

```json
{ "email": "user@example.com", "role": "tenant_user" }
```

Roles: `tenant_admin`, `tenant_user`, `tenant_viewer`.

### DELETE `/tenants/{tenantId}/members/{userId}`

Remove a member. Requires `tenant_admin` role. Response: 204.

---

## Secrets

Secrets are encrypted at rest (AES-256-GCM envelope encryption). The API never returns secret values.

### GET `/tenants/{tenantId}/secrets`

List secret metadata (names, types, timestamps — never values).

### PUT `/tenants/{tenantId}/secrets/{name}`

Create or update a secret. Requires `tenant_admin` role.

```json
{
  "value": "sk-...",
  "type": "env",
  "target_env_var": "OPENAI_API_KEY"
}
```

### DELETE `/tenants/{tenantId}/secrets/{name}`

Delete a secret. Requires `tenant_admin` role. Response: 204.

### POST `/tenants/{tenantId}/secrets/rotate`

Rotate a secret (provide new value). Requires `tenant_admin` role.

```json
{ "name": "OPENAI_API_KEY", "value": "sk-new-..." }
```

---

## Runtime Control

### GET `/tenants/{tenantId}/runtime`

Get tenant runtime state, container ID, last activity, and resource limits.

```json
{
  "tenant_id": "...",
  "state": "running",
  "container_id": "abc123...",
  "last_activity_at": "2026-02-28T...",
  "limits": { "mem_limit": "1536m", "cpu_quota": 100000, "pids_limit": 512 }
}
```

States: `running`, `paused`, `stopped`, `error`, `not_found`.

### POST `/tenants/{tenantId}/runtime/start`

Start the tenant container. Requires `tenant_user` or above.

### POST `/tenants/{tenantId}/runtime/stop`

Stop and remove the tenant container. Requires `tenant_user` or above.

### POST `/tenants/{tenantId}/runtime/pause`

Pause the container (memory retained, CPU released). Requires `tenant_user` or above.

### POST `/tenants/{tenantId}/runtime/wake`

Wake a paused or stopped tenant. Requires `tenant_user` or above.

### GET `/tenants/{tenantId}/runtime/logs`

Get container logs.

Query parameters:
- `since` — Unix timestamp
- `tail` — number of lines (default 200, max 5000)

---

## Internal Endpoints

These are used by octw-edge and should be restricted to internal access (mTLS in production).

Base URL: `http://localhost:8000/internal/v1/tenants`

All endpoints accept either a UUID or slug as the `{identifier}`.

| Method | Path | Description |
|---|---|---|
| POST | `/{identifier}/ensure-running` | Wake tenant if not running |
| POST | `/{identifier}/pause-if-idle` | Pause tenant |
| POST | `/{identifier}/stop-if-idle` | Stop tenant |
| GET | `/{identifier}/status` | Get container state and IP |

### GET `/{identifier}/status` Response

```json
{ "state": "running", "ip": "172.18.0.5" }
```

---

## Metrics

### GET `/metrics`

Prometheus-format metrics endpoint. No authentication required.

```bash
curl http://localhost:8000/metrics
```

Available metrics:

| Metric | Type | Description |
|---|---|---|
| `octw_tenant_container_starts_total` | Counter | Tenant container start events (label: `tenant_id`) |
| `octw_tenant_container_stops_total` | Counter | Tenant container stop events (label: `tenant_id`) |
| `octw_tenant_wake_events_total` | Counter | Wake-on-request events (label: `tenant_id`) |
| `octw_tenant_pause_events_total` | Counter | Tenant pause events (label: `tenant_id`) |
| `octw_active_tenants` | Gauge | Currently running tenant containers |
| `octw_proxy_request_duration_seconds` | Histogram | Edge proxy request duration (labels: `tenant_slug`, `method`, `status`) |
| `octw_secret_operations_total` | Counter | Secret lifecycle operations (labels: `tenant_id`, `operation`) |
| `octw_auth_failures_total` | Counter | Authentication failures (label: `reason`) |

A Prometheus scrape config is provided at `configs/prometheus.yml`.

---

## Health

### GET `/health`

Health check endpoint on octw-api. No authentication required.

```json
{ "status": "ok" }
```

### GET `/health` (octw-edge, port 8443)

Health check endpoint on octw-edge.

```json
{ "status": "ok", "service": "octw-edge" }
```
