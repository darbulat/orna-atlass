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

## Long-form audio stage baseline

Run the reproducible sparse-PCM benchmark without committing generated audio:

```bash
python -m orna_atlas.app.scripts.benchmark_audio_pipeline --hours 1 6
```

The fixture is mono 8 kHz/16-bit PCM. It has the full logical byte length and the
waveform code reads every frame, while sparse allocation avoids leaving hundreds
of megabytes on disk. These numbers cover checksum/metadata and streaming waveform
generation only; they do not claim BirdNET, S3 network, transcoding or full worker
capacity.

| Date | Worktree | Duration | Logical size | Metadata | Waveform | Total | Max RSS | Configured timeout |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 2026-07-14 | `dbaa412` + worktree | 1 h | 57,600,044 B | 0.1310 s | 2.1801 s | 2.3111 s | 217,040 KiB | 3,600 s |
| 2026-07-14 | `dbaa412` + worktree | 6 h | 345,600,044 B | 0.8684 s | 10.8725 s | 11.7409 s | 217,040 KiB | 21,600 s |

Measured on Linux x86_64 with an Intel Core i7-13700H. The timeout scales by
declared duration and is capped at six hours; an asset without trusted duration
receives that maximum rather than the short default. RQ retries twice with a
configurable interval. A recovery worker replaces queued or running jobs whose
heartbeat remains stale beyond the maximum timeout. Re-run this benchmark on
representative 44.1/48 kHz field audio and measure BirdNET and real object-storage
latency separately before setting production SLOs or reducing the timeout ceiling.
