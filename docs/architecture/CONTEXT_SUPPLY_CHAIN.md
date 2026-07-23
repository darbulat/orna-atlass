# Repository context supply chain

The developer platform keeps operational context reviewable beside the code. Its purpose is to
supply the smallest trustworthy context for a change and produce evidence that survives a chat or
tool session.

## Flow

```text
task request
  -> AGENTS.md (global contract and truth order)
  -> architecture/domain/current-state indexes (relevant facts and invariants)
  -> accepted spec + ADRs (change intent and durable decisions)
  -> specialist role + optional skill (bounded workflow)
  -> code/migration/contracts/tests (implementation evidence)
  -> repository checks + agent eval cases (governance regression evidence)
  -> PR handoff (human-reviewable outcome, checks and risks)
```

Each step narrows context. A role or skill may add technique, but may not override an upstream
invariant, expand task authorization, or turn planned behavior into a runtime fact.

## Artifact responsibilities

| Artifact | Responsibility | Not a substitute for |
| --- | --- | --- |
| `AGENTS.md` | short repository-wide operating contract | domain design detail or a task spec |
| `docs/architecture/` | navigation, ownership and dependency companions | canonical `docs/ARCHITECTURE.md` |
| `docs/CURRENT_STATE.md` | tested implementation summary and known limits | executable evidence |
| `docs/DOMAIN_RULES.md` | business, privacy and lifecycle invariants | implementation or migration |
| `docs/adr/` | accepted durable cross-module decisions | routine implementation notes |
| `specs/` | reviewable scope and acceptance behavior for a change | proof that the change shipped |
| `.agents/roles/` | specialist inputs, outputs and boundaries | authority to mutate outside task scope |
| `.agents/skills/` | repeatable, task-specific workflows | the root contract or human review |
| `evals/` | registered deterministic cases that catch governance/skill drift | application unit/integration/e2e tests |

## Loading rules

1. Start with `AGENTS.md`; do not preload every long design document.
2. Select a route from `docs/architecture/README.md` and a role from `.agents/roles/README.md`.
3. Read the authoritative source for each claim and inspect the corresponding code/test before
   relying on it.
4. Use one accepted spec for the task. If none is needed, keep acceptance behavior in the issue/PR.
5. Invoke only skills that match the bounded operation. Treat skill output as a draft until verified.
6. Record conflicts, missing evidence and skipped checks in the final handoff.

## Deterministic assembly

`.agents/context-map.toml` is the reviewed routing policy. Build a path manifest or self-contained
Markdown bundle with the standard-library-only CLI:

```bash
python3 scripts/build_agent_context.py \
  "Harden playback grants" \
  --role security \
  --changed-path orna_atlas/app/modules/media/service.py \
  --format markdown
```

Selection is stable and budgeted. It keeps `AGENTS.md`, `docs/CURRENT_STATE.md` and the selected role
contract first, then reserves matched domain rules, ADRs and workflow guidance before explicit
changed/target source files and broader domain patterns. Oversized source sets may be truncated, but
matched invariant files are not displaced by them.

Every requested or mapped file must resolve to allowlisted UTF-8 text inside the repository. The
builder rejects traversal, all symlink paths, secret/credential names, build/cache directories,
binary data and paths over the hard file/byte limits. Validate the complete map and every referenced
file with `python3 scripts/build_agent_context.py --check`; CI runs the same contract as a fast eval.

External conversations, copied prompts and tool memory can clarify a request, but they are not part
of the durable supply chain until their decision or acceptance criteria are reviewed into a spec,
ADR or authoritative repository document.

## Evaluation and maintenance

Agent eval cases exercise representative requests and forbidden shortcuts against repository-owned
expectations. They should be deterministic, contain no production credentials or network
dependency, and fail with an actionable explanation. Application behavior remains covered by the
normal Python, integration, frontend and browser suites.

When a governance artifact changes:

- update direct indexes and references;
- add or adjust an eval case for a newly important instruction or skill behavior;
- run architecture/governance checks plus the relevant application tests;
- review whether the root contract remains concise and whether a detail should move to a focused
  companion, role, skill or spec instead.

This supply chain and its trade-offs are recorded in
[`ADR-0006`](../adr/0006-repository-native-agent-governance.md).
