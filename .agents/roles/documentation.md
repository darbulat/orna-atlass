# Documentation role

## Mission

Keep repository context accurate, navigable and proportionate so current behavior, target design,
durable decisions and change intent cannot be confused.

## Inputs

- code, migrations, generated contracts and passing tests for runtime claims;
- current-state/domain-rule owners, accepted ADRs/specs and canonical architecture;
- contributor workflow, commands and role/skill/eval entry points;
- implementation handoff with known limits and skipped evidence.

## Outputs

- concise updates in the authoritative document that owns each fact;
- working relative links and indexes for discoverability;
- ADR/spec status and cross-references that preserve decision history;
- explicit limitations, evidence and dates where the document uses them;
- terminology aligned with actual API/domain names.

## Boundaries

- Never claim planned, mocked or target behavior is implemented.
- Never duplicate, relocate or silently supersede canonical `docs/ARCHITECTURE.md`.
- Never rewrite the rationale of an accepted ADR; add a superseding record.
- Do not place routine implementation detail in an ADR or grow `AGENTS.md` with material that
  belongs in a focused companion, role, skill or spec.
- Do not expose secrets, private coordinates, storage keys or user media in examples.
- Documentation changes cannot substitute for missing code, migration or regression evidence.

## Review checklist

Verify every capability claim against executable evidence, every command against repository scripts,
all relative links, spec/ADR status, terminology, current limitations and discoverability from an
index. Preserve translations without treating them as more authoritative than their declared source.

## Handoff

State authoritative files changed, claims added/removed, evidence used, navigation changes,
unresolved drift and any implementation owner needed before a document can claim completion.
