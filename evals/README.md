# Agent evaluation registry

`manifest.toml` is the executable registry for deterministic repository checks. Run the fast,
dependency-free tier with:

```bash
python scripts/run_agent_evals.py --tier fast
```

The normal backend, integration, frontend and browser CI jobs execute the registered full and
dependency-backed suites. Add a registry entry when a new quality boundary gains a stable command;
do not put production credentials or live-service probes in an eval.
Registry `env` values are explicit non-secret test gates merged into each subprocess. The PostGIS
scale eval sets `RUN_INTEGRATION_TESTS=1`, so missing disposable dependencies fail instead of being
reported as a passing skipped test.

- `architecture/` owns import, transaction and ADR-policy checks.
- `prompt/` owns context-routing and prompt-harness checks.
- `performance/` points to reproducible bounded benchmarks and scale tests.
- `ui/` points to deterministic browser journeys and accessibility checks.
