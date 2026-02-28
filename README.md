# OCTW — OpenClaw Tenant Wrapper

OCTW is a multi-tenant abstraction layer that provisions and operates multiple independent [OpenClaw](https://github.com/openclaw/openclaw) installations on a single host. Each tenant gets its own isolated OpenClaw gateway, network, filesystem, credentials, and webchat — using the upstream container image without forking.

## Quick Start

### Prerequisites

- Docker (with compose plugin)
- [uv](https://docs.astral.sh/uv/) (for CLI and development)

### 1. Clone and prepare the host

```bash
git clone https://github.com/kumanday/OCTW.git && cd OCTW

sudo mkdir -p /var/lib/octw /etc/octw
sudo chown $USER /var/lib/octw
sudo python3 -c "import os; open('/etc/octw/master.key','wb').write(os.urandom(32))"
sudo chown $USER /etc/octw/master.key
sudo chmod 600 /etc/octw/master.key
```

### 2. Configure provider API keys

Set one or more LLM provider keys. At least one is required:

```bash
export OCTW_ZAI_API_KEY="your-zai-key"          # Z.ai GLM Coding Plan
export OCTW_MOONSHOT_API_KEY="your-moonshot-key" # Moonshot AI Kimi Coding Plan
export OCTW_MINIMAX_API_KEY="your-minimax-key"   # MiniMax Coding Plan
```

### 3. Launch the stack

```bash
export OCTW_KEK=$(python3 -c "print(open('/etc/octw/master.key','rb').read().hex())")
export OCTW_JWT_SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
docker compose up -d
```

This starts four services:

| Service | Port | Purpose |
|---|---|---|
| **octw-api** | 8000 | REST API and one-click provisioning |
| **octw-edge** | 8443 | Tenant proxy with wake-on-request |
| **octw-db** | 5432 | PostgreSQL (metadata, secrets, audit) |
| **octw-cache** | 6379 | Redis (sessions, locks) |

### 4. Provision a tenant

```bash
# Authenticate
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@example.com"}' | jq -r .dev_token)

JWT=$(curl -s -X POST http://localhost:8000/api/v1/auth/verify \
  -H 'Content-Type: application/json' \
  -d "{\"token\":\"$TOKEN\"}" | jq -r .access_token)

# One-click provision
curl -s -X POST http://localhost:8000/api/v1/provision \
  -H "Authorization: Bearer $JWT" \
  -H 'Content-Type: application/json' \
  -d '{"slug":"acme", "name":"Acme Corp", "provider":"zai"}' | jq
```

Response:
```json
{
  "tenant_id": "...",
  "slug": "acme",
  "status": "running",
  "provider": "zai",
  "model": "zai-coding/glm-5",
  "url": "https://octw.example.com/acme/"
}
```

The tenant's OpenClaw webchat is accessible at `https://octw.example.com/acme/`.

### 5. List available providers

```bash
curl -s http://localhost:8000/api/v1/provision/providers \
  -H "Authorization: Bearer $JWT" | jq
```

## CLI

```bash
uv sync
uv run octw tenant list
uv run octw tenant status <tenant-id>
uv run octw tenant stop <tenant-id>
```

See [docs/cli.md](docs/cli.md) for the full command reference.

## Documentation

| Document | Contents |
|---|---|
| [Architecture](docs/architecture.md) | Component overview, isolation model, data flow |
| [API Reference](docs/api.md) | All REST endpoints with request/response examples |
| [Providers](docs/providers.md) | Supported LLM providers, adding new ones |
| [Configuration](docs/configuration.md) | All environment variables and defaults |
| [Security](docs/security.md) | Threat model, secret strategy, container hardening |
| [CLI Reference](docs/cli.md) | Operator command-line tool |
| [Deployment](docs/deployment.md) | Production setup, Docker Compose, development mode |

## Running Tests

```bash
uv run pytest tests/ -v
```

## License

See [LICENSE](LICENSE).
