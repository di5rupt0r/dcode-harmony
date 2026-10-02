from __future__ import annotations

import sys
import types
from pathlib import Path

from dcode_harmony import cli
from dcode_harmony.launcher import DEFAULT_MODEL_SPEC, build_bootstrap_config, ensure_profile


def test_build_bootstrap_config_contains_default_provider() -> None:
    config = build_bootstrap_config()
    assert '[models]\ndefault = "local-harmony:gpt-oss-20b"' in config
    assert '[models.providers.local-harmony]' in config
    assert (
        'class_path = "dcode_harmony.providers.harmony:HarmonyCompletionChatModel"'
        in config
    )


def test_ensure_profile_writes_expected_config(tmp_path: Path) -> None:
    profile = ensure_profile(tmp_path)
    config = (profile / "config.toml").read_text(encoding="utf-8")
    assert profile.exists()
    assert f'default = "{DEFAULT_MODEL_SPEC}"' in config


def test_cli_main_sets_env_and_delegates(monkeypatch, tmp_path: Path) -> None:
    calls: dict[str, str] = {}

    def _cli_main() -> int:
        calls["DEEPAGENTS_HOME"] = str(__import__("os").environ["DEEPAGENTS_HOME"])
        calls["DEEPAGENTS_CODE_EXPERIMENTAL"] = str(
            __import__("os").environ["DEEPAGENTS_CODE_EXPERIMENTAL"]
        )
        return 7

    monkeypatch.setitem(sys.modules, "deepagents_code", types.SimpleNamespace(cli_main=_cli_main))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("DEEPAGENTS_HOME", raising=False)
    monkeypatch.delenv("DEEPAGENTS_CODE_EXPERIMENTAL", raising=False)

    assert cli.main() == 7
    assert calls["DEEPAGENTS_HOME"].endswith(".dcode-harmony")
    assert calls["DEEPAGENTS_CODE_EXPERIMENTAL"] == "1"
