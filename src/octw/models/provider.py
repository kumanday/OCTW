from __future__ import annotations

import enum
from dataclasses import dataclass


class ProviderKey(enum.StrEnum):
    ZAI = "zai"
    MOONSHOT = "moonshot"
    MINIMAX = "minimax"


@dataclass(frozen=True)
class ProviderSpec:
    key: ProviderKey
    env_var: str
    provider_name: str  # OpenClaw provider name (before the / in model ref)
    model_id: str  # full model reference: provider_name/model_name
    model_name: str  # just the model name (after the /)
    display_name: str
    base_url: str | None  # None = built-in provider, no models.providers entry needed
    api_type: str | None  # "openai-completions" or "anthropic-messages"
    builtin: bool  # if True, only set auth + model selection, no providers config


PROVIDERS: dict[ProviderKey, ProviderSpec] = {
    ProviderKey.ZAI: ProviderSpec(
        key=ProviderKey.ZAI,
        env_var="ZAI_API_KEY",
        provider_name="zai",
        model_id="zai/glm-5",
        model_name="glm-5",
        display_name="Z.ai GLM Coding Plan",
        base_url="https://api.z.ai/api/coding/paas/v4",
        api_type="openai-completions",
        builtin=False,
    ),
    ProviderKey.MOONSHOT: ProviderSpec(
        key=ProviderKey.MOONSHOT,
        env_var="MOONSHOT_API_KEY",
        provider_name="kimi-coding",
        model_id="kimi-coding/k2p5",
        model_name="k2p5",
        display_name="Moonshot AI Kimi Coding Plan",
        base_url=None,
        api_type=None,
        builtin=True,
    ),
    ProviderKey.MINIMAX: ProviderSpec(
        key=ProviderKey.MINIMAX,
        env_var="MINIMAX_API_KEY",
        provider_name="minimax-coding",
        model_id="minimax-coding/MiniMax-M2.5",
        model_name="MiniMax-M2.5",
        display_name="MiniMax Coding Plan",
        base_url=None,
        api_type=None,
        builtin=True,
    ),
}


def get_provider(key: str) -> ProviderSpec:
    try:
        return PROVIDERS[ProviderKey(key)]
    except (ValueError, KeyError):
        valid = ", ".join(p.value for p in ProviderKey)
        raise ValueError(f"Unknown provider '{key}'. Valid providers: {valid}") from None
