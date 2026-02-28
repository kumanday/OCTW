from __future__ import annotations

from octw.common.config import OCTWSettings


class TestConfig:
    def test_defaults(self):
        s = OCTWSettings()
        assert s.tenant_base_dir == "/var/lib/octw/tenants"
        assert s.default_pids_limit == 512
        assert s.idle_pause_seconds == 1800
        assert s.idle_stop_seconds == 28800

    def test_env_prefix(self):
        import os
        os.environ["OCTW_LOG_LEVEL"] = "DEBUG"
        s = OCTWSettings()
        assert s.log_level == "DEBUG"
        del os.environ["OCTW_LOG_LEVEL"]
