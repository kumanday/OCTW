# Providers

OCTW supports multiple LLM providers. Provider API keys are configured once on the server and shared across all tenants. Each tenant selects a provider at provisioning time.

## Available Providers

| Key | Display Name | Model ID | Env Var |
|---|---|---|---|
| `zai` | Z.ai GLM Coding Plan | `zai/glm-5` | `OCTW_ZAI_API_KEY` |
| `moonshot` | Moonshot AI Kimi Coding Plan | `kimi-coding/k2p5` | `OCTW_MOONSHOT_API_KEY` |
| `minimax` | MiniMax Coding Plan | `minimax-coding/MiniMax-M2.5` | `OCTW_MINIMAX_API_KEY` |

## Configuration

Set the API keys as environment variables on the host (or in `docker-compose.yml`). Only providers with a configured key will be available for provisioning. You can configure one, two, or all three.

```bash
export OCTW_ZAI_API_KEY="your-zai-api-key"
export OCTW_MOONSHOT_API_KEY="your-moonshot-api-key"
export OCTW_MINIMAX_API_KEY="your-minimax-api-key"
```

## Checking Configured Providers

```bash
curl -s http://localhost:8000/api/v1/provision/providers \
  -H "Authorization: Bearer $JWT" | jq
```

Response:

```json
[
  {
    "key": "zai",
    "display_name": "Z.ai GLM Coding Plan",
    "model": "zai/glm-5",
    "configured": true
  },
  {
    "key": "moonshot",
    "display_name": "Moonshot AI Kimi Coding Plan",
    "model": "kimi-coding/k2p5",
    "configured": false
  },
  {
    "key": "minimax",
    "display_name": "MiniMax Coding Plan",
    "model": "minimax-coding/MiniMax-M2.5",
    "configured": true
  }
]
```

## How Providers Are Used

When a tenant is provisioned with a provider:

1. **Init job** — the provider's API key is injected as an env var (e.g. `ZAI_API_KEY`) and `OPENCLAW_DEFAULT_MODEL` is set to the model ID.
2. **OpenClaw config** — `openclaw.json` is patched to set `models.default` to the model ID and configure the provider with a SecretRef (`{"$ref": "env:ZAI_API_KEY"}`), avoiding plaintext keys in config files.
3. **Runtime** — the container is started with the provider's API key injected as an env var. This happens on every start, including wake-on-request after hibernation.

The provider choice is stored on the tenant row, so it persists across restarts.

## Specifying a Provider During Provisioning

```bash
curl -X POST http://localhost:8000/api/v1/provision \
  -H "Authorization: Bearer $JWT" \
  -H 'Content-Type: application/json' \
  -d '{"slug":"acme", "name":"Acme Corp", "provider":"moonshot"}'
```

If the provider's API key is not configured on the server, the request fails with a 400 error.

## Adding a New Provider

Edit `src/octw/models/provider.py`:

```python
ProviderKey.NEW_PROVIDER: ProviderSpec(
    key=ProviderKey.NEW_PROVIDER,
    env_var="NEW_PROVIDER_API_KEY",
    model_id="new-provider/model-name",
    display_name="New Provider Plan",
),
```

Then add the corresponding setting in `src/octw/common/config.py`:

```python
new_provider_api_key: str | None = None
```

And update the `get_provider_api_key` mapping:

```python
"NEW_PROVIDER_API_KEY": self.new_provider_api_key,
```

Finally, add `OCTW_NEW_PROVIDER_API_KEY` to `docker-compose.yml` under the octw-api environment section.
