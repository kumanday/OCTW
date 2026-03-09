from __future__ import annotations

import pytest

from octw.models.provider import PROVIDERS, ProviderKey, get_provider


class TestProviderRegistry:
    def test_all_providers_defined(self):
        assert len(PROVIDERS) == 3
        assert ProviderKey.ZAI in PROVIDERS
        assert ProviderKey.MOONSHOT in PROVIDERS
        assert ProviderKey.MINIMAX in PROVIDERS

    def test_get_provider_by_key(self):
        spec = get_provider("zai")
        assert spec.env_var == "ZAI_API_KEY"
        assert spec.model_id == "zai/glm-5"
        assert spec.provider_name == "zai"
        assert spec.model_name == "glm-5"
        assert spec.builtin is True

    def test_get_provider_moonshot(self):
        spec = get_provider("moonshot")
        assert spec.env_var == "MOONSHOT_API_KEY"
        assert spec.model_id == "kimi-coding/k2p5"
        assert spec.provider_name == "kimi-coding"
        assert spec.builtin is True

    def test_get_provider_minimax(self):
        spec = get_provider("minimax")
        assert spec.env_var == "MINIMAX_API_KEY"
        assert spec.model_id == "minimax-coding/MiniMax-M2.5"
        assert spec.provider_name == "minimax-coding"
        assert spec.builtin is True

    def test_get_provider_invalid(self):
        with pytest.raises(ValueError, match="Unknown provider"):
            get_provider("invalid")

    def test_provider_specs_have_unique_env_vars(self):
        env_vars = [s.env_var for s in PROVIDERS.values()]
        assert len(env_vars) == len(set(env_vars))

    def test_provider_specs_have_unique_models(self):
        models = [s.model_id for s in PROVIDERS.values()]
        assert len(models) == len(set(models))

    def test_model_id_matches_provider_and_model_name(self):
        for spec in PROVIDERS.values():
            assert spec.model_id == f"{spec.provider_name}/{spec.model_name}"
