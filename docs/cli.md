# CLI Reference

The OCTW CLI (`octw`) is an operator tool for managing tenants and secrets from the command line.

## Installation

```bash
uv sync
```

All commands are run via `uv run octw`.

## Tenant Commands

### Create a tenant

```bash
uv run octw tenant create --slug <slug> --name <name> [options]
```

Options:
- `--slug` (required) — DNS-safe identifier
- `--name` (required) — display name
- `--plan` — `standard` (default) or `premium`
- `--isolation` — `standard` (default) or `hardened`
- `--no-trusted-proxy` — disable trusted-proxy auth

Output: JSON with tenant ID, slug, status, and network ID.

### List tenants

```bash
uv run octw tenant list
```

Shows all tenants with their status and container state.

### Start a tenant

```bash
uv run octw tenant start <tenant-id>
```

Pulls secrets from the vault and starts the container.

### Stop a tenant

```bash
uv run octw tenant stop <tenant-id>
```

Stops and removes the container. State volumes are preserved.

### Pause a tenant

```bash
uv run octw tenant pause <tenant-id>
```

Pauses the container (memory retained, CPU released).

### Get tenant status

```bash
uv run octw tenant status <tenant-id>
```

Output: JSON with runtime state, container ID, last activity, and resource limits.

### Delete a tenant

```bash
uv run octw tenant delete <tenant-id> [--yes]
```

Stops the container, removes the network, deletes filesystem directories, and removes the tenant from the database. Use `--yes` to skip the confirmation prompt.

## Secret Commands

### Set a secret

```bash
uv run octw secret set <tenant-id> --name <name> [--value <value>] [--env-var <env-var>]
```

- `--name` (required) — secret name
- `--value` — secret value (prompted securely if not provided)
- `--env-var` — target environment variable name in the container

### List secrets

```bash
uv run octw secret list <tenant-id>
```

Shows secret metadata (name, type, target env var). Values are never displayed.

## Server Commands

### Run the API server

```bash
uv run octw server api [--host 0.0.0.0] [--port 8000]
```

### Run the edge proxy

```bash
uv run octw server edge [--host 0.0.0.0] [--port 8443]
```

These commands are for development/debugging. For production, use Docker Compose.
