# Design decisions

> Explanation. The "why" behind the current shape.

- **Published packages over vendoring**: install `deepagents-code` +
  pinned `deepagents` rather than cloning the upstream monorepo, so the
  project stays small and reproducible.
- **Native Harmony tokens, not JSON**: prompts are built with
  `render_conversation_for_completion` and completions are parsed with
  `parse_messages_from_completion_tokens` (and `StreamableParser` for SSE).
  JSON-envelope parsing was removed because it hid real parse paths.
- **Tokens are authoritative**: SSE events carry `index/content/tokens/stop`;
  `return_tokens=true` endpoint is the contract. The stream ends with
  `stop: true` — there is no `data: [DONE]` sentinel from llama-server.
- **`apply_patch` is mandatory**: the agent must have a safe patch mechanism
  on day one; the GPT-OSS grammar is the only accepted format to match the
  model's training.
- **Analysis channel never leaks**: reasoning content is parsed but not
  emitted as visible chunks; tool calls surface as complete chunks on close.
- **Document → test → implement**: every fix follows this order; live
  validation is only claimed when a real server was used.
