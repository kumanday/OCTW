# Deployment

## Docker Compose (Recommended)

### Prerequisites

- Docker Engine with compose plugin
- At least one LLM provider API key

### Host Setup

```bash
# Create directories
sudo mkdir -p /var/lib/octw /etc/octw
sudo chown $USER /var/lib/octw

# Generate master encryption key
sudo python3 -c "import os; open('/etc/octw/master.key','wb').write(os.urandom(32))"
sudo chown $USER /etc/octw/master.key
sudo chmod 600 /etc/octw/master.key
```

### Environment Variables

```bash
# Required
export OCTW_KEK=$(python3 -c "print(open('/etc/octw/master.key','rb').read().hex())")
export OCTW_JWT_SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")

# Provider keys (at least one required)
export OCTW_ZAI_API_KEY="your-key"
export OCTW_MOONSHOT_API_KEY="your-key"
export OCTW_MINIMAX_API_KEY="your-key"
```

### Launch

```bash
docker compose up -d
```

### Verify

```bash
docker compose ps          # all 4 services should be Up/Healthy
curl http://localhost:8000/health   # {"status":"ok"}
curl http://localhost:8443/health   # {"status":"ok","service":"octw-edge"}
```

### Services

| Service | Port | Image |
|---|---|---|
| octw-api | 8000 | Built from Dockerfile |
| octw-edge | 8443 | Built from Dockerfile |
| octw-db | 5432 | postgres:16-alpine |
| octw-cache | 6379 | redis:7-alpine |

### Rebuild After Code Changes

```bash
docker compose up -d --build
```

### View Logs

```bash
docker compose logs -f octw-api
docker compose logs -f octw-edge
```

### Reset Everything

```bash
docker compose down -v            # removes containers and volumes
sudo rm -rf /var/lib/octw/tenants/*  # removes tenant data
```

## Development Setup

For running services outside Docker Compose (e.g. for debugging with breakpoints):

```bash
uv sync

# Start only infrastructure
docker compose up -d octw-db octw-cache

# Run API in one terminal
uv run octw server api

# Run edge proxy in another terminal
uv run octw server edge
```

Both connect to the same Postgres and Redis instances from Docker Compose.

## Production Considerations

### TLS Termination

The edge proxy (octw-edge) does not terminate TLS itself. In production, place a reverse proxy in front:

- **nginx** or **Caddy** with automatic ACME certificates
- Cloud load balancer with TLS termination
- Tailscale / WireGuard for private access

### Database

The included Postgres is suitable for development. For production:

- Use a managed Postgres instance (RDS, Cloud SQL, etc.)
- Enable SSL connections
- Set strong passwords
- Configure backups

Update `OCTW_DB_URL` to point to your production database.

### Secrets

- Use a strong, unique `OCTW_JWT_SECRET` (at least 32 bytes)
- Protect `/etc/octw/master.key` with file permissions (`chmod 600`)
- Consider backing the KEK with cloud KMS for production
- Rotate the JWT secret periodically

### Resource Limits

Default tenant limits (1.5 GB RAM, 1 vCPU, 512 PIDs) are suitable for development. Adjust per deployment:

```bash
export OCTW_DEFAULT_MEM_LIMIT=2g
export OCTW_DEFAULT_PIDS_LIMIT=1024
```

### Monitoring

Prometheus metrics are available at `http://localhost:8000/metrics`. Key metrics:

- `octw_tenant_container_starts_total`
- `octw_tenant_wake_events_total`
- `octw_active_tenants`
- `octw_proxy_request_duration_seconds`
- `octw_auth_failures_total`

A Prometheus scrape config is provided at `configs/prometheus.yml`.
