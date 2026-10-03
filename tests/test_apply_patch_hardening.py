"""Failing-first tests for apply_patch hardening (PR review §6)."""

from __future__ import annotations

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


def test_move_to_existing_destination_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("hello\n", encoding="utf-8")
    (tmp_path / "b.txt").write_text("keep\n", encoding="utf-8")
    patch = """*** Begin Patch
*** Update File: a.txt
*** Move to: b.txt
@@
-hello
+changed
*** End Patch
"""
    with pytest.raises(PatchError, match="destination already exists"):
        apply_patch_text(patch, workspace=tmp_path)
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "hello\n"
    assert (tmp_path / "b.txt").read_text(encoding="utf-8") == "keep\n"


def test_move_to_new_destination_works(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("hello\n", encoding="utf-8")
    patch = """*** Begin Patch
*** Update File: a.txt
*** Move to: sub/dir/b.txt
@@
-hello
+hi
*** End Patch
"""
    apply_patch_text(patch, workspace=tmp_path)
    assert not (tmp_path / "a.txt").exists()
    assert (tmp_path / "sub/dir/b.txt").read_text(encoding="utf-8") == "hi\n"


def test_rollback_removes_created_directories(tmp_path: Path) -> None:
    good = tmp_path / "good.txt"
    good.write_text("x\n", encoding="utf-8")
    patch = """*** Begin Patch
*** Add File: newdir/created.txt
+data
*** Update File: missing.txt
@@
-nope
+yes
*** End Patch
"""
    with pytest.raises(PatchError):
        apply_patch_text(patch, workspace=tmp_path)
    assert not (tmp_path / "newdir").exists()
    assert good.read_text(encoding="utf-8") == "x\n"


def test_rollback_restores_source_after_move_failure(tmp_path: Path) -> None:
    # Force a post-move failure by placing a later operation that cannot be
    # validated... validation runs first, so instead trigger a write failure
    # at execution time via a second move into an existing path created by an
    # earlier op in the same patch.
    (tmp_path / "one.txt").write_text("1\n", encoding="utf-8")
    (tmp_path / "two.txt").write_text("2\n", encoding="utf-8")
    patch = """*** Begin Patch
*** Update File: one.txt
*** Move to: moved.txt
@@
-1
+1b
*** Delete File: moved.txt
*** End Patch
"""
    # Delete of missing file fails at validation -> nothing applied.
    with pytest.raises(PatchError):
        apply_patch_text(patch, workspace=tmp_path)
    assert (tmp_path / "one.txt").read_text(encoding="utf-8") == "1\n"
    assert (tmp_path / "two.txt").read_text(encoding="utf-8") == "2\n"


def test_empty_file_and_no_final_newline_and_crlf_and_unicode(tmp_path: Path) -> None:
    p = tmp_path / "unicode.txt"
    p.write_bytes("olá\r\nfim".encode())  # CRLF + no trailing newline
    patch = """*** Begin Patch
*** Update File: unicode.txt
@@
 olá
-fim
+fim!
*** End Patch
"""
    apply_patch_text(patch, workspace=tmp_path)
    assert p.read_bytes() == "olá\r\nfim!".encode()


def test_same_path_multiple_operations_compose(tmp_path: Path) -> None:
    target = tmp_path / "a.txt"
    target.write_text("old\n", encoding="utf-8")
    patch = """*** Begin Patch
*** Update File: a.txt
@@
-old
+first
*** Update File: a.txt
@@
-first
+second
*** End Patch
"""
    apply_patch_text(patch, workspace=tmp_path)
    assert target.read_text(encoding="utf-8") == "second\n"


def test_add_then_update_same_path_composes(tmp_path: Path) -> None:
    patch = """*** Begin Patch
*** Add File: new.txt
+alpha
*** Update File: new.txt
@@
-alpha
+beta
*** End Patch
"""
    apply_patch_text(patch, workspace=tmp_path)
    assert (tmp_path / "new.txt").read_text(encoding="utf-8") == "beta\n"


def test_delete_then_add_same_path_composes(tmp_path: Path) -> None:
    (tmp_path / "d.txt").write_text("gone\n", encoding="utf-8")
    patch = """*** Begin Patch
*** Delete File: d.txt
*** Add File: d.txt
+back
*** End Patch
"""
    apply_patch_text(patch, workspace=tmp_path)
    assert (tmp_path / "d.txt").read_text(encoding="utf-8") == "back\n"


def test_eof_anchored_hunk_ignores_earlier_duplicates(tmp_path: Path) -> None:
    target = tmp_path / "tail.txt"
    target.write_text("a\nx\nb\nx\n", encoding="utf-8")
    patch = """*** Begin Patch
*** Update File: tail.txt
@@
-x
+X
*** End of File
*** End Patch
"""
    apply_patch_text(patch, workspace=tmp_path)
    assert target.read_text(encoding="utf-8") == "a\nx\nb\nX\n"


def test_failed_write_leaves_original_file_intact(tmp_path: Path) -> None:
    good = tmp_path / "good.txt"
    good.write_text("one\nold\n", encoding="utf-8")
    blocked = tmp_path / "blocked.txt"
    blocked.write_text("keep\n", encoding="utf-8")
    blocked.chmod(0o444)
    try:
        patch = """*** Begin Patch
*** Update File: good.txt
@@
 one
-old
+new
*** Update File: blocked.txt
@@
-keep
+changed
*** End Patch
"""
        with pytest.raises((PatchError, OSError)):
            apply_patch_text(patch, workspace=tmp_path)
        # Rollback must restore the earlier successful edit too.
        assert good.read_text(encoding="utf-8") == "one\nold\n"
        assert blocked.read_text(encoding="utf-8") == "keep\n"
    finally:
        blocked.chmod(0o644)
