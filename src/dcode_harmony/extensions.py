"""dcode Python extension entrypoint for Harmony tooling."""

from __future__ import annotations

from deepagents_code.extensions import ExtensionAPI

from dcode_harmony.tools.apply_patch import PatchError, apply_patch_text


async def extension(api: ExtensionAPI) -> None:
    """Register GPT-OSS expected tools for dcode sessions."""

    def apply_patch(patch: str) -> str:
        try:
            return apply_patch_text(patch, workspace=api.cwd)
        except PatchError as exc:
            return f"Patch failed: {exc}"

    apply_patch.__name__ = "apply_patch"
    apply_patch.__doc__ = "Apply patch text inside the current workspace safely."
    api.register_tool(apply_patch)
