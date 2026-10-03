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
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path


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


def _find_hunk_position(
    haystack: list[str], needle: list[str], start: int, *, require_eof: bool = False
) -> int:
    if not needle:
        if require_eof:
            return len(haystack)
        return start
    matches = [
        idx
        for idx in range(start, len(haystack) - len(needle) + 1)
        if haystack[idx : idx + len(needle)] == needle
    ]
    if require_eof:
        matches = [idx for idx in matches if idx + len(needle) == len(haystack)]
    if not matches:
        if require_eof:
            raise PatchError("Update context not anchored at end of file")
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


def _apply_update(
    original: str, patch_lines: Iterable[str], *, end_of_file: bool
) -> str:
    newline = _detect_newline(original)
    has_trailing = original.endswith(("\n", "\r"))
    source = original.splitlines()
    out = source[:]
    cursor = 0

    hunks: list[list[str]] = []
    current: list[str] = []
    for line in patch_lines:
        if line.startswith("@@"):
            if current:
                hunks.append(current)
                current = []
            continue
        current.append(line)
    if current:
        hunks.append(current)

    for index, hunk in enumerate(hunks):
        require_eof = end_of_file and index == len(hunks) - 1
        for line in hunk:
            if not line or line[0] not in {" ", "+", "-"}:
                raise PatchError("Malformed update hunk lines")
        old_chunk = [line[1:] for line in hunk if line[0] in {" ", "-"}]
        new_chunk = [line[1:] for line in hunk if line[0] in {" ", "+"}]
        at = _find_hunk_position(out, old_chunk, cursor, require_eof=require_eof)
        out = out[:at] + new_chunk + out[at + len(old_chunk) :]
        cursor = at + len(new_chunk)
    body = newline.join(out)
    if has_trailing:
        body += newline
    return body


def _mode_of(path: Path) -> int | None:
    try:
        import stat as _stat

        return _stat.S_IMODE(os.stat(path).st_mode)
    except OSError:
        return None


@dataclass
class _PlannedOp:
    op: Operation
    source: Path
    target: Path
    new_bytes: bytes | None  # None means delete
    original_bytes: bytes | None
    original_mode: int | None = None  # permission bits of source before patch


def _plan(patch: str, workspace: Path) -> list[_PlannedOp]:
    if not workspace.exists() or not workspace.is_dir():
        raise PatchError(f"Workspace does not exist: {workspace}")
    operations = _parse_patch(patch)
    planned: list[_PlannedOp] = []
    # Virtual workspace state: path -> bytes (or None when absent), so that
    # later operations on the same path compose with earlier planned ones.
    state: dict[Path, bytes | None] = {}

    def _read(path: Path) -> bytes | None:
        if path in state:
            return state[path]
        if path.is_symlink():
            return None
        if path.exists() and path.is_file():
            return path.read_bytes()
        return None

    for op in operations:
        source = _resolve_workspace_path(workspace, op.path)
        _check_path_safety(workspace, source)
        target = source
        if op.move_to is not None:
            target = _resolve_workspace_path(workspace, op.move_to)
            _check_path_safety(workspace, target)
            dst_known = _read(target)
            if (
                dst_known is not None
                or (target not in state and target.exists())
                or target.is_symlink()
            ):
                raise PatchError(f"move destination already exists: {op.move_to}")
        if op.kind == "add":
            if _read(source) is not None or (
                source not in state and (source.exists() or source.is_symlink())
            ):
                raise PatchError(f"Cannot add existing file: {op.path}")
            new_bytes = ("\n".join(op.lines) + ("\n" if op.lines else "")).encode(
                "utf-8"
            )
            planned.append(_PlannedOp(op, source, target, new_bytes, None))
            state[source] = new_bytes
            continue
        if op.kind == "delete":
            original = _read(source)
            if original is None and not source.exists():
                raise PatchError(f"Cannot delete missing file: {op.path}")
            if source.exists() and source.is_dir():
                raise PatchError(f"Cannot delete directory: {op.path}")
            planned.append(
                _PlannedOp(op, source, target, None, original, _mode_of(source))
            )
            state[source] = None
            continue
        if op.kind == "update":
            if not op.lines:
                raise PatchError("Malformed update operation")
            original = _read(source)
            if original is None:
                raise PatchError(f"Cannot update missing file: {op.path}")
            try:
                text = original.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise PatchError(f"Cannot update non-UTF-8 file: {op.path}") from exc
            updated = _apply_update(text, op.lines, end_of_file=op.end_of_file)
            planned.append(
                _PlannedOp(
                    op,
                    source,
                    target,
                    updated.encode("utf-8"),
                    original,
                    _mode_of(source),
                )
            )
            if target != source:
                state[target] = updated.encode("utf-8")
                state[source] = None
            else:
                state[source] = updated.encode("utf-8")
            continue
        raise PatchError(f"Unsupported operation: {op.kind}")
    for item in planned:
        if item.new_bytes is None:
            continue  # deletes only unlink
        probe = item.target.parent
        while not probe.exists():
            probe = probe.parent
        if not os.access(probe, os.W_OK):
            raise PatchError(
                f"Parent directory not writable: {probe} (needed for {item.target})"
            )
    return planned


def _open_parent_fd(path: Path) -> int:
    try:
        return os.open(path.parent, os.O_RDONLY)
    except FileNotFoundError as exc:
        raise PatchError(f"Parent directory does not exist: {path.parent}") from exc


def _write_bytes_secure(path: Path, data: bytes, mode: int | None = None) -> None:
    """Write fully to a temp file in the same directory, then atomically
    replace the target. A failed write never leaves a truncated target.
    `mode` (permission bits) is applied to the staged file before replace
    so the target keeps its mode across updates and rollback."""
    dir_fd = _open_parent_fd(path)
    tmp_name = f".dcode-tmp-{os.getpid()}-{os.urandom(4).hex()}"
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
        fd = os.open(tmp_name, flags, 0o644, dir_fd=dir_fd)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
        except Exception:
            try:
                os.close(fd)
            except OSError:
                pass
            try:
                os.unlink(tmp_name, dir_fd=dir_fd)
            except OSError:
                pass
            raise
        if mode is not None:
            os.chmod(tmp_name, mode, dir_fd=dir_fd)
        try:
            os.replace(tmp_name, path.name, src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
        except Exception:
            try:
                os.unlink(tmp_name, dir_fd=dir_fd)
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
    created_dirs: list[Path] = []
    try:
        for item in planned:
            path = item.source
            target = item.target
            parent = target.parent
            missing_parents = []
            probe = parent
            while not probe.exists():
                missing_parents.append(probe)
                probe = probe.parent
            if item.op.kind == "add":
                parent.mkdir(parents=True, exist_ok=True)
                created_dirs.extend(missing_parents)
                _write_bytes_secure(
                    target, item.new_bytes or b"", mode=item.original_mode
                )
                applied.append(item)
                results.append(f"Added {item.op.path}")
            elif item.op.kind == "delete":
                _unlink_secure(path)
                applied.append(item)
                results.append(f"Deleted {item.op.path}")
            else:
                parent.mkdir(parents=True, exist_ok=True)
                created_dirs.extend(missing_parents)
                _write_bytes_secure(
                    target, item.new_bytes or b"", mode=item.original_mode
                )
                applied.append(item)
                if target != path:
                    try:
                        _unlink_secure(path)
                    except OSError:
                        _unlink_secure(target)
                        if item.original_bytes is not None:
                            _write_bytes_secure(
                                path, item.original_bytes, mode=item.original_mode
                            )
                        applied.pop()
                        raise
                    results.append(f"Updated {item.op.path} -> {item.op.move_to}")
                else:
                    results.append(f"Updated {item.op.path}")
    except Exception:
        for item in reversed(applied):
            try:
                if item.op.kind == "add":
                    if item.target.exists():
                        _unlink_secure(item.target)
                elif item.op.kind == "delete":
                    if item.original_bytes is not None:
                        _write_bytes_secure(
                            item.source, item.original_bytes, mode=item.original_mode
                        )
                else:
                    if item.target != item.source and item.target.exists():
                        _unlink_secure(item.target)
                    if item.original_bytes is not None:
                        _write_bytes_secure(
                            item.source, item.original_bytes, mode=item.original_mode
                        )
            except OSError:
                pass
        # Remove directories the patch created (deepest first, only if empty).
        for directory in sorted(created_dirs, key=lambda p: len(p.parts), reverse=True):
            try:
                directory.rmdir()
            except OSError:
                pass
        raise
    return "\n".join(results)
