"""CLI entry point for plug-and-play dcode Harmony launcher."""

from dcode_harmony.launcher import run_dcode


def main() -> int:
    """Run upstream dcode with Harmony bootstrap defaults."""
    return run_dcode()
