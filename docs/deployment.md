# Deployment

## Compose Topology

The recommended deployment is the provided Docker Compose stack:

| Service | Exposure | Role |
|---|---|---|
| `octw-proxy` | public `80/443` | HTTPS termination, `auth_request`, browser routing |
| `octw-oidc` | internal | `oauth2-proxy` for OIDC login/session |
| `octw-api` | `127.0.0.1:8000` | REST API and browser app |
| `octw-edge` | `127.0.0.1:8443` | Tenant HTTP and WebSocket proxy |
| `octw-db` | internal plus `5432` | PostgreSQL metadata store |
| `octw-cache` | internal plus `6379` | Redis sessions and orchestration locks |

The API and edge stay on localhost for operator access. End users only hit `octw-proxy` over HTTPS.

## Host Preparation

```bash
sudo mkdir -p /var/lib/octw /etc/octw
sudo chown "$USER" /var/lib/octw
sudo python3 -c "import os; open('/etc/octw/master.key','wb').write(os.urandom(32))"
sudo chown "$USER" /etc/octw/master.key
sudo chmod 600 /etc/octw/master.key
```

## Environment Setup

```bash
cp .env.example .env
```

Set at least:

- `OCTW_KEK`
- `OCTW_JWT_SECRET`
- `OCTW_PUBLIC_BASE_URL`
- `OCTW_SERVER_NAME`
- `OCTW_TRUSTED_PROXY_ENABLED=true`
- `OCTW_OIDC_CLIENT_ID`
- `OCTW_OIDC_CLIENT_SECRET`
- `OCTW_OIDC_COOKIE_SECRET`
- one provider API key such as `OCTW_ZAI_API_KEY`

## OIDC Provider Profiles

### Keycloak

In `.env`:

```dotenv
OCTW_OIDC_PROVIDER=keycloak-oidc
OCTW_OIDC_ISSUER_URL=https://keycloak.example.com/realms/octw
OCTW_OIDC_EMAIL_DOMAINS=example.com
OCTW_OIDC_WHITELIST_DOMAINS=.example.com
```

Use [configs/oauth2-proxy/keycloak.example.cfg](/Users/magos/dev/kumanday/OCTW/configs/oauth2-proxy/keycloak.example.cfg) as the reference for optional Keycloak group or role gates.

### Google Workspace

In `.env`:

```dotenv
OCTW_OIDC_PROVIDER=google
OCTW_OIDC_ISSUER_URL=
OCTW_OIDC_EMAIL_DOMAINS=example.com
OCTW_OIDC_WHITELIST_DOMAINS=.example.com
```

If you need Google Group enforcement:

1. Put the Admin SDK service account JSON at `configs/oauth2-proxy/credentials/google-admin-sdk.json`
2. Copy the relevant settings from [configs/oauth2-proxy/google-workspace.example.cfg](/Users/magos/dev/kumanday/OCTW/configs/oauth2-proxy/google-workspace.example.cfg) into your active oauth2-proxy config
3. Delegate domain-wide authority and grant the Admin SDK read scopes in Google Workspace

## Launch

```bash
docker compose up -d --build
```

`octw-proxy` will generate a self-signed certificate if `configs/certs/fullchain.pem` and `configs/certs/privkey.pem` are missing.

## Verification

### Container health

```bash
docker compose ps
curl http://localhost:8000/health
curl http://localhost:8443/health
curl -k https://localhost/health
```

### Browser flow

Open `https://<your-domain>/app`.

The first successful visit should:

1. redirect through your OIDC provider
2. return to OCTW with a valid `oauth2-proxy` session
3. mint an `octw_session` cookie from the trusted forwarded email header
4. create or resume the single user-owned tenant
5. land on `/app/chat`

### Provision verification

A successful `POST /api/v1/provision` or `POST /api/v1/app/deploy-or-resume` now implies:

- `openclaw.json` exists after onboarding
- the tenant container started
- the gateway health check succeeded
- a server-side WebSocket handshake to the tenant gateway succeeded

If verification fails, OCTW stores the failure and returns an error instead of pretending the tenant is ready.

## Logs

```bash
docker compose logs -f octw-proxy
docker compose logs -f octw-oidc
docker compose logs -f octw-api
docker compose logs -f octw-edge
```

## Rebuild After Code Changes

```bash
docker compose up -d --build
```

## Reset

```bash
docker compose down -v
sudo rm -rf /var/lib/octw/tenants/*
```

## Production Notes

- Replace the generated certificate under `configs/certs/` with a real certificate before exposing the stack broadly.
- Keep `octw-api` and `octw-edge` bound to localhost. The public entrypoint should stay `octw-proxy` only.
- The default Postgres and Redis containers are adequate for development and small-scale testing. For production, move them to managed services and update `OCTW_DB_URL` and `OCTW_REDIS_URL`.
- Pin `OCTW_OPENCLAW_DIGEST` if you need deterministic tenant image rollouts.
