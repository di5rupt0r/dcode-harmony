from __future__ import annotations

import sys
import types
from pathlib import Path

from dcode_harmony import cli
from dcode_harmony.launcher import (
    DEFAULT_MODEL_SPEC,
    build_bootstrap_config,
    ensure_profile,
)


def test_build_bootstrap_config_contains_default_provider() -> None:
    config = build_bootstrap_config()
    assert '[models]\ndefault = "local-harmony:gpt-oss-20b"' in config
    assert "[models.providers.local-harmony]" in config
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

    monkeypatch.setitem(
        sys.modules, "deepagents_code", types.SimpleNamespace(cli_main=_cli_main)
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("DEEPAGENTS_HOME", raising=False)
    monkeypatch.delenv("DEEPAGENTS_CODE_EXPERIMENTAL", raising=False)

    assert cli.main() == 7
    assert calls["DEEPAGENTS_HOME"].endswith(".dcode-harmony")
    assert calls["DEEPAGENTS_CODE_EXPERIMENTAL"] == "1"


def test_launcher_respects_env_override_for_home(monkeypatch, tmp_path: Path) -> None:
    custom_home = tmp_path / "custom"
    monkeypatch.setenv("DEEPAGENTS_HOME", str(custom_home))
    profile = ensure_profile(custom_home)
    assert profile == custom_home
    assert profile.exists()


def test_bootstrap_config_includes_endpoint_params() -> None:
    config = build_bootstrap_config()
    assert 'base_url = "http://127.0.0.1:8080"' in config
    assert 'completion_path = "/completion"' in config
    assert "timeout_s = 120.0" in config
    assert 'stop = ["<|return|>", "<|call|>"]' in config


def test_cli_main_none_maps_to_exit_zero(monkeypatch, tmp_path: Path) -> None:
    def _cli_main() -> None:
        return None

    monkeypatch.setitem(
        sys.modules, "deepagents_code", types.SimpleNamespace(cli_main=_cli_main)
    )
    monkeypatch.setenv("DEEPAGENTS_HOME", str(tmp_path / "profile"))

    assert cli.main() == 0


def test_run_dcode_does_not_overwrite_existing_config(
    monkeypatch, tmp_path: Path
) -> None:
    profile = tmp_path / "profile"
    profile.mkdir()
    (profile / "config.toml").write_text("# user edits\n", encoding="utf-8")
    monkeypatch.setenv("DEEPAGENTS_HOME", str(profile))
    ensure_profile(profile)
    assert (profile / "config.toml").read_text(encoding="utf-8") == "# user edits\n"


def test_generated_config_is_consumed_by_real_dcode(tmp_path: Path) -> None:
    """The bootstrap config.toml must actually load through deepagents_code."""
    import subprocess
    import sys

    profile = ensure_profile(tmp_path / "profile")
    env = {**__import__("os").environ, "DEEPAGENTS_HOME": str(profile)}
    code = (
        "from deepagents_code.config import create_model;"
        "r = create_model('local-harmony:gpt-oss-20b');"
        "m = r.model; print(type(m).__module__ + ':' + type(m).__name__);"
        "print(m.base_url, m.completion_path)"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "dcode_harmony.providers.harmony:HarmonyCompletionChatModel" in result.stdout
    assert "http://127.0.0.1:8080 /completion" in result.stdout


def test_dcode_help_subprocess(tmp_path: Path) -> None:
    import subprocess
    import sys

    env = {**__import__("os").environ, "DEEPAGENTS_HOME": str(tmp_path / "profile")}
    binary = Path(sys.executable).parent / "dcode"
    result = subprocess.run(
        [str(binary), "--help"],
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert result.returncode == 0
    assert "deepagents-code" in result.stdout
