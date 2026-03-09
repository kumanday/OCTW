# OCTW — OpenClaw Tenant Wrapper

OCTW provisions and operates multiple isolated [OpenClaw](https://github.com/openclaw/openclaw) installations on one host. This branch adds a browser-first app flow: reverse-proxy OIDC login, one-click tenant deployment, verified readiness, wake-on-resume, and a minimal OCTW-hosted chat UI.

## Quick Start

### Prerequisites

- Docker Engine with the Compose plugin
- [uv](https://docs.astral.sh/uv/) for local development and tests
- At least one supported model provider API key
- A public DNS name that points to the VM
- OIDC client credentials for your IdP

### 1. Prepare the host

```bash
git clone https://github.com/kumanday/OCTW.git
cd OCTW

sudo mkdir -p /var/lib/octw /etc/octw
sudo chown "$USER" /var/lib/octw
sudo python3 -c "import os; open('/etc/octw/master.key','wb').write(os.urandom(32))"
sudo chown "$USER" /etc/octw/master.key
sudo chmod 600 /etc/octw/master.key
```

### 2. Create `.env`

```bash
cp .env.example .env
```

Fill in these values at minimum:

- `OCTW_KEK`
- `OCTW_JWT_SECRET`
- `OCTW_PUBLIC_BASE_URL`
- `OCTW_SERVER_NAME`
- `OCTW_TRUSTED_PROXY_ENABLED=true`
- one or more provider API keys such as `OCTW_ZAI_API_KEY`
- `OCTW_OIDC_CLIENT_ID`
- `OCTW_OIDC_CLIENT_SECRET`
- `OCTW_OIDC_COOKIE_SECRET`

Useful generators:

```bash
python3 -c "import os; print(os.urandom(32).hex())"
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
python3 -c "import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode().rstrip('='))"
```

### 3. Pick an OIDC provider profile

The stack now includes both public ingress and OIDC inside Docker:

- `octw-proxy` terminates HTTPS and routes requests
- `octw-oidc` runs `oauth2-proxy`

Base oauth2-proxy settings live in [configs/oauth2-proxy/oauth2-proxy.cfg](/Users/magos/dev/kumanday/OCTW/configs/oauth2-proxy/oauth2-proxy.cfg).

Provider examples:

- Keycloak: [configs/oauth2-proxy/keycloak.example.cfg](/Users/magos/dev/kumanday/OCTW/configs/oauth2-proxy/keycloak.example.cfg)
- Google Workspace: [configs/oauth2-proxy/google-workspace.example.cfg](/Users/magos/dev/kumanday/OCTW/configs/oauth2-proxy/google-workspace.example.cfg)

Typical Keycloak settings in `.env`:

```dotenv
OCTW_OIDC_PROVIDER=keycloak-oidc
OCTW_OIDC_ISSUER_URL=https://keycloak.example.com/realms/octw
OCTW_OIDC_EMAIL_DOMAINS=example.com
OCTW_OIDC_WHITELIST_DOMAINS=.example.com
```

Typical Google Workspace settings in `.env`:

```dotenv
OCTW_OIDC_PROVIDER=google
OCTW_OIDC_ISSUER_URL=
OCTW_OIDC_EMAIL_DOMAINS=example.com
OCTW_OIDC_WHITELIST_DOMAINS=.example.com
```

If you want Google Group checks, place the Admin SDK service account JSON at `configs/oauth2-proxy/credentials/google-admin-sdk.json` and copy the relevant settings from the Google example config.

### 4. Launch the stack

```bash
docker compose up -d --build
```

This starts six services:

| Service | Port | Purpose |
|---|---|---|
| `octw-proxy` | `80`, `443` | Public HTTPS ingress and routing |
| `octw-oidc` | internal | `oauth2-proxy` for OIDC login/session |
| `octw-api` | `127.0.0.1:8000` | API, browser app, provisioning workflow |
| `octw-edge` | `127.0.0.1:8443` | Auth-aware tenant HTTP and WebSocket proxy |
| `octw-db` | `5432` | PostgreSQL metadata store |
| `octw-cache` | `6379` | Redis sessions and locks |

If `configs/certs/fullchain.pem` and `configs/certs/privkey.pem` do not exist, `octw-proxy` generates an ephemeral self-signed certificate inside the container for bootstrap only. Mount real cert files in `configs/certs/` for production.

### 5. Open the browser app

Open:

```text
https://octw.example.com/app
```

The browser flow is:

1. `octw-proxy` sends the request through `octw-oidc`
2. OCTW boots or refreshes the local `octw_session` cookie from the trusted forwarded email header
3. `POST /api/v1/app/deploy-or-resume` creates or resumes the user's single tenant
4. OCTW verifies the OpenClaw tenant before returning success
5. The browser connects to `/t/{slug}/ws` through `octw-edge` and lands in chat

### 6. Operator / CLI provisioning still works

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@example.com"}' | jq -r .dev_token)

JWT=$(curl -s -X POST http://localhost:8000/api/v1/auth/verify \
  -H 'Content-Type: application/json' \
  -d "{\"token\":\"$TOKEN\"}" | jq -r .access_token)

curl -s -X POST http://localhost:8000/api/v1/provision \
  -H "Authorization: Bearer $JWT" \
  -H 'Content-Type: application/json' \
  -d '{"slug":"acme", "name":"Acme Corp", "provider":"zai"}' | jq
```

The provision response now includes readiness verification:

```json
{
  "tenant_id": "...",
  "slug": "acme",
  "status": "running",
  "provider": "zai",
  "model": "zai/glm-5",
  "url": "https://octw.example.com/acme/",
  "verification_status": "verified",
  "verification_error": null
}
```

## Operator CLI

```bash
uv sync
uv run octw tenant list
uv run octw tenant status <tenant-id>
uv run octw tenant stop <tenant-id>
```

See [docs/cli.md](/Users/magos/dev/kumanday/OCTW/docs/cli.md).

## Documentation

| Document | Contents |
|---|---|
| [docs/architecture.md](/Users/magos/dev/kumanday/OCTW/docs/architecture.md) | Control-plane and tenant data flow |
| [docs/api.md](/Users/magos/dev/kumanday/OCTW/docs/api.md) | Browser app, operator API, and internal endpoints |
| [docs/configuration.md](/Users/magos/dev/kumanday/OCTW/docs/configuration.md) | Environment variables and proxy config files |
| [docs/deployment.md](/Users/magos/dev/kumanday/OCTW/docs/deployment.md) | Compose deployment, OIDC setup, verification |
| [docs/security.md](/Users/magos/dev/kumanday/OCTW/docs/security.md) | Reverse-proxy auth, trusted-proxy boundaries, secrets |
| [docs/providers.md](/Users/magos/dev/kumanday/OCTW/docs/providers.md) | Supported model providers |
| [docs/cli.md](/Users/magos/dev/kumanday/OCTW/docs/cli.md) | Operator CLI reference |

## Running Tests

```bash
uv run pytest tests/ -v
```

## License

See [LICENSE](/Users/magos/dev/kumanday/OCTW/LICENSE).
