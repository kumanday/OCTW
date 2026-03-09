# Security

## Trust Boundaries

OCTW now has three distinct auth boundaries:

1. `octw-proxy` plus `octw-oidc` authenticate the browser user with OIDC
2. `octw-api` trusts the forwarded user header only from configured proxy IPs and converts it into the local `octw_session` cookie
3. each tenant OpenClaw gateway trusts only `octw-edge` via OpenClaw `trusted-proxy` mode

That split avoids device pairing, Tailscale login, and dangerous gateway auth bypasses for end users.

## Public Ingress

Public browser traffic terminates at `octw-proxy` over HTTPS.

- `octw-proxy` uses Nginx `auth_request` against `octw-oidc`
- `octw-oidc` stores its own login session in a secure cookie
- Nginx forwards the authenticated email as `X-Forwarded-Email` to OCTW app endpoints
- `octw-api` accepts that header only when `OCTW_TRUSTED_PROXY_ENABLED=true` and the caller IP matches `OCTW_TRUSTED_PROXY_IPS`

The browser never receives raw tenant credentials and never connects directly to tenant container IPs.

## OCTW Browser Session

After a successful OIDC-authenticated request, `octw-api` creates `octw_session`:

- signed with `OCTW_JWT_SECRET`
- `HttpOnly`
- `SameSite=Lax`
- `Secure` when `OCTW_PUBLIC_BASE_URL` is HTTPS

`octw-edge` uses that cookie for both HTTP proxying and the `/t/{slug}/ws` WebSocket path.

## Tenant Gateway Auth

When OCTW configures a tenant, it rewrites the OpenClaw gateway auth section to:

- `gateway.auth.mode = "trusted-proxy"`
- `gateway.auth.trustedProxy.userHeader = "x-octw-user-email"`
- `gateway.trustedProxies = [<octw-edge IP>]`
- `gateway.controlUi.allowedOrigins = [OCTW_PUBLIC_BASE_URL]`

OCTW also removes dangerous fallback controls such as insecure auth and device-auth disable flags.

## Edge Proxy Controls

`octw-edge` now enforces all of the following before proxying to a tenant:

- validates the OCTW bearer token or `octw_session` cookie
- checks tenant membership via the internal API
- wakes paused or stopped tenants on demand
- strips user-supplied forwarded identity headers and injects its own `x-octw-user-id` and `x-octw-user-email`
- proxies both HTTP and WebSocket traffic over private Docker networks only

## Secret Handling

Secrets still use envelope encryption:

- KEK from `OCTW_KEK` or `OCTW_KEK_PATH`
- one DEK per tenant in the database
- AES-256-GCM for stored ciphertext
- runtime injection into container environment variables only

Provider API keys remain host-level shared secrets. Per-tenant secrets remain encrypted in the database and are never returned by the API.

## Container Isolation

Each tenant still gets:

- a dedicated Docker bridge network
- dedicated tenant directories under `/var/lib/octw/tenants/<tenant-id>/`
- no published host ports
- non-root execution and dropped Linux capabilities
- resource limits and idle pause/stop enforcement

`octw-edge` is the only control-plane container attached to tenant networks.

## Operational Guidance

- Keep `octw-api` and `octw-edge` on localhost-only bindings.
- Use a real TLS certificate in `configs/certs/` for production.
- Do not enable OpenClaw insecure auth fallbacks to make browser login easier. The trusted-proxy path replaces that need.
- If you use Google Group checks in `oauth2-proxy`, treat the Admin SDK service-account JSON under `configs/oauth2-proxy/credentials/` as a production secret.
