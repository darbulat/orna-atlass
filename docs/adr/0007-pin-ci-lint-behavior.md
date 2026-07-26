# ADR-0007: Pin CI lint behavior explicitly

- Status: accepted
- Date: 2026-07-26

## Context

The backend CI installs the `dev` dependency group and then runs Ruff across the repository. The
previous lower-bound-only requirement (`ruff>=0.5.0`) allowed a new Ruff release to change the
effective default lint policy without any repository change. Ruff 0.16.0 consequently enabled a
broader rule set and failed existing code with 175 findings, while the repository's established
Ruff 0.15.22 check remained clean.

Adopting a broader lint policy can be valuable, but doing so incidentally during dependency
resolution mixes toolchain migration with unrelated changes and makes local and CI results depend on
installation time. A lint-policy expansion requires an explicit candidate, review of every newly
enabled rule and verified remediation rather than an unbounded dependency range.

## Decision

Pin Ruff exactly to version `0.15.22` in the Python `dev` dependency group. Clean local
verification environments that install this group and CI therefore execute the same known lint
behavior.

Future Ruff upgrades are explicit repository changes. An upgrade must run the candidate version
against the complete repository, review any rule-selection or semantic changes, fix or deliberately
configure the resulting findings, and pass the normal backend and frontend verification cycle before
merging. The pin must not be loosened merely to obtain newer releases automatically.

## Consequences

- Ruff results are reproducible between clean local Python 3.12 environments and GitHub Actions.
- Unrelated dependency installation cannot silently expand or weaken the lint gate.
- Ruff security and correctness improvements are adopted only through reviewed upgrades rather than
  automatically; maintainers must periodically evaluate and update the pin.
- The decision affects developer tooling only. It does not change application runtime behavior,
  public contracts, database schema, privacy rules or deployment configuration.

## Rejected alternatives

- **Keep only a minimum Ruff version:** permits the same lint-policy drift that caused the CI
  failure.
- **Fix all findings from the new release in this CI repair:** combines a repository-wide lint
  migration with an unrelated delivery and makes review substantially less bounded.
- **Disable the newly reported rules globally:** would encode an accidental release transition as
  policy without first reviewing which rules the project should adopt.
