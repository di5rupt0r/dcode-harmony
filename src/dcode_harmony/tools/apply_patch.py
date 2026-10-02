"""Safe GPT-OSS compatible apply_patch implementation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


class PatchError(ValueError):
    """Raised when a patch cannot be parsed or safely applied."""


@dataclass(frozen=True)
class Operation:
    kind: str
    path: str
    lines: tuple[str, ...] = ()


def _resolve_workspace_path(workspace: Path, relative_path: str) -> Path:
    path = Path(relative_path)
    if path.is_absolute():
        raise PatchError(f"Refusing absolute path: {relative_path}")
    candidate = workspace / path
    workspace_resolved = workspace.resolve()
    if any(part == ".." for part in path.parts):
        raise PatchError(f"Refusing path outside workspace: {relative_path}")
    parent = candidate.parent.resolve()
    if not str(parent).startswith(f"{workspace_resolved}{Path('/')}") and parent != workspace_resolved:
        raise PatchError(f"Refusing path outside workspace: {relative_path}")
    return candidate


def _ensure_no_symlink_escape(workspace: Path, path: Path) -> None:
    workspace_resolved = workspace.resolve()
    current = path
    while current != workspace_resolved and current != current.parent:
        if current.exists() and current.is_symlink():
            target = current.resolve()
            if not str(target).startswith(f"{workspace_resolved}{Path('/')}") and target != workspace_resolved:
                raise PatchError(f"Refusing symlink escape: {current}")
        current = current.parent


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
            payload = []
            while i < len(lines) - 1 and not lines[i].startswith("*** "):
                payload.append(lines[i])
                i += 1
            if not any(item.startswith("@@") for item in payload):
                raise PatchError("Malformed update operation")
            ops.append(Operation("update", path, tuple(payload)))
            continue
        raise PatchError(f"Malformed patch header: {line}")
    if not ops:
        raise PatchError("Malformed patch: no operations")
    return ops


def _find_subsequence(haystack: list[str], needle: list[str], start: int) -> int:
    if not needle:
        return start
    last = len(haystack) - len(needle)
    for idx in range(start, last + 1):
        if haystack[idx : idx + len(needle)] == needle:
            return idx
    raise PatchError("Malformed update hunk: context not found")


def _apply_update(original: str, patch_lines: Iterable[str]) -> str:
    source = original.splitlines()
    out = source[:]
    cursor = 0
    current_hunk: list[str] = []

    def apply_hunk(hunk: list[str]) -> None:
        nonlocal out, cursor
        if not hunk:
            return
        for line in hunk:
            if not line or line[0] not in {" ", "+", "-"}:
                raise PatchError("Malformed update hunk lines")
        old_chunk = [line[1:] for line in hunk if line[0] in {" ", "-"}]
        new_chunk = [line[1:] for line in hunk if line[0] in {" ", "+"}]
        at = _find_subsequence(out, old_chunk, cursor)
        out = out[:at] + new_chunk + out[at + len(old_chunk) :]
        cursor = at + len(new_chunk)

    for line in patch_lines:
        if line.startswith("@@"):
            apply_hunk(current_hunk)
            current_hunk = []
            continue
        current_hunk.append(line)
    apply_hunk(current_hunk)
    return "".join(f"{line}\n" for line in out)


def apply_patch_text(patch: str, *, workspace: Path) -> str:
    """Apply custom patch grammar under a workspace boundary."""
    operations = _parse_patch(patch)
    results: list[str] = []
    for op in operations:
        path = _resolve_workspace_path(workspace, op.path)
        _ensure_no_symlink_escape(workspace, path)
        if op.kind == "add":
            if path.exists():
                raise PatchError(f"Cannot add existing file: {op.path}")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("".join(f"{line}\n" for line in op.lines), encoding="utf-8")
            results.append(f"Added {op.path}")
            continue
        if op.kind == "delete":
            if not path.exists():
                raise PatchError(f"Cannot delete missing file: {op.path}")
            path.unlink()
            results.append(f"Deleted {op.path}")
            continue
        if op.kind == "update":
            if not op.lines:
                raise PatchError("Malformed update operation")
            if not path.exists():
                raise PatchError(f"Cannot update missing file: {op.path}")
            original = path.read_text(encoding="utf-8")
            updated = _apply_update(original, op.lines)
            path.write_text(updated, encoding="utf-8")
            results.append(f"Updated {op.path}")
            continue
        raise PatchError(f"Unsupported operation: {op.kind}")
    return "\n".join(results)
