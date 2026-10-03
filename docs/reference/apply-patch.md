# apply_patch tool

> Reference.

- Tool name is exactly `apply_patch`; single argument `patch: str`. Paths
  live inside the patch text.
- Accepts only the GPT-OSS `*** Begin Patch` grammar (Add/Update/Delete,
  optional `*** Move to:`, `@@` hunks, `*** End of File`). Unified diff is
  **rejected** — that would diverge from what GPT-OSS is trained to emit.
- Absolute paths, `../` traversal, and symlinks (escaping or not) are
  rejected; writes use `dir_fd` + `O_NOFOLLOW`.
- All operations validate before any write; failures roll back earlier
  writes. Writes are atomic (temp file + `os.replace`), preserve permission
  bits, and leave no `.dcode-tmp-*` files.
- Ambiguous hunk context is rejected (`ambiguous context`) unless the
  anchor disambiguates (`@@` header or `*** End of File`).

TOCTOU scope: parent directories are opened by path, not walked fd-by-fd.
The tool defends against a symlinked final component and a symlinked parent
at validation time, but does **not** resist an attacker concurrently
swapping an intermediate directory between validation and `open`. Running
patches in a private workspace is the expected boundary; do not treat this
tool as a security boundary against a hostile local process.
