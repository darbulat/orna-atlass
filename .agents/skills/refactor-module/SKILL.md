---
name: refactor-module
description: "Refactor ORNA Atlas backend or frontend modules without changing observable behavior. Use for splitting large files, extracting helpers, clarifying layer boundaries, reducing duplication, or reorganizing Python and TypeScript code."
---

# Refactor an ORNA Module

## Freeze behavior

1. Read `AGENTS.md`, `docs/CURRENT_STATE.md`, relevant domain rules, and the target module's callers and tests.
2. Define the preserved API, database, side-effect, logging, error, accessibility, and concurrency behavior.
3. Add characterization coverage for any behavior not already protected.
4. Bound the refactor and preserve unrelated worktree changes.

## Move code safely

- Keep backend flow as router -> service -> repository -> model and keep integration calls behind their existing boundaries.
- Keep every transaction service-owned, preserve intentional durable phase boundaries and never
  move `commit()` into repositories.
- Extract pure policy, validation, mapping, and formatting functions before moving stateful orchestration.
- Preserve explicit public DTO allowlists, coordinate privacy, access policy, idempotency, cache timing, and truthful failures.
- Preserve generated API types and established typed clients; treat a contract or schema change as a separate behavior change.
- Preserve server/client component boundaries, global player ownership, shared authentication refresh, request-race handling, and accessibility semantics.
- Prefer small compile- and test-green moves; avoid compatibility shims that create two sources of truth.
- Avoid circular imports, hidden global state, broader exports, and speculative abstractions.

## Verify equivalence

1. Run the closest characterization test after each meaningful extraction.
2. Run `python -m pytest` and `python -m ruff check .` for Python changes.
3. Run `cd web && npm run typecheck && npm run lint` plus affected frontend tests for TypeScript changes.
4. Run integration or Playwright checks when the refactor crosses those boundaries.
5. Inspect the final diff for accidental contract, migration, query-count, side-effect-order, or user-copy changes.
6. Leave `docs/CURRENT_STATE.md` unchanged unless observable capability or limitation actually changes.
