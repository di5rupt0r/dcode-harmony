# Agent instructions (permanent)

This repository is developed by **multiple coding agents**. Handoff must be frictionless. These rules are mandatory for every agent session and cannot be skipped because a chat prompt omitted them.

## Required workflow order

For every fix or feature, do the work in this order only:

1. **Document first**
   - Update `HANDOFF.md` with intent, decisions, verified APIs, and what is in/out of scope.
   - Update `MILESTONES.md` acceptance criteria and status honestly before writing code.
   - Do not implement undocumented work.

2. **Tests second**
   - Write a **failing** test for every fix or feature before implementation.
   - Prefer real boundaries (filesystem, Harmony encoding). Mock only external I/O such as HTTP transport.
   - Run the new test and confirm it fails for the right reason.

3. **Implement third**
   - Smallest change that makes the failing test pass.
   - Match existing Python style: 4-space indent, double quotes, `from __future__ import annotations`.
   - Before using third-party APIs (`openai-harmony`, llama-server, `deepagents_code`), check the **installed** package or upstream README. Do not guess API names.

4. **Commit and push granularly**
   - Commit after each coherent unit (docs, then tests, then implementation, then follow-up docs).
   - Prefer small, reviewable commits over one large batch.
   - Push to `origin` so other agents never work from stale local-only state.

## Scope discipline

- Do not expand a PR whose scope is already fixed.
- Out-of-scope milestones stay `TODO` in `MILESTONES.md` and get their own follow-up issue/PR.
- Do not claim live validation unless a live server was actually used.

## Before / after checklist

**Before changing code:** read `AGENTS.md`, `HANDOFF.md`, `README.md`, and `MILESTONES.md`.

**After changing code:** run `pytest -m "not live"`, report real pass/fail counts, update milestone status, and leave a single clear session entry in `HANDOFF.md` (no long "picked up where X left off" logs).

Cursor agents also load `.cursor/rules/agent-handoff.mdc` (`alwaysApply: true`). Keep that file aligned with this document.
