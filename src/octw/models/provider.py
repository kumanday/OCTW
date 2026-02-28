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
    model_id: str
    display_name: str


PROVIDERS: dict[ProviderKey, ProviderSpec] = {
    ProviderKey.ZAI: ProviderSpec(
        key=ProviderKey.ZAI,
        env_var="ZAI_API_KEY",
        model_id="zai-coding/glm-5",
        display_name="Z.ai GLM Coding Plan",
    ),
    ProviderKey.MOONSHOT: ProviderSpec(
        key=ProviderKey.MOONSHOT,
        env_var="MOONSHOT_API_KEY",
        model_id="kimi-coding/k2p5",
        display_name="Moonshot AI Kimi Coding Plan",
    ),
    ProviderKey.MINIMAX: ProviderSpec(
        key=ProviderKey.MINIMAX,
        env_var="MINIMAX_API_KEY",
        model_id="minimax-coding/MiniMax-M2.5",
        display_name="MiniMax Coding Plan",
    ),
}


def get_provider(key: str) -> ProviderSpec:
    try:
        return PROVIDERS[ProviderKey(key)]
    except (ValueError, KeyError):
        valid = ", ".join(p.value for p in ProviderKey)
        raise ValueError(f"Unknown provider '{key}'. Valid providers: {valid}") from None
