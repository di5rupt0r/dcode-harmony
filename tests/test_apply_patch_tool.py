from __future__ import annotations

from pathlib import Path

import pytest

from dcode_harmony.tools.apply_patch import PatchError, apply_patch_text


def test_apply_patch_updates_and_adds_files(tmp_path: Path) -> None:
    file_a = tmp_path / "a.txt"
    file_a.write_text("one\nold\nthree\n", encoding="utf-8")

    patch = """*** Begin Patch
*** Update File: a.txt
@@
 one
-old
+new
 three
*** Add File: b.txt
+hello
+world
*** End Patch
"""
    output = apply_patch_text(patch, workspace=tmp_path)
    assert "Updated a.txt" in output
    assert "Added b.txt" in output
    assert file_a.read_text(encoding="utf-8") == "one\nnew\nthree\n"
    assert (tmp_path / "b.txt").read_text(encoding="utf-8") == "hello\nworld\n"


def test_apply_patch_rejects_absolute_and_parent_traversal(tmp_path: Path) -> None:
    absolute = """*** Begin Patch
*** Add File: /etc/passwd
+x
*** End Patch
"""
    traversal = """*** Begin Patch
*** Add File: ../escape.txt
+x
*** End Patch
"""
    with pytest.raises(PatchError, match="absolute"):
        apply_patch_text(absolute, workspace=tmp_path)
    with pytest.raises(PatchError, match="outside workspace"):
        apply_patch_text(traversal, workspace=tmp_path)


def test_apply_patch_rejects_symlink_escape(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("outside\n", encoding="utf-8")
    link = tmp_path / "link.txt"
    link.symlink_to(outside)

    patch = """*** Begin Patch
*** Update File: link.txt
@@
-outside
+inside
*** End Patch
"""
    with pytest.raises(PatchError, match="symlink escape"):
        apply_patch_text(patch, workspace=tmp_path)


def test_apply_patch_rejects_malformed(tmp_path: Path) -> None:
    patch = "*** Begin Patch\n*** Update File: x.txt\n+line\n*** End Patch\n"
    with pytest.raises(PatchError, match="Malformed"):
        apply_patch_text(patch, workspace=tmp_path)
