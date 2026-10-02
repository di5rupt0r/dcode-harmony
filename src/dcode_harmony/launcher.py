"""Bootstrap launcher for upstream deepagents-code CLI."""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_PROVIDER = "local-harmony"
DEFAULT_MODEL = "gpt-oss-20b"
DEFAULT_MODEL_SPEC = f"{DEFAULT_PROVIDER}:{DEFAULT_MODEL}"
DEFAULT_ENDPOINT = "http://127.0.0.1:8080/completion"


def build_bootstrap_config() -> str:
    """Return config.toml content for a plug-and-play Harmony default."""
    return f"""[models]
default = "{DEFAULT_MODEL_SPEC}"
allowed = ["{DEFAULT_MODEL_SPEC}"]

[models.providers.local-harmony]
enabled = true
class_path = "dcode_harmony.providers.harmony:HarmonyCompletionChatModel"
models = ["{DEFAULT_MODEL}"]

[models.providers.local-harmony.params]
base_url = "http://127.0.0.1:8080"
completion_path = "/completion"
timeout_s = 120.0
stop = ["<|return|>", "<|call|>"]
"""


def ensure_profile(profile_root: Path) -> Path:
    """Create an isolated Deep Agents profile with Harmony defaults."""
    profile_root.mkdir(parents=True, exist_ok=True)
    config_path = profile_root / "config.toml"
    if not config_path.exists():
        config_path.write_text(build_bootstrap_config(), encoding="utf-8")
    return profile_root


def run_dcode() -> int:
    """Delegate execution to deepagents-code after environment bootstrap."""
    default_home = Path.home() / ".dcode-harmony"
    profile_root = Path(os.environ.get("DEEPAGENTS_HOME", default_home))
    ensure_profile(profile_root)
    os.environ.setdefault("DEEPAGENTS_HOME", str(profile_root))
    os.environ.setdefault("DEEPAGENTS_CODE_EXPERIMENTAL", "1")
    from deepagents_code import cli_main

    result = cli_main()
    # deepagents_code.cli_main is typed `() -> None` (exits via SystemExit);
    # a return of None means success.
    return 0 if result is None else int(result)
