# ADR-0006: Repository-native agent governance and context supply chain

- Status: accepted
- Date: 2026-07-23

## Context

ORNA Atlas has privacy, playback, transaction, migration and media-lifecycle invariants that span
several layers. Developers and coding agents need those constraints before editing, but one large
prompt is difficult to review, consumes irrelevant context and drifts from the code. Chat history,
personal tool configuration and undocumented conventions are not durable or available to every
contributor.

Reusable workflows also need regression evidence. Application tests prove product behavior, but do
not by themselves detect broken context routing, incomplete role boundaries, placeholder skills or
agent instructions that recommend a forbidden shortcut.

## Decision

Developer and agent governance is versioned in the repository and follows a progressive context
supply chain:

1. Root `AGENTS.md` is the concise operational entry point and defines truth order, invariants,
   forbidden actions, checks and handoff requirements.
2. `docs/ARCHITECTURE.md` remains the single canonical target architecture. Focused companions in
   `docs/architecture/` provide navigation, current repository boundaries and context routing
   without copying the canonical design.
3. `docs/CURRENT_STATE.md`, `docs/DOMAIN_RULES.md`, accepted ADRs and accepted specs supply current
   facts, normative rules, durable decisions and task-level acceptance context respectively.
4. `.agents/roles/` defines specialist inputs, outputs and boundaries. `.agents/skills/` contains
   small reusable workflows for recurring operations. Neither can override the root contract,
   domain rules, accepted ADRs, user scope or security policy.
5. `specs/` stores reviewable scope and acceptance behavior for ambiguous or cross-layer changes. A
   spec is never evidence that a capability is implemented.
6. Deterministic repository checks validate architecture/governance structure, and `evals/`
   registers representative architecture, prompt, UI and performance scenarios. These evals
   supplement, not replace, normal unit, contract, integration, migration and browser tests.
7. The final PR handoff closes the chain with changed boundaries, invariant/acceptance evidence,
   checks, migration/contract/docs impact, security considerations and residual risk.

Context is loaded progressively: global contract first, then only the relevant architecture route,
role, domain rule, ADR/spec, code and tests. External conversations become durable context only
after their decisions or acceptance criteria are reviewed into an authoritative repository artifact.

## Consequences

- Governance changes are diffable, reviewable and available in local, CI and agent environments.
- Contributors can find focused context without loading the whole documentation set, while
  handoffs remain reproducible after a tool session ends.
- Skills and role contracts have explicit trust boundaries and can be evaluated for common safe
  workflows and forbidden shortcuts.
- Maintainers must keep links, roles, skills and eval fixtures synchronized when invariants or
  repository layout changes. Structural checks may add small CI maintenance and runtime cost.
- Passing an agent eval proves only the encoded governance scenario; it cannot establish product
  correctness, security completeness or production readiness.
- Overly detailed global guidance is treated as context debt and should move to the narrowest
  authoritative companion.

## Rejected alternatives

- **One comprehensive root prompt:** easy to start, but difficult to keep concise, route selectively
  or test by concern.
- **Tool- or account-local instructions only:** not reliably available to all contributors and not
  reviewed with the code they affect.
- **A second architecture tree for agents:** creates competing canonical sources and target/current
  ambiguity.
- **Skills without deterministic evals or human handoff:** makes workflow drift invisible and
  encourages unverified completion claims.
- **Application tests as the only governance check:** they do not exercise instruction discovery,
  role routing or safe workflow recommendations.

## Rollback

Supersede this ADR before changing the governance model. Optional roles, skills or eval cases may be
retired only after their indexes, checks and CI references are removed in the same change. Retiring
developer tooling does not alter application behavior, domain invariants or the canonical status of
`docs/ARCHITECTURE.md`.
