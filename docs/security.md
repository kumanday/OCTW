# Security

## Threat Model

OCTW assumes tenants are mutually untrusted. Tenants may be adversarial through prompt injection, may install compromised skills or MCP servers, and should never be able to access another tenant's data or network.

### Primary Threats

| Threat | Mitigation |
|---|---|
| Cross-tenant data access | Per-tenant volumes with `0700` permissions, separate Docker networks |
| Cross-tenant network movement | Dedicated bridge network per tenant (`internal=true`), no inter-tenant connectivity |
| Host compromise via container breakout | Non-root execution, all capabilities dropped, `no-new-privileges`, optional gVisor |
| Secret leakage to disk | AES-256-GCM encryption at rest, env var injection at runtime, SecretRef in OpenClaw config |
| Ingress auth bypass | JWT validation at edge proxy, forwarded header sanitization |

## Secret Strategy

### Envelope Encryption

```
Master KEK (file at /etc/octw/master.key or OCTW_KEK env var)
  │
  └─► encrypts per-tenant DEK (stored in DB as ciphertext)
        │
        └─► encrypts each secret value (AES-256-GCM, unique nonce per value)
```

- **KEK** — 32-byte AES key, stored outside the database (file or env var). Single point of trust.
- **DEK** — one random 32-byte key per tenant, encrypted by KEK and stored in `tenant_deks` table.
- **Secret values** — encrypted by the tenant's DEK using AES-256-GCM with a unique 12-byte nonce.

### Runtime Secret Delivery

1. Secrets are decrypted **only** when starting or waking a tenant container.
2. Decrypted values are injected as **environment variables** into the container process.
3. Secrets are **never written** to the tenant's state volume or config files by OCTW.
4. OpenClaw config uses **SecretRef** (`{"$ref": "env:ZAI_API_KEY"}`) to reference env vars without embedding values.

### Secret Categories

| Category | Example | Storage |
|---|---|---|
| Provider API keys (shared) | `ZAI_API_KEY` | Server config (`OCTW_ZAI_API_KEY`), injected at runtime |
| Per-tenant secrets | Channel tokens, custom keys | Encrypted in DB, injected at runtime |
| Platform secrets | JWT secret, DB password | Server environment only |
| Infrastructure secrets | KEK, TLS keys | File or env, never in DB |

## Container Hardening

Every tenant container runs with:

```yaml
user: "1000:1000"
cap_drop: ["ALL"]
security_opt: ["no-new-privileges:true"]
pids_limit: 512
mem_limit: "1536m"
cpu_quota: 100000
```

Additionally:
- No Docker socket mount
- No host port publishing
- No privileged mode
- Restart policy: `unless-stopped`
- Health check: `curl -sf http://localhost:18789/health` every 30s

### Isolation Modes

| Mode | Runtime | Description |
|---|---|---|
| `standard` | Default Docker (runc) | seccomp + AppArmor profiles |
| `hardened` | gVisor (runsc) | User-space kernel, stronger syscall isolation |

Set per tenant at creation: `"isolation_mode": "hardened"`.

## Network Isolation

- Each tenant gets a dedicated Docker bridge network (`octw_tenant_<id>`).
- Networks are created with `internal=true` — no outbound internet access by default.
- Only the edge proxy (octw-edge) is connected to tenant networks.
- Tenant containers never join the default bridge network.
- No ports are published to the host.

## Authentication and Authorization

### Edge Proxy (octw-edge)

- Authenticates every request via JWT Bearer token or `octw_session` cookie.
- Sanitizes forwarded headers (`X-Forwarded-For` is overwritten with client IP).
- Injects `x-octw-tenant-slug`, `x-octw-user-id`, `x-octw-user-email` headers.

### API (octw-api)

- JWT-based auth on all endpoints (except `/auth/login` and `/auth/verify`).
- RBAC: every tenant operation checks membership and role.
- Roles: `tenant_admin` > `tenant_user` > `tenant_viewer`.

## Audit Logging

All sensitive actions emit audit events stored in the `audit_events` table:

- Tenant create / delete
- Secret set / rotate / delete
- Container start / stop / pause / wake
- Member add / remove
- Route mapping changes
- Backup / restore

Each event includes `tenant_id`, `user_id`, action type, and detail metadata.
