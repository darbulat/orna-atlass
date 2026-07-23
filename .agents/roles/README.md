# Specialist role contracts

Roles define bounded responsibilities for planning, implementation and review. They are routing
context, not separate authority: every role follows root `AGENTS.md`, task scope, domain rules and
accepted ADRs.

| Role | Route when | Contract |
| --- | --- | --- |
| Architect | a decision crosses modules/layers, changes boundaries or needs an ADR | [`architect.md`](architect.md) |
| Backend | FastAPI, services, repositories, models, migrations, integrations or workers change | [`backend.md`](backend.md) |
| Frontend | Next.js routes/components, API wrappers, player state or accessibility changes | [`frontend.md`](frontend.md) |
| Test | acceptance behavior, regression strategy, integration fixtures or browser coverage changes | [`test.md`](test.md) |
| Security | auth, roles, sensitive data, playback grants, storage scope, logs or abuse boundaries change | [`security.md`](security.md) |
| Documentation | current-state, architecture companions, specs, ADRs or contributor context changes | [`documentation.md`](documentation.md) |

Use all applicable roles for a cross-cutting change, but keep one named owner for each deliverable.
A useful sequence is architect/security review, backend/frontend implementation, test evidence, then
documentation reconciliation. Small changes may combine roles in one contributor.

Every role hands off the outcome, evidence, skipped checks, contract/migration/docs impact, risks and
preserved unrelated worktree changes. Role-specific deliverables add to, rather than replace, the
PR handoff in `AGENTS.md`.
