# OpenClaw Multi-Tenant Wrapper (OCTW) Specification

Version: 0.1 (implementation-ready)
Last updated: 2026-02-28
Status: Draft for build

## 1. Purpose

Build a multi-tenant abstraction layer (a wrapper) that provisions and operates multiple independent OpenClaw installations on the same host VM, with strong isolation, secure secret handling, and predictable performance.

Key requirement: OCTW must use the upstream OpenClaw repository and container image without forking OpenClaw.

This specification is written so an autonomous engineering agent can implement OCTW end to end.

## 2. Background and constraints

OpenClaw is designed as a "personal, local-first gateway" and explicitly warns that it is not a hostile multi-tenant security boundary. The security guidance recommends separating trust boundaries with separate gateways and credentials, ideally on separate OS users or separate hosts. OCTW follows that guidance by running one OpenClaw Gateway per tenant, not by multiplexing tenants inside a single gateway process.

OpenClaw also enforces strict configuration schema validation. Invalid or unknown configuration keys can prevent the gateway from starting. OCTW must treat OpenClaw configuration as a versioned contract.

OpenClaw provides first-class secret references (SecretRef) with an eager, in-memory runtime snapshot and fail-fast activation model. OCTW should rely on SecretRef wherever supported, and avoid patterns known to write resolved `${VAR}` secrets into config files during some config-writing commands.

Trusted-proxy auth is available in OpenClaw. OCTW can use it to place OpenClaw behind an identity-aware reverse proxy, enabling browser-based Control UI access without device pairing, but it must be configured carefully and only when the proxy is the only reachable ingress path.

## 3. Definitions

- Tenant: An isolated OpenClaw installation, including its own OpenClaw state directory, workspace, runtime container, and credentials.
- Control plane: OCTW services that manage tenants, users, secrets, policy, routing, and auditing.
- Data plane: Per-tenant OpenClaw containers plus runtime isolation primitives.
- Edge proxy: The only inbound entrypoint for tenant traffic (HTTP and WebSocket).
- Orchestrator: OCTW component that manages container lifecycle, networks, volumes, and resource limits.
- Vault: OCTW secret storage mechanism that encrypts tenant secrets at rest and provides them to the orchestrator at runtime.

## 4. Goals

### 4.1 Functional goals

1. Provision a new tenant:
   - Allocate stable tenant identifier and slug.
   - Create isolated runtime resources.
   - Initialize OpenClaw state and workspace.
   - Configure gateway auth and safe defaults.
2. Provide tenant access:
   - Secure browser access to the OpenClaw Control UI and WebChat (preferred).
   - Optional: Provide a separate OCTW UI as a façade (out of MVP scope).
3. Operate tenants:
   - Start, stop, pause, resume (wake on request).
   - Collect metrics and logs.
   - Rotate secrets and gateway access.
   - Backup and restore tenant state.
4. Share resources safely:
   - Allow a set of host-wide shared services (proxy, observability, optional local model server).
   - Provide controlled, auditable cross-tenant access only through explicit sharing mechanisms.

### 4.2 Security goals

1. Tenant isolation:
   - Prevent tenant A from reading or influencing tenant B state.
   - Prevent lateral network movement between tenants by default.
2. Secret safety:
   - No plaintext tenant secrets stored on the host in world-readable locations.
   - Prefer "secrets in memory" at runtime and "encrypted at rest" in storage.
3. Least privilege:
   - OpenClaw containers run as non-root with minimal Linux capabilities.
   - Orchestrator is the only component with container runtime control.
4. Auditability:
   - All sensitive actions are logged with tenant scoping.
5. Safe ingress:
   - No direct access to tenant OpenClaw ports from the public network.
   - All inbound traffic goes through a hardened edge proxy and explicit allow rules.

### 4.3 Performance goals

1. Predictable per-tenant resource limits and quotas.
2. Host stability under many idle tenants through hibernation:
   - Pause idle containers after an inactivity window.
   - Stop long-idle containers to reclaim memory.
3. Fast wake path:
   - Proxy can wake a paused/stopped tenant on the first request.
4. Efficient sharing of immutable artifacts:
   - OpenClaw image layers should be shared across tenants.
   - Optional shared caches for package registries and skill fetches.

## 5. Non-goals

1. Modifying or forking OpenClaw source code.
2. Treating a single OpenClaw gateway as a multi-tenant security boundary.
3. Providing perfect isolation against kernel-level exploits. OCTW will provide defense in depth; stronger isolation options (gVisor or Kata) are supported but depend on host capabilities.
4. Building a full-featured replacement for OpenClaw Control UI in the MVP.

## 6. Threat model

### 6.1 Assumptions

- Tenants are mutually untrusted.
- Tenants can be adversarial through prompt injection from inbound channels.
- Tenants may install skills or configure MCP servers that are malicious or compromised.
- Host operator is trusted (but mistakes happen).
- The edge proxy and control plane are exposed to authenticated users, but not to the public internet unless explicitly configured.

### 6.2 Primary threats

1. Cross-tenant data access:
   - Reading another tenant's workspace, OpenClaw state, OAuth tokens, or transcripts.
2. Cross-tenant network movement:
   - Direct TCP connections to other tenant containers or host services that are not intended to be shared.
3. Host compromise:
   - Container breakout, Docker socket exposure, privileged container misconfiguration.
4. Secret leakage:
   - Secrets stored in plaintext on disk, leaked via logs, leaked in URLs, or embedded into OpenClaw config by config-writing commands.
5. Ingress auth bypass:
   - WebSocket origin issues, reverse proxy header spoofing, misconfigured trusted proxies.

### 6.3 Security posture

OCTW uses multiple layers:

- Per-tenant: container namespace isolation, per-tenant volumes, per-tenant network, per-tenant auth and secrets injection.
- Host-wide: edge proxy access control, firewall rules, service account separation, and strong secret at-rest encryption.
- Optional hardening: gVisor runtime, SELinux/AppArmor, egress proxy with allowlists.

## 7. High-level architecture

### 7.1 Components

Control plane (host-wide):
- octw-api: REST API for tenant management, secrets, and runtime operations.
- octw-ui: Minimal admin and tenant portal UI (optional but recommended).
- octw-db: Postgres for metadata, RBAC, audit logs.
- octw-cache: Redis for sessions, rate limiting, orchestration locks.
- octw-vault: Secret encryption service or library inside octw-api (backend pluggable).
- octw-edge: Reverse proxy that terminates TLS, authenticates users, routes to the right tenant, and wakes tenants as needed.
- octw-observability: Prometheus + Grafana + Loki (optional but recommended).

Data plane (per tenant):
- openclaw-tenant: Upstream OpenClaw container, configured and run by OCTW.
- (optional) tenant-egress-proxy: Per-tenant egress policy enforcement (or shared egress proxy with per-tenant policy).
- (optional) tenant-sidecar: Helper for logs, file sync, or secret resolution.

### 7.2 ASCII diagram

```
                        Internet / VPN / Tailnet
                                 |
                                 v
                        +-----------------+
                        |     octw-edge    |
                        | TLS + AuthN/Z   |
                        | Wake-on-request |
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

Control plane network (host internal):
+------------------+   +-----------+   +-----------+
|     octw-api      |---|  octw-db   |---| octw-cache |
+------------------+   +-----------+   +-----------+
         |
         v
+------------------+
| octw-orchestrator |
| docker/containerd|
+------------------+
```

## 8. Resource model

OCTW must explicitly separate three resource classes:

### 8.1 Per-tenant isolated resources

Mandatory per tenant:
- Container: one OpenClaw gateway container per tenant.
- State volume: OpenClaw state directory (equivalent to `~/.openclaw`).
- Workspace volume: OpenClaw workspace directory.
- Tenant network: isolated container network. No inter-tenant connectivity by default.
- Tenant gateway auth config: token/password or trusted-proxy auth configuration.
- Tenant secrets: provider keys, channel tokens, and any other tenant-specific credentials.
- Tenant logs: gateway logs, proxy logs, audit events (tagged with tenant_id).

Recommended:
- Per-tenant Linux UID/GID mapping (user namespaces or rootless containers) to reduce cross-volume risk.
- Per-tenant encrypted storage for state and workspace.

### 8.2 Host-wide shared resources (securely shared)

- Edge proxy (octw-edge): shared entrypoint.
- Container runtime: shared Docker/containerd (but only orchestrator controls it).
- Image cache: shared OpenClaw image layers, pinned by digest.
- Observability stack: shared metrics/logs systems, with tenant_id as a first-class label.
- Egress proxy: shared or per-tenant enforcement proxy, with per-tenant policies.
- Optional local model service: shared inference endpoint, with per-tenant authentication and rate limits.
- Optional shared skill cache/mirror: a host service that caches skill downloads to reduce external traffic.

Security requirement: shared services must enforce tenant scoping at the API layer and must not trust client-supplied tenant_id without authentication and authorization.

### 8.3 External resources (multi-tenant on external infrastructure)

- External Postgres or object storage for backups.
- External identity provider (OIDC) for OCTW authentication.
- External LLM providers (OpenAI, Anthropic, etc), keyed per tenant.
- External logging/metrics sinks (optional).

Access model: every external request that is initiated by OCTW must include tenant identifier in one of:
- Dedicated credentials per tenant (preferred).
- Resource naming or prefix with tenant_id.
- Tenant_id claim in a signed JWT or mTLS client identity.
- Row-level security in shared databases.

## 9. Isolation design

### 9.1 Container hardening baseline (required)

For each OpenClaw tenant container:
- Run as non-root (UID 1000 or tenant-specific UID).
- Drop all Linux capabilities.
- Set `no-new-privileges`.
- Disallow privileged mode.
- Do not mount Docker socket.
- Use a read-only root filesystem if compatible, with writable volumes only where required.
- Set resource limits:
  - Memory limit (hard) and memory reservation (soft).
  - CPU quota or shares.
  - PID limit.
  - Optional: I/O weight.
- Configure health checks and restart policy.

### 9.2 Network isolation baseline (required)

- Create a dedicated Docker network per tenant.
- Attach only:
  - The tenant OpenClaw container.
  - The shared edge proxy (or a per-tenant proxy that bridges).
- No tenant container should be on the default bridge network.
- No direct host port publishing for OpenClaw (no `-p 18789:18789` per tenant).
- Only octw-edge can reach tenant gateways.

### 9.3 Strong isolation options (recommended)

OCTW should support an "isolation mode" per tenant:

- standard: Docker, default runtime with seccomp and AppArmor.
- hardened: Docker + gVisor (`runsc`) runtime.
- strongest (optional): Kata Containers (if host supports it) or microVM based isolation.

The orchestrator must implement a runtime abstraction so a tenant can be created with a specific runtime class.

## 10. Secrets and credential strategy

### 10.1 Secret categories

A. "Provider keys" used by OpenClaw model providers and skills.
B. "Channel credentials" such as Telegram tokens, Slack tokens, or WhatsApp session artifacts.
C. "OCTW platform secrets" such as OIDC client secrets, cookie signing keys, and DB passwords.
D. "Infrastructure secrets" such as TLS private keys (if not using automated ACME).

### 10.2 Storage requirements

- OCTW must encrypt all tenant secrets at rest.
- The orchestrator must not persist plaintext tenant secrets to disk.
- Avoid embedding secrets in URLs or logs.

### 10.3 Preferred integration with OpenClaw SecretRef

OpenClaw supports SecretRef objects with an in-memory runtime snapshot and fail-fast activation. OCTW should use SecretRef for fields that support it, including:
- `models.providers.<provider>.apiKey`
- `skills.entries.<skillKey>.apiKey`
- Google Chat service account refs
- auth profile `keyRef` and `tokenRef`

OCTW should prefer SecretRef objects over `${VAR}` substitution because `${VAR}` substitution has been observed to be resolved and written into config files by some config-writing commands in some versions.

### 10.4 Handling fields without SecretRef support

For secrets that are not in OpenClaw SecretRef scope (example: some channel tokens), OCTW should prefer:
1. Environment variable fallbacks supported by the relevant OpenClaw channel integration.
2. Process environment injection at container start.
3. Avoid writing tokens into `openclaw.json` as plaintext.
4. Avoid `${VAR}` inside `openclaw.json` unless unavoidable, and gate any OpenClaw commands that might rewrite config.

### 10.5 Vault design (OCTW)

OCTW vault backend must be pluggable:

- Backend option 1 (default): Postgres table storing ciphertext blobs, encrypted with envelope encryption.
- Backend option 2: HashiCorp Vault (external).
- Backend option 3: Cloud KMS + secret manager.

#### 10.5.1 Envelope encryption (default)

- Master Key Encryption Key (KEK): stored outside DB (example: in a root-only file or injected via environment at boot, ideally backed by TPM or cloud KMS).
- Per-tenant Data Encryption Key (DEK): generated randomly and stored encrypted by KEK.
- Tenant secret values encrypted by tenant DEK using AEAD (AES-256-GCM or XChaCha20-Poly1305).
- Store:
  - ciphertext
  - nonce/iv
  - algorithm
  - key version
  - created_at, updated_at
  - metadata (provider name, last rotated timestamp)

#### 10.5.2 Runtime delivery

- octw-orchestrator requests decrypted secrets for a tenant only when starting or resuming that tenant.
- Secrets are provided over an mTLS channel from octw-api to octw-orchestrator.
- Secrets are injected into the OpenClaw container via environment variables.
- Secrets are never written into the tenant state volume by OCTW.

### 10.6 Secret rotation

OCTW must support:
- Manual rotation for each secret.
- Bulk rotation per tenant.
- Rotation event triggers container restart or `openclaw secrets reload` when supported.

## 11. Tenant provisioning lifecycle

### 11.1 Tenant identifiers

- tenant_id: UUID (primary key).
- tenant_slug: DNS-safe string for routing (example: `acme`, `lab-42`).
- tenant_status: provisioning | running | paused | stopped | error | deleting.

### 11.2 Provisioning steps (state machine)

1. Create tenant metadata in octw-db.
2. Allocate filesystem locations:
   - `/var/lib/octw/tenants/<tenant_id>/state`
   - `/var/lib/octw/tenants/<tenant_id>/workspace`
   - `/var/lib/octw/tenants/<tenant_id>/logs`
   - Ensure owner-only permissions.
3. Create tenant network:
   - `octw_tenant_<tenant_id>` (internal).
4. Initialize OpenClaw state:
   - Start a one-shot OpenClaw container (init job) with the state and workspace volumes mounted.
   - Run `openclaw onboard --non-interactive` with:
     - `--mode local`
     - `--flow quickstart` (or manual if needed)
     - `--secret-input-mode ref` for provider keys and auth profiles
     - `--accept-risk` as required by OpenClaw non-interactive mode
   - Ensure gateway bind and port are compatible with octw-edge routing (bind to lan inside tenant network, not loopback).
5. Apply OCTW baseline security config:
   - Ensure gateway auth is enabled (token or trusted-proxy).
   - Ensure DM policy uses pairing by default.
   - Ensure dangerous commands or config writes from chat are disabled unless explicitly enabled for the tenant.
6. Register routing:
   - Add route mapping tenant_slug to tenant container internal address in octw-edge dynamic config store.
7. Set tenant status to stopped (default) or running (if requested).

### 11.3 Using trusted-proxy auth (recommended for web access)

Optionally configure each tenant OpenClaw to use `gateway.auth.mode = "trusted-proxy"` so octw-edge authenticates users and passes identity in a header. This removes device pairing as the primary gate for Control UI access and avoids exposing gateway tokens in URLs.

Hard requirements if enabled:
- octw-edge must be the only reachable ingress path to the tenant gateway.
- OpenClaw `gateway.trustedProxies` must include only octw-edge IP(s) reachable inside the tenant network.
- octw-edge must overwrite and sanitize forwarded headers.

If trusted-proxy is not used, OCTW must:
- Keep OpenClaw token auth enabled.
- Ensure octw-edge does not put the token in query strings.
- Prefer header-based token propagation where possible.

## 12. Tenant operation and performance controls

### 12.1 Container states

- running: container started.
- paused: container paused (memory retained).
- stopped: container stopped (memory reclaimed).
- error: container unhealthy or crashloop.

### 12.2 Idle hibernation policy (default)

Implement a policy similar to:

- Pause after 30 minutes of inactivity.
- Stop after 4 hours paused or 8 hours inactivity.

Inactivity definition:
- No HTTP or WS traffic to tenant gateway through octw-edge.
- Optional: no outbound message activity detected (if observable).

### 12.3 Wake-on-request

octw-edge must implement:
1. Resolve tenant from request host/path.
2. Check cached tenant runtime state.
3. If tenant not running:
   - Call octw-orchestrator `ensureRunning(tenant_id)` with a short timeout.
4. Proxy request to tenant gateway.

Concurrency control:
- Use Redis lock `tenant:<id>:wake-lock` to avoid thundering herd starts.

### 12.4 Resource quotas

Per tenant defaults (configurable):
- Memory: 1.5 GB
- CPU: 1 vCPU (quota) or shares
- Disk: enforce via filesystem quota if using XFS project quota or similar
- PIDs: 512

OCTW must allow per-tenant override with operator approval.

## 13. Ingress and routing

### 13.1 Routing scheme

Preferred:
- Wildcard DNS: `<tenant_slug>.octw.example.com` routes to octw-edge.

Fallback:
- Path routing: `octw.example.com/t/<tenant_slug>/...`

OCTW must support both. Subdomain is cleaner for WebSocket origins and cookies.

### 13.2 Authentication

octw-edge must enforce authentication and authorization before proxying to tenant.

Recommended:
- OIDC login at octw-edge or octw-ui.
- Session cookie with httpOnly and secure flags.
- Optional MFA in octw-api.

Authorization:
- User must be a member of the tenant.
- Role-based access:
  - tenant_admin
  - tenant_user
  - tenant_viewer

### 13.3 Rate limiting

At octw-edge:
- Per-IP rate limits for unauthenticated requests.
- Per-user and per-tenant rate limits for authenticated requests.
- WebSocket connection limits per user and per tenant.

At octw-api:
- Per-token and per-tenant rate limits for management endpoints.

## 14. Egress control (optional but recommended)

Provide an egress enforcement mode:

- All tenant containers have outbound internet access disabled except to:
  - octw-egress-proxy
  - DNS resolver
  - Optional shared services (model server, metrics agent)

octw-egress-proxy can enforce per-tenant allowlists:
- Allowed domains for LLM providers.
- Allowed domains for skill fetch sources.
- Allowed domains for webhook callbacks and integrations.

Implementation options:
- HTTP CONNECT proxy (Envoy, Squid) + iptables to block direct outbound.
- eBPF based policy (Cilium) if available.

## 15. Host-wide shared services

### 15.1 Shared local model server (optional)

Provide `octw-model-gateway`:
- OpenAI-compatible endpoint on the host (or a GPU node).
- Per-tenant API keys issued by octw-api.
- Rate limits and quotas per tenant.

Tenants can be configured to use this endpoint as a custom provider.

### 15.2 Skill caching/mirroring (optional)

Provide `octw-skill-mirror`:
- Caches GitHub releases or repo tarballs for known skills.
- Enforces allowed sources and checksums.
- Prevents SSRF by blocking internal IP ranges.

## 16. External multi-tenant resource access

OCTW services must propagate tenant identity safely.

### 16.1 Internal tenant context propagation

- octw-edge issues a JWT for backend calls with claims:
  - `tid` (tenant_id)
  - `sub` (user_id)
  - `roles` (role list)
  - `exp`
- octw-api validates JWT and uses `tid` for scoping.

### 16.2 Database scoping

For shared Postgres:
- All tenant-owned tables include `tenant_id` UUID column.
- Enforce Row Level Security (RLS) policies based on a session setting:
  - `SET app.tenant_id = '<tenant_id>'`
- Deny queries without tenant_id set.

Global tables (no tenant_id):
- migration table, global config, node registry, etc.

### 16.3 Object storage scoping

If using S3 compatible storage:
- Store backups at `s3://octw-backups/<tenant_id>/<timestamp>/...`
- Credentials:
  - Prefer per-tenant IAM role that can access only its prefix.

### 16.4 External service patterns

For any shared external service, implement one of:

- Separate credential per tenant (best).
- Same credential but include tenant_id in:
  - request headers
  - resource names/prefixes
  - JWT claims with enforced policy on receiver side.

Never rely on an untrusted client-provided `X-Tenant-ID` header alone.

## 17. Cross-tenant sharing mechanisms (optional)

OCTW may support controlled sharing without breaking isolation.

Two safe primitives:

A. Shared resources published by OCTW:
- A group-owned MCP server endpoint managed externally.
- OCTW stores the endpoint metadata and permissions.
- Tenants opt-in to add the MCP config.

B. Peer-to-peer relay (zero-knowledge style):
- A relay server that transports encrypted payloads between tenants.
- Relay sees metadata (sender, receiver, timestamp, size) but cannot read content.
- Wake-on-request for sleeping tenants is supported via relay notification.

These features are optional and can be implemented after core multi-tenant operation.

## 18. Observability and auditing

### 18.1 Metrics (Prometheus)

Collect:
- Tenant container CPU, memory, restarts.
- Tenant request counts and latency at octw-edge.
- Wake events, pause/stop events.
- Secret rotation events.
- Auth failures and rate limit hits.

All metrics must include `tenant_id` label where applicable.

### 18.2 Logs

- octw-edge access logs: include tenant_slug and tenant_id, but never include secrets or auth tokens.
- octw-api audit logs: include actor user_id, tenant_id, action type, and diff metadata.
- openclaw container logs: stored per tenant in Loki with tenant_id label.

### 18.3 Audit events (mandatory)

OCTW must emit audit events for:
- Tenant create/delete.
- Secret set/rotate/delete.
- Container start/stop/pause/wake.
- Role membership changes.
- Route mapping changes.
- Backup and restore.

## 19. Backup and restore

### 19.1 Backup

Backup inputs:
- Tenant state directory (OpenClaw state).
- Tenant workspace.
- octw-db (metadata and vault ciphertext).
- octw-edge config (routes).

Backup constraints:
- Encrypted at rest in backup target.
- Include tenant_id in the backup path.
- Optional per-tenant retention policy.

### 19.2 Restore

Restore steps:
1. Restore octw-db metadata and secrets.
2. Restore tenant filesystem volumes.
3. Recreate tenant container and network if missing.
4. Start tenant and run `openclaw doctor` read-only checks.
5. Validate tenant health endpoint through octw-edge.

## 20. Upgrade strategy (OpenClaw dependency)

### 20.1 Pinning

OCTW must pin OpenClaw image by digest, not by mutable tag.

Store in octw-db:
- openclaw_image_ref
- openclaw_version
- openclaw_digest
- upgrade_timestamp

### 20.2 Canary and rollback

- Upgrade a canary tenant first.
- Run smoke tests:
  - Gateway starts and health check passes.
  - Control UI connects through octw-edge.
  - Secrets activate successfully.
- If failures:
  - Roll back by restarting tenant on the previous digest.
  - Restore state if config was mutated.

### 20.3 Avoid unsafe config-writing commands

Due to known issues in some OpenClaw versions where config write operations can:
- resolve `${VAR}` and persist secrets in plaintext
- write redacted placeholders into the actual config file

OCTW automation must avoid running interactive config commands (`configure`, `doctor --fix`) unless the pinned version is validated safe in CI.

Preferred:
- Use `openclaw onboard --non-interactive` for initial setup.
- Use `openclaw secrets audit` and `openclaw secrets reload` for secrets lifecycle.
- Only run `doctor` in read-only mode unless explicitly requested and backed up.

## 21. OCTW API specification

Base URL: `/api/v1`

All requests require authentication except login.

### 21.1 Auth

- POST `/auth/login`
  - Body: `{ "email": "user@example.com" }`
  - Response: 202 accepted
- POST `/auth/verify`
  - Body: `{ "token": "<magic_link_token>" }`
  - Response: `{ "session": { ... } }`
- POST `/auth/logout`
  - Response: 204

### 21.2 Tenants

- POST `/tenants`
  - Body: `{ "slug": "acme", "name": "Acme", "plan": "standard" }`
  - Response: `{ "tenantId": "...", "slug": "...", "status": "provisioning" }`
- GET `/tenants`
  - Response: list of tenants user belongs to
- GET `/tenants/{tenantId}`
- PATCH `/tenants/{tenantId}`
- DELETE `/tenants/{tenantId}`

### 21.3 Membership and RBAC

- GET `/tenants/{tenantId}/members`
- POST `/tenants/{tenantId}/members`
  - Body: `{ "email": "u@x.com", "role": "tenant_user" }`
- DELETE `/tenants/{tenantId}/members/{userId}`

### 21.4 Secrets

- GET `/tenants/{tenantId}/secrets`
  - Response: metadata only, never values
- PUT `/tenants/{tenantId}/secrets/{name}`
  - Body: `{ "value": "...", "type": "env", "targetEnvVar": "OPENAI_API_KEY" }`
- DELETE `/tenants/{tenantId}/secrets/{name}`
- POST `/tenants/{tenantId}/secrets/rotate`
  - Body: `{ "name": "OPENAI_API_KEY" }`

### 21.5 Runtime control

- GET `/tenants/{tenantId}/runtime`
  - Response: `{ state, containerId, lastActivityAt, limits }`
- POST `/tenants/{tenantId}/runtime/start`
- POST `/tenants/{tenantId}/runtime/stop`
- POST `/tenants/{tenantId}/runtime/pause`
- POST `/tenants/{tenantId}/runtime/wake`
- GET `/tenants/{tenantId}/runtime/logs?since=...`

### 21.6 Internal orchestrator API (mTLS only)

- POST `/internal/v1/tenants/{tenantId}/ensure-running`
- POST `/internal/v1/tenants/{tenantId}/pause-if-idle`
- POST `/internal/v1/tenants/{tenantId}/stop-if-idle`
- GET  `/internal/v1/tenants/{tenantId}/status`

## 22. Container specification for tenant OpenClaw

### 22.1 Base image

Use upstream OpenClaw image pinned by digest:
- `ghcr.io/openclaw/openclaw@sha256:<digest>`

### 22.2 Volumes and mounts

Bind mounts (preferred for encryption and backups):
- `/var/lib/octw/tenants/<tenant_id>/state` -> `/home/node/.openclaw`
- `/var/lib/octw/tenants/<tenant_id>/workspace` -> `/home/node/.openclaw/workspace`

### 22.3 Environment variables

At minimum:
- `OPENCLAW_GATEWAY_BIND=lan`
- `OPENCLAW_GATEWAY_PORT=18789`
- `OPENCLAW_CANVAS_PORT=18790` (if needed)
- Provider env vars (injected at start): `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, etc.
- Channel env vars where supported (example: `TELEGRAM_BOT_TOKEN`)

Avoid:
- putting secrets in `.env` files on disk unless encrypted.

### 22.4 Network

- Attach tenant container only to `octw_tenant_<id>` network.
- Do not publish ports to host.

### 22.5 Security options

- Drop all capabilities.
- `no-new-privileges=true`
- `read_only=true` if compatible.
- `pids_limit=512`
- `mem_limit` and `cpu_quota`

## 23. Implementation plan (phased)

### Phase 1: Orchestrator + tenant runtime

Deliverables:
- octw-orchestrator can:
  - create tenant network
  - create tenant directories
  - start/stop/pause containers
  - apply resource limits
- octw-cli (operator) can:
  - create tenant
  - start tenant
  - fetch status

Acceptance tests:
- Create 2 tenants, verify:
  - containers cannot ping each other
  - state and workspace directories are distinct
  - no host ports exposed for tenant gateways

### Phase 2: Control plane API + RBAC + audit

Deliverables:
- octw-api with Postgres schema and RBAC.
- audit log pipeline.
- secret vault storage (ciphertext in DB, KEK outside DB).

Acceptance tests:
- Non-member cannot access tenant routes.
- Secrets can be stored and retrieved as metadata only.

### Phase 3: Edge proxy + wake-on-request

Deliverables:
- octw-edge routes by subdomain or path.
- Auth via OIDC.
- Wake-on-request with locking.

Acceptance tests:
- Stopped tenant wakes on first request and loads Control UI.
- WebSocket works through proxy.

### Phase 4: OpenClaw integration hardening

Deliverables:
- Automated non-interactive onboarding with `--secret-input-mode ref`.
- Trusted-proxy auth configuration (optional toggle).
- Guardrails around config-writing commands.
- Egress proxy mode (optional).

Acceptance tests:
- No secrets appear in tenant `openclaw.json` or logs after provisioning.
- Secrets activation fails fast if missing and yields actionable errors.

### Phase 5: Observability + backup/restore

Deliverables:
- Prometheus metrics and dashboards.
- Loki log aggregation with tenant labels.
- Backup/restore tooling.

Acceptance tests:
- Restore a tenant from backup and verify it runs.

## 24. Acceptance criteria (final)

OCTW is considered complete when:

1. Multiple tenants can run on a single VM without forking OpenClaw.
2. Tenants have isolated:
   - filesystem state and workspace
   - gateway auth and credentials
   - network connectivity (no default cross-tenant connectivity)
3. Host-wide shared services are:
   - accessible only through authenticated, authorized paths
   - tagged and scoped by tenant_id
4. External resource access is:
   - tenant-scoped with tenant_id or per-tenant credentials
   - auditable
5. The system supports:
   - pause/stop/wake policies
   - safe upgrades with canary and rollback
   - encrypted secret storage

## 25. Reference links (upstream and related)

Upstream OpenClaw:
- https://github.com/openclaw/openclaw
- https://docs.openclaw.ai

Key docs referenced by OCTW design:
- https://docs.openclaw.ai/gateway/security
- https://docs.openclaw.ai/gateway/configuration
- https://docs.openclaw.ai/gateway/secrets
- https://docs.openclaw.ai/gateway/trusted-proxy-auth
- https://docs.openclaw.ai/cli/onboard

Existing multi-tenant approach (for comparison):
- https://github.com/jomafilms/openclaw-multitenant
