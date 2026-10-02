"""Failing-first tests for apply_patch hardening (PR review §6)."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from dcode_harmony.tools.apply_patch import PatchError, apply_patch_text


def test_update_with_move_to_renames_file(tmp_path: Path) -> None:
    (tmp_path / "old.txt").write_text("a\nb\nc\n", encoding="utf-8")
    patch = """*** Begin Patch
*** Update File: old.txt
*** Move to: new.txt
@@
 a
-b
+B
 c
*** End Patch
"""
    output = apply_patch_text(patch, workspace=tmp_path)
    assert not (tmp_path / "old.txt").exists()
    assert (tmp_path / "new.txt").read_text(encoding="utf-8") == "a\nB\nc\n"
    assert "new.txt" in output


def test_crlf_line_endings_are_preserved(tmp_path: Path) -> None:
    target = tmp_path / "win.txt"
    target.write_bytes(b"one\r\nold\r\nthree\r\n")
    patch = """*** Begin Patch
*** Update File: win.txt
@@
 one
-old
+new
 three
*** End Patch
"""
    apply_patch_text(patch, workspace=tmp_path)
    assert target.read_bytes() == b"one\r\nnew\r\nthree\r\n"


def test_missing_trailing_newline_is_preserved(tmp_path: Path) -> None:
    target = tmp_path / "noeol.txt"
    target.write_bytes(b"one\nold")
    patch = """*** Begin Patch
*** Update File: noeol.txt
@@
 one
-old
+new
*** End Patch
"""
    apply_patch_text(patch, workspace=tmp_path)
    assert target.read_bytes() == b"one\nnew"


def test_ambiguous_context_is_rejected(tmp_path: Path) -> None:
    target = tmp_path / "dup.txt"
    target.write_text("same\nsame\n", encoding="utf-8")
    patch = """*** Begin Patch
*** Update File: dup.txt
@@
-same
+different
*** End Patch
"""
    with pytest.raises(PatchError, match="ambiguous context"):
        apply_patch_text(patch, workspace=tmp_path)


def test_multi_file_patch_is_atomic_on_failure(tmp_path: Path) -> None:
    good = tmp_path / "good.txt"
    good.write_text("a\nold\n", encoding="utf-8")
    patch = """*** Begin Patch
*** Update File: good.txt
@@
 a
-old
+new
*** Update File: missing.txt
@@
-x
+y
*** End Patch
"""
    with pytest.raises(PatchError):
        apply_patch_text(patch, workspace=tmp_path)
    # The successful op must have been rolled back too.
    assert good.read_text(encoding="utf-8") == "a\nold\n"


def test_symlink_to_file_inside_workspace_is_rejected(tmp_path: Path) -> None:
    real = tmp_path / "real.txt"
    real.write_text("x\n", encoding="utf-8")
    link = tmp_path / "link.txt"
    link.symlink_to(real)
    patch = """*** Begin Patch
*** Update File: link.txt
@@
-x
+y
*** End Patch
"""
    with pytest.raises(PatchError):
        apply_patch_text(patch, workspace=tmp_path)


def test_dangling_symlink_is_rejected(tmp_path: Path) -> None:
    link = tmp_path / "dangling.txt"
    link.symlink_to(tmp_path / "nope.txt")
    patch = """*** Begin Patch
*** Update File: dangling.txt
@@
-x
+y
*** End Patch
"""
    with pytest.raises(PatchError):
        apply_patch_text(patch, workspace=tmp_path)


def test_missing_workspace_is_rejected(tmp_path: Path) -> None:
    patch = """*** Begin Patch
*** Add File: a.txt
+x
*** End Patch
"""
    with pytest.raises(PatchError):
        apply_patch_text(patch, workspace=tmp_path / "does-not-exist")


def test_add_existing_file_fails_without_touching_it(tmp_path: Path) -> None:
    target = tmp_path / "exists.txt"
    target.write_text("keep\n", encoding="utf-8")
    patch = """*** Begin Patch
*** Add File: exists.txt
+other
*** End Patch
"""
    with pytest.raises(PatchError):
        apply_patch_text(patch, workspace=tmp_path)
    assert target.read_text(encoding="utf-8") == "keep\n"


def test_symlinked_parent_directory_escape_rejected(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"outside-{tmp_path.name}"
    outside.mkdir(exist_ok=True)
    (tmp_path / "sub").symlink_to(outside)
    patch = """*** Begin Patch
*** Add File: sub/evil.txt
+x
*** End Patch
"""
    with pytest.raises(PatchError):
        apply_patch_text(patch, workspace=tmp_path)
    assert not (outside / "evil.txt").exists()


def test_end_of_file_marker_anchors_to_eof(tmp_path: Path) -> None:
    target = tmp_path / "tail.txt"
    target.write_text("a\nb\nc\n", encoding="utf-8")
    patch = """*** Begin Patch
*** Update File: tail.txt
@@
 b
-c
+C
*** End of File
*** End Patch
"""
    apply_patch_text(patch, workspace=tmp_path)
    assert target.read_text(encoding="utf-8") == "a\nb\nC\n"
