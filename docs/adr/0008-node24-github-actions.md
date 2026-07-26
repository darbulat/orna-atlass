# ADR-0008: Run first-party GitHub Actions on Node.js 24

- Status: accepted
- Date: 2026-07-26

## Context

The CI workflow used `actions/checkout@v4`, `actions/setup-node@v4` and
`actions/setup-python@v5`. GitHub Actions reported that these releases target the deprecated
Node.js 20 action runtime and were being forced onto Node.js 24 by the hosted runner. The jobs still
passed, but relying on compatibility enforcement leaves the workflow on deprecated action majors
and makes a later enforcement change more likely to interrupt delivery.

The current major releases of all three first-party actions are version 7 and declare `node24` in
their action metadata. The application tool versions selected by the workflow—Node.js 20 for the
frontend and Python 3.12 for the backend—are inputs to those actions and are independent of the
JavaScript runtime used internally by the actions themselves.

## Decision

Use `actions/checkout@v7`, `actions/setup-node@v7` and `actions/setup-python@v7` throughout the CI
workflow. Preserve the existing checkout depth, dependency-cache configuration and selected
application tool versions.

Continue following the repository's major-tag convention for first-party GitHub Actions. Future
action-major upgrades remain explicit workflow changes and must pass the complete backend and
frontend jobs before being accepted.

## Consequences

- First-party workflow actions execute on their declared Node.js 24 runtime instead of deprecated
  Node.js 20 compatibility handling.
- Backend, frontend, integration, migration, image-build and browser gates retain their existing
  commands and intended acceptance coverage.
- Following major tags admits compatible patch and minor updates published within each major;
  maintainers still need to review future major migrations explicitly.
- This changes CI orchestration only. It does not alter application runtime dependencies, public
  contracts, database schema, deployment services, privacy rules or playback behavior.

## Rejected alternatives

- **Keep the deprecated action majors:** preserves warnings and relies on compatibility behavior that
  GitHub has announced as transitional.
- **Change the application Node.js or Python versions at the same time:** conflates independent
  runtime migrations with the action-runtime maintenance change.
- **Pin arbitrary commit SHAs in this repair:** would introduce a different dependency-management
  convention without a repository-wide supply-chain decision or update process.
