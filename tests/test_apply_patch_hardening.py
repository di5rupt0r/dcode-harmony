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
    # Force a post-move failure at execution time: an add into an
    # unwritable directory. The move must be rolled back with the source
    # restored and the destination removed.
    (tmp_path / "one.txt").write_text("1\n", encoding="utf-8")
    blocked_dir = tmp_path / "blocked"
    blocked_dir.mkdir()
    blocked_dir.chmod(0o555)
    try:
        patch = """*** Begin Patch
*** Update File: one.txt
*** Move to: moved.txt
@@
-1
+1b
*** Add File: blocked/new.txt
+x
*** End Patch
"""
        with pytest.raises((PatchError, OSError)):
            apply_patch_text(patch, workspace=tmp_path)
        assert (tmp_path / "one.txt").read_text(encoding="utf-8") == "1\n"
        assert not (tmp_path / "moved.txt").exists()
        assert not (blocked_dir / "new.txt").exists()
    finally:
        blocked_dir.chmod(0o755)


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
    blocked_dir = tmp_path / "blocked"
    blocked_dir.mkdir()
    blocked = blocked_dir / "blocked.txt"
    blocked.write_text("keep\n", encoding="utf-8")
    blocked_dir.chmod(0o555)
    try:
        patch = """*** Begin Patch
*** Update File: good.txt
@@
 one
-old
+new
*** Update File: blocked/blocked.txt
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
        blocked_dir.chmod(0o755)


def test_eof_insertion_only_hunk_appends(tmp_path: Path) -> None:
    target = tmp_path / "tail.txt"
    target.write_text("head\n", encoding="utf-8")
    patch = """*** Begin Patch
*** Update File: tail.txt
@@
+tail
*** End of File
*** End Patch
"""
    apply_patch_text(patch, workspace=tmp_path)
    assert target.read_text(encoding="utf-8") == "head\ntail\n"


def test_executable_mode_preserved_on_update(tmp_path: Path) -> None:
    import os
    import stat

    target = tmp_path / "deploy.sh"
    target.write_text("#!/bin/sh\nold\n", encoding="utf-8")
    target.chmod(0o755)
    patch = """*** Begin Patch
*** Update File: deploy.sh
@@
-old
+new
*** End Patch
"""
    apply_patch_text(patch, workspace=tmp_path)
    assert stat.S_IMODE(os.stat(target).st_mode) == 0o755
    assert target.read_text(encoding="utf-8") == "#!/bin/sh\nnew\n"


def test_rollback_restores_executable_mode(tmp_path: Path) -> None:
    import os
    import stat

    good = tmp_path / "run.sh"
    good.write_text("one\nold\n", encoding="utf-8")
    good.chmod(0o755)
    blocked_dir = tmp_path / "blocked"
    blocked_dir.mkdir()
    blocked_dir.chmod(0o555)
    try:
        patch = """*** Begin Patch
*** Update File: run.sh
@@
-old
+new
*** Add File: blocked/new.txt
+x
*** End Patch
"""
        with pytest.raises((PatchError, OSError)):
            apply_patch_text(patch, workspace=tmp_path)
        assert stat.S_IMODE(os.stat(good).st_mode) == 0o755
        assert good.read_text(encoding="utf-8") == "one\nold\n"
    finally:
        blocked_dir.chmod(0o755)


def test_long_filename_near_component_limit_works(tmp_path: Path) -> None:
    name = "a" * 240 + ".txt"
    target = tmp_path / name
    target.write_text("one\nold\n", encoding="utf-8")
    patch = f"""*** Begin Patch
*** Update File: {name}
@@
-old
+new
*** End Patch
"""
    apply_patch_text(patch, workspace=tmp_path)
    assert target.read_text(encoding="utf-8") == "one\nnew\n"


def test_writable_file_in_readonly_directory_fails_clearly(tmp_path: Path) -> None:
    blocked_dir = tmp_path / "ro"
    blocked_dir.mkdir()
    target = blocked_dir / "notes.txt"
    target.write_text("x\n", encoding="utf-8")
    target.chmod(0o666)
    blocked_dir.chmod(0o555)
    try:
        patch = """*** Begin Patch
*** Update File: ro/notes.txt
@@
-x
+y
*** End Patch
"""
        with pytest.raises(PatchError, match="not writable"):
            apply_patch_text(patch, workspace=tmp_path)
    finally:
        blocked_dir.chmod(0o755)


def test_failed_replace_leaves_no_staged_temp(tmp_path: Path, monkeypatch) -> None:
    import dcode_harmony.tools.apply_patch as ap

    target = tmp_path / "a.txt"
    target.write_text("old\n", encoding="utf-8")
    real_replace = ap.os.replace

    def _boom(src, dst, **kwargs):
        raise OSError("simulated rename failure")

    # Syscall-boundary fault injection: no user-space trigger exists for
    # EPERM-on-rename on this host (chattr +i not permitted; no ro-tmpfs).
    # Stubbed only `os.replace` — same class as the httpx transport mock.
    monkeypatch.setattr(ap.os, "replace", _boom)
    patch = """*** Begin Patch
*** Update File: a.txt
@@
-old
+new
*** End Patch
"""
    with pytest.raises(OSError, match="simulated rename failure"):
        apply_patch_text(patch, workspace=tmp_path)
    monkeypatch.setattr(ap.os, "replace", real_replace)
    leftovers = [p.name for p in tmp_path.iterdir() if ".dcode-tmp-" in p.name]
    assert leftovers == []
    assert target.read_text(encoding="utf-8") == "old\n"


def test_delete_add_update_same_path_replacement_keeps_default_mode(
    tmp_path: Path,
) -> None:
    import os
    import stat

    target = tmp_path / "run.sh"
    target.write_text("old\n", encoding="utf-8")
    target.chmod(0o755)
    patch = """*** Begin Patch
*** Delete File: run.sh
*** Add File: run.sh
+new
*** Update File: run.sh
@@
-new
+newer
*** End Patch
"""
    apply_patch_text(patch, workspace=tmp_path)
    assert target.read_text(encoding="utf-8") == "newer\n"
    mode = stat.S_IMODE(os.stat(target).st_mode)
    assert mode != 0o755, f"replacement inherited deleted file's mode: {oct(mode)}"


def test_failed_chmod_leaves_no_staged_temp(tmp_path: Path, monkeypatch) -> None:
    """Fault injection at the syscall boundary.

    No user-space boundary reproduces "write allowed, chmod denied" on this
    host (chattr +i is EPERM, no read-only tmpfs available), so this stubs
    only `os.chmod` — the smallest possible boundary, same class as the
    httpx transport mock. The target must stay intact and no staged temp
    may remain.
    """
    import dcode_harmony.tools.apply_patch as ap

    target = tmp_path / "a.txt"
    target.write_text("old\n", encoding="utf-8")

    def _chmod_boom(path, mode, **kwargs):
        raise OSError("simulated chmod failure")

    target.chmod(0o755)
    monkeypatch.setattr(ap.os, "chmod", _chmod_boom)
    patch = """*** Begin Patch
*** Update File: a.txt
@@
-old
+new
*** End Patch
"""
    with pytest.raises(OSError, match="simulated chmod failure"):
        apply_patch_text(patch, workspace=tmp_path)
    monkeypatch.undo()
    leftovers = [p.name for p in tmp_path.iterdir() if ".dcode-tmp-" in p.name]
    assert leftovers == []
    assert target.read_text(encoding="utf-8") == "old\n"
