# Performance baseline

The API request log emits `event=http.request.complete`, `request_id`, method, path, status and `duration_ms` as one JSON object. Preserve this event schema when changing logging so local and hosted measurements remain comparable.

## Reproducible local protocol

1. Start a clean compose stack and apply migrations.
2. Seed only the documented local fixture set.
3. Warm each route with five requests.
4. Send 100 sequential requests to `/health`, `/api/v1/atlas/points?zoom=3` and `/api/v1/sessions/featured?limit=6`.
5. Record p50, p95, p99, error count, fixture count, commit SHA and machine details below.

Do not publish a number without the dataset size and commit. Sequential latency is a diagnostic baseline, not a capacity claim. Add concurrent testing only after production scale and SLOs are agreed.

## Recorded runs

| Date | Commit | Dataset | Route | p50 | p95 | p99 | Errors | Environment |
|---|---|---:|---|---:|---:|---:|---:|---|
| 2026-07-12 | `7ca5b8b` worktree | 13 locations / 12 sessions / 4 collections | `/health` | 20.41 ms | 23.42 ms | 25.11 ms | 0/100 | Local Docker Compose, sequential warm requests |
| 2026-07-12 | `7ca5b8b` worktree | 13 locations / 12 sessions / 4 collections | `/api/v1/atlas/points?zoom=3` | 17.40 ms | 19.63 ms | 21.41 ms | 0/100 | Local Docker Compose, sequential warm requests |
| 2026-07-12 | `7ca5b8b` worktree | 13 locations / 12 sessions / 4 collections | `/api/v1/sessions/featured?limit=6` | 19.01 ms | 21.90 ms | 22.79 ms | 0/100 | Local Docker Compose, sequential warm requests |

## Initial guardrails

Until product SLOs are defined, investigate any endpoint with errors or a repeatable p95 regression greater than 20% against the same fixture and environment. Atlas scale must also be tested with a representative large dataset before claiming production capacity.
