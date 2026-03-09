# API Reference

Base operator API URL: `http://localhost:8000/api/v1`

There are now two auth modes:

- operator and CLI endpoints use OCTW bearer tokens
- browser app endpoints under `/api/v1/app/*` are expected to sit behind `octw-proxy` and OIDC

## Browser App Routes

### GET `/app`

Serves the single-page OCTW browser shell.

### GET `/app/chat`

Serves the same shell and resumes the chat view.

### GET `/api/v1/app/session`

Bootstrap endpoint for the browser app.

Behavior:

- if `octw_session` exists, returns the current user and tenant state
- otherwise, if the request came through the trusted reverse proxy, creates the local user if needed, mints `octw_session`, and returns the same payload
- otherwise returns `401`

Response:

```json
{
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "email": "user@example.com",
  "tenant": {
    "tenant_id": "44262e00-b7fc-462a-bf2e-8f7b750f4cfe",
    "slug": "u-0123456789abcdef0123",
    "status": "running",
    "verification_status": "verified",
    "verification_error": null,
    "chat_url": "https://octw.example.com/app/chat"
  }
}
```

### POST `/api/v1/app/deploy-or-resume`

Idempotent browser flow entrypoint.

Behavior:

- creates the signed-in user's single tenant if it does not exist yet
- otherwise wakes the existing tenant if it is paused or stopped
- re-runs verification if the tenant is not currently marked `verified`

Response:

```json
{
  "created": true,
  "tenant": {
    "tenant_id": "44262e00-b7fc-462a-bf2e-8f7b750f4cfe",
    "slug": "u-0123456789abcdef0123",
    "status": "running",
    "verification_status": "verified",
    "verification_error": null,
    "chat_url": "https://octw.example.com/app/chat"
  }
}
```

### WebSocket `/t/{slug}/ws`

Browser chat connections go through `octw-edge` on this path.

`octw-edge` validates the OCTW session, checks tenant membership, wakes the tenant if needed, and then proxies the WebSocket to the tenant gateway.

## Authentication Endpoints

### POST `/auth/login`

Request a development magic-link token.

```json
{ "email": "user@example.com" }
```

Response:

```json
{ "message": "Check your email for a login link", "dev_token": "..." }
```

### POST `/auth/verify`

Exchange a dev token for an OCTW bearer token and `octw_session` cookie.

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

Placeholder endpoint. Browser logout is currently expected to happen through `/oauth2/sign_out` at the ingress layer.

## Provisioning

### GET `/provision/providers`

List supported providers and whether their server-side API key is configured.

### POST `/provision`

Operator one-click provisioning flow.

Request:

```json
{
  "slug": "acme",
  "name": "Acme Corp",
  "provider": "zai",
  "secrets": {}
}
```

Response:

```json
{
  "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
  "slug": "acme",
  "status": "running",
  "provider": "zai",
  "model": "zai-coding/glm-5",
  "url": "https://octw.example.com/acme/",
  "verification_status": "verified",
  "verification_error": null
}
```

A successful response implies the config exists, the gateway is healthy, and a server-side WebSocket connection to the tenant succeeded.

## Tenant Management

### POST `/tenants`

Create tenant metadata without running the provisioning workflow.

### GET `/tenants`

List tenants visible to the caller.

### GET `/tenants/{tenantId}`

Fetch tenant details.

### PATCH `/tenants/{tenantId}`

Update mutable tenant fields such as `name`.

### DELETE `/tenants/{tenantId}`

Delete the tenant and its resources.

## Secrets

### GET `/tenants/{tenantId}/secrets`

List secret metadata. Values are never returned.

### PUT `/tenants/{tenantId}/secrets/{name}`

Create or replace a secret.

### DELETE `/tenants/{tenantId}/secrets/{name}`

Delete a secret.

### POST `/tenants/{tenantId}/secrets/rotate`

Rotate a secret value.

## Runtime Control

### GET `/tenants/{tenantId}/runtime`

Return runtime state and resource limits.

### POST `/tenants/{tenantId}/runtime/start`

Start the tenant container.

### POST `/tenants/{tenantId}/runtime/stop`

Stop and remove the tenant container.

### POST `/tenants/{tenantId}/runtime/pause`

Pause the tenant container.

### POST `/tenants/{tenantId}/runtime/wake`

Wake a paused or stopped tenant.

### GET `/tenants/{tenantId}/runtime/logs`

Return container logs.

## Internal API

Internal base URL: `http://octw-api:8000/internal/v1/tenants`

These endpoints are intended for `octw-edge` and internal automation.

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/{identifier}/ensure-running` | Wake tenant if needed |
| `GET` | `/{identifier}/access/{user_id}` | Confirm membership before proxying |
| `POST` | `/{identifier}/pause-if-idle` | Pause tenant |
| `POST` | `/{identifier}/stop-if-idle` | Stop tenant |
| `GET` | `/{identifier}/status` | Return runtime state and container IP |
