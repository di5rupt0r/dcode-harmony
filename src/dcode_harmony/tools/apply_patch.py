"""Safe GPT-OSS compatible apply_patch implementation.

Patch grammar (subset of the GPT-OSS ``*** Begin Patch`` format)::

    *** Begin Patch
    *** Add File: path
    +line
    *** Delete File: path
    *** Update File: path
    *** Move to: new-path
    @@
     context
    -old
    +new
    *** End of File
    *** End Patch

Safety properties:

- paths are confined to the workspace; absolute paths, ``..`` traversal and
  symlink escapes (including in-workspace symlinks) are rejected;
- every operation is validated (and the new content fully computed) before
  any write, and any runtime failure rolls back earlier writes;
- file bytes are written with ``dir_fd`` + ``O_NOFOLLOW`` so a symlink
  swapped in mid-operation cannot redirect the write.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


class PatchError(ValueError):
    """Raised when a patch cannot be parsed or safely applied."""


@dataclass(frozen=True)
class Operation:
    kind: str
    path: str
    lines: tuple[str, ...] = ()
    move_to: str | None = None
    end_of_file: bool = False


def _resolve_workspace_path(workspace: Path, relative_path: str) -> Path:
    path = Path(relative_path)
    if path.is_absolute():
        raise PatchError(f"Refusing absolute path: {relative_path}")
    if any(part == ".." for part in path.parts):
        raise PatchError(f"Refusing path outside workspace: {relative_path}")
    candidate = workspace / path
    workspace_resolved = workspace.resolve()
    parent = candidate.parent.resolve()
    if parent != workspace_resolved and workspace_resolved not in parent.parents:
        raise PatchError(f"Refusing path outside workspace: {relative_path}")
    return candidate


def _check_path_safety(workspace: Path, path: Path) -> None:
    workspace_resolved = workspace.resolve()
    current = path
    while True:
        if current.is_symlink():
            raise PatchError(f"Refusing symlink in patch path: {current}")
        if current == workspace_resolved or current == current.parent:
            break
        current = current.parent
    # The parent chain must stay inside the workspace after resolution.
    parent = path.parent.resolve()
    if parent != workspace_resolved and workspace_resolved not in parent.parents:
        raise PatchError(f"Refusing path outside workspace: {path}")


def _parse_patch(patch: str) -> list[Operation]:
    lines = patch.splitlines()
    if not lines or lines[0] != "*** Begin Patch" or lines[-1] != "*** End Patch":
        raise PatchError("Malformed patch envelope")
    ops: list[Operation] = []
    i = 1
    while i < len(lines) - 1:
        line = lines[i]
        if line.startswith("*** Add File: "):
            path = line.removeprefix("*** Add File: ")
            i += 1
            payload: list[str] = []
            while i < len(lines) - 1 and not lines[i].startswith("*** "):
                if not lines[i].startswith("+"):
                    raise PatchError("Malformed add-file hunk")
                payload.append(lines[i][1:])
                i += 1
            ops.append(Operation("add", path, tuple(payload)))
            continue
        if line.startswith("*** Delete File: "):
            path = line.removeprefix("*** Delete File: ")
            ops.append(Operation("delete", path))
            i += 1
            continue
        if line.startswith("*** Update File: "):
            path = line.removeprefix("*** Update File: ")
            i += 1
            move_to = None
            if i < len(lines) - 1 and lines[i].startswith("*** Move to: "):
                move_to = lines[i].removeprefix("*** Move to: ")
                i += 1
            payload = []
            end_of_file = False
            while i < len(lines) - 1 and not lines[i].startswith("*** "):
                payload.append(lines[i])
                i += 1
            # Accept "*** End of File" as a trailing marker after the hunks.
            if i < len(lines) - 1 and lines[i] == "*** End of File":
                end_of_file = True
                i += 1
            if not any(item.startswith("@@") for item in payload):
                raise PatchError("Malformed update operation")
            ops.append(Operation("update", path, tuple(payload), move_to, end_of_file))
            continue
        if line == "*** End of File":
            i += 1
            continue
        raise PatchError(f"Malformed patch header: {line}")
    if not ops:
        raise PatchError("Malformed patch: no operations")
    return ops


def _find_hunk_position(haystack: list[str], needle: list[str], start: int) -> int:
    if not needle:
        return start
    matches = [
        idx
        for idx in range(start, len(haystack) - len(needle) + 1)
        if haystack[idx : idx + len(needle)] == needle
    ]
    if not matches:
        raise PatchError("Malformed update hunk: context not found")
    if len(matches) > 1:
        raise PatchError("ambiguous context")
    return matches[0]


def _detect_newline(text: str) -> str:
    if "\r\n" in text:
        return "\r\n"
    if "\r" in text:
        return "\r"
    return "\n"


def _apply_update(original: str, patch_lines: Iterable[str], *, end_of_file: bool) -> str:
    newline = _detect_newline(original)
    has_trailing = original.endswith(("\n", "\r"))
    source = original.splitlines()
    out = source[:]
    cursor = 0
    current_hunk: list[str] = []
    last_match_end_at_eof = False

    def apply_hunk(hunk: list[str]) -> None:
        nonlocal out, cursor, last_match_end_at_eof
        if not hunk:
            return
        for line in hunk:
            if not line or line[0] not in {" ", "+", "-"}:
                raise PatchError("Malformed update hunk lines")
        old_chunk = [line[1:] for line in hunk if line[0] in {" ", "-"}]
        new_chunk = [line[1:] for line in hunk if line[0] in {" ", "+"}]
        at = _find_hunk_position(out, old_chunk, cursor)
        last_match_end_at_eof = at + len(old_chunk) == len(out)
        out = out[:at] + new_chunk + out[at + len(old_chunk) :]
        cursor = at + len(new_chunk)

    for line in patch_lines:
        if line.startswith("@@"):
            apply_hunk(current_hunk)
            current_hunk = []
            continue
        current_hunk.append(line)
    apply_hunk(current_hunk)
    if end_of_file and not last_match_end_at_eof:
        raise PatchError("Update context not anchored at end of file")
    body = newline.join(out)
    if has_trailing:
        body += newline
    return body


@dataclass
class _PlannedOp:
    op: Operation
    source: Path
    target: Path
    new_bytes: bytes | None  # None means delete
    original_bytes: bytes | None


def _plan(patch: str, workspace: Path) -> list[_PlannedOp]:
    if not workspace.exists() or not workspace.is_dir():
        raise PatchError(f"Workspace does not exist: {workspace}")
    operations = _parse_patch(patch)
    planned: list[_PlannedOp] = []
    for op in operations:
        source = _resolve_workspace_path(workspace, op.path)
        _check_path_safety(workspace, source)
        target = source
        if op.move_to is not None:
            target = _resolve_workspace_path(workspace, op.move_to)
            _check_path_safety(workspace, target)
        if op.kind == "add":
            if source.exists() or source.is_symlink():
                raise PatchError(f"Cannot add existing file: {op.path}")
            new_bytes = ("\n".join(op.lines) + ("\n" if op.lines else "")).encode("utf-8")
            planned.append(_PlannedOp(op, source, target, new_bytes, None))
            continue
        if op.kind == "delete":
            if not source.exists() and not source.is_symlink():
                raise PatchError(f"Cannot delete missing file: {op.path}")
            if source.is_dir():
                raise PatchError(f"Cannot delete directory: {op.path}")
            planned.append(_PlannedOp(op, source, target, None, source.read_bytes()))
            continue
        if op.kind == "update":
            if not op.lines:
                raise PatchError("Malformed update operation")
            if not source.exists() or source.is_symlink():
                raise PatchError(f"Cannot update missing file: {op.path}")
            original = source.read_bytes()
            try:
                text = original.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise PatchError(f"Cannot update non-UTF-8 file: {op.path}") from exc
            updated = _apply_update(text, op.lines, end_of_file=op.end_of_file)
            planned.append(_PlannedOp(op, source, target, updated.encode("utf-8"), original))
            continue
        raise PatchError(f"Unsupported operation: {op.kind}")
    return planned


def _open_parent_fd(path: Path) -> int:
    try:
        return os.open(path.parent, os.O_RDONLY)
    except FileNotFoundError as exc:
        raise PatchError(f"Parent directory does not exist: {path.parent}") from exc


def _write_bytes_secure(path: Path, data: bytes) -> None:
    dir_fd = _open_parent_fd(path)
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW
        fd = os.open(path.name, flags, 0o644, dir_fd=dir_fd)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
        except Exception:
            try:
                os.close(fd)
            except OSError:
                pass
            raise
    finally:
        os.close(dir_fd)


def _unlink_secure(path: Path) -> None:
    dir_fd = _open_parent_fd(path)
    try:
        os.unlink(path.name, dir_fd=dir_fd)
    finally:
        os.close(dir_fd)


def _rename_secure(src: Path, dst: Path) -> None:
    src_fd = _open_parent_fd(src)
    dst_fd = _open_parent_fd(dst)
    try:
        os.rename(src.name, dst.name, src_dir_fd=src_fd, dst_dir_fd=dst_fd)
    finally:
        os.close(src_fd)
        os.close(dst_fd)


def apply_patch_text(patch: str, *, workspace: Path) -> str:
    """Apply patch grammar under a workspace boundary.

    All operations are validated and new contents computed before any write;
    a failure at any point rolls earlier writes back.
    """
    planned = _plan(patch, workspace)
    results: list[str] = []
    applied: list[_PlannedOp] = []
    try:
        for item in planned:
            path = item.source
            target = item.target
            if item.op.kind == "add":
                target.parent.mkdir(parents=True, exist_ok=True)
                _write_bytes_secure(target, item.new_bytes or b"")
                results.append(f"Added {item.op.path}")
            elif item.op.kind == "delete":
                _unlink_secure(path)
                results.append(f"Deleted {item.op.path}")
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                _write_bytes_secure(target, item.new_bytes or b"")
                if target != path:
                    _unlink_secure(path)
                    results.append(f"Updated {item.op.path} -> {item.op.move_to}")
                else:
                    results.append(f"Updated {item.op.path}")
            applied.append(item)
    except Exception:
        for item in reversed(applied):
            try:
                if item.op.kind == "add":
                    if item.target.exists():
                        _unlink_secure(item.target)
                elif item.op.kind == "delete":
                    if item.original_bytes is not None:
                        _write_bytes_secure(item.source, item.original_bytes)
                else:
                    if item.target != item.source and item.target.exists():
                        _unlink_secure(item.target)
                    if item.original_bytes is not None:
                        _write_bytes_secure(item.source, item.original_bytes)
            except OSError:
                pass
        raise
    return "\n".join(results)
