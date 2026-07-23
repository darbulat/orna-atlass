# Architecture evals

`scripts/check_architecture.py` rejects runtime import cycles, reverse layer dependencies, direct
router access to repositories/models, and repository-owned commits. `adr-policy.toml` lists durable
surfaces that require a new ADR in the same change; `scripts/check_adr_policy.py` enforces it.
