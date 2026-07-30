# ORNA Atlas

ORNA Atlas is a living sound atlas of natural places: long-form field recordings linked to exact locations, local time, sunrise movement, habitat metadata, and high-quality audio assets.

The implemented capabilities and current limitations are tracked in `docs/CURRENT_STATE.md`.

## Core stack

- **API:** FastAPI
- **Database:** PostgreSQL with PostGIS
- **Cache and jobs:** Redis
- **Audio processing:** RQ worker, persistent processing jobs, waveform metadata
- **Audio storage:** S3-compatible object storage (MinIO in local compose) with presigned playback URLs
- **Frontend:** Next.js / React, TypeScript, WebGL map/globe layer, audio-first interaction design
- **Primary domain:** locations, audio sessions, dawn line discovery, playback metadata, memberships, and editorial collections

## Local development

1. Copy `.env.example` to `.env` and adjust values if needed.
2. Start the stack:

```bash
docker compose up --build
```

The compose stack first runs `alembic upgrade head`, then starts the API,
frontend, PostgreSQL, Redis, the audio worker, and the resilient
storage-cleanup/pipeline-recovery workers.

3. Add local atlas test data:

```bash
docker compose exec -e APP_ENVIRONMENT=local api python -m orna_atlas.app.seed_atlas --force
```

Existing pre-ownership demo rows are never claimed implicitly. For a deliberate
one-time local/test migration of known manifest rows already marked `seed=true`,
add `--adopt-legacy-seed`; collection/session links are still left untouched.

4. Open the frontend at <http://localhost:3000> and the API at <http://localhost:8000>.

## Server deployment

Connect to the deployment server before running the server Compose commands below:

```bash
ssh root@94.183.151.61
```

For a shared development server backed by external S3-compatible storage, set
the public API and `S3_*` values in `.env`, then layer the server override over
the local compose file:

```bash
docker compose -f docker-compose.yml -f docker-compose.server.yml up -d --build
```

For the repository-managed HTTPS gateway, set `PUBLIC_HOST` to the canonical apex
hostname, provision a certificate covering both `$PUBLIC_HOST` and `www.$PUBLIC_HOST`
under `.deploy/certbot/conf/live/$PUBLIC_HOST/`, and add the tracked HTTPS overlay.
The gateway redirects the `www` hostname to the canonical apex hostname. Run
certificate issuance only after both DNS names resolve to this server, and set a
real contact address in `CERTBOT_EMAIL`.

When an existing HTTP gateway already serves `/var/www/certbot` on port 80, use
the webroot flow without stopping it:

```bash
docker run --rm \
  -v "$PWD/.deploy/certbot/conf:/etc/letsencrypt" \
  -v "$PWD/.deploy/certbot/work:/var/lib/letsencrypt" \
  -v "$PWD/.deploy/certbot/logs:/var/log/letsencrypt" \
  -v "$PWD/.deploy/certbot/www:/var/www/certbot" \
  certbot/certbot:v5.7.0 certonly --non-interactive --agree-tos \
  --email "$CERTBOT_EMAIL" --webroot -w /var/www/certbot \
  --cert-name "$PUBLIC_HOST" -d "$PUBLIC_HOST" -d "www.$PUBLIC_HOST"
```

On a fresh host where no gateway is listening and port 80 is free, bootstrap the
certificate with standalone mode before starting the HTTPS Compose overlay:

```bash
docker run --rm -p 80:80 \
  -v "$PWD/.deploy/certbot/conf:/etc/letsencrypt" \
  -v "$PWD/.deploy/certbot/work:/var/lib/letsencrypt" \
  -v "$PWD/.deploy/certbot/logs:/var/log/letsencrypt" \
  certbot/certbot:v5.7.0 certonly --non-interactive --agree-tos \
  --email "$CERTBOT_EMAIL" --standalone --cert-name "$PUBLIC_HOST" \
  -d "$PUBLIC_HOST" -d "www.$PUBLIC_HOST"
```

The renewal service preserves the names in this certificate lineage automatically.

```bash
docker compose -f docker-compose.yml -f docker-compose.server.yml \
  -f docker-compose.https.yml up -d --build
```

The gateway renders `deploy/nginx.conf.template`; its access-log format replaces every HLS
playback path with a redacted sentinel before writing the log record.

The override enforces production validation for the API, disables local-admin compatibility,
disables MinIO, keeps PostgreSQL, Redis, and worker metrics bound to loopback, and removes direct
API/web host-port publication.

### Production environment

Use `.env.example` as the local-development template, but replace every development credential and
URL before a production start. The production configuration is grouped below:

| Area | Variables | Production requirements |
| --- | --- | --- |
| Public routing | `PUBLIC_HOST`, `NEXT_PUBLIC_API_URL`, `CORS_ORIGINS`, `TRUSTED_PROXY_CIDRS` | Use the canonical HTTPS host/origin. `CORS_ORIGINS` is a JSON list such as `["https://atlas.example.com"]`; trusted proxies are a JSON list of only the reverse-proxy network CIDRs. With the HTTPS overlay, the browser API URL is replaced by the same-origin `/api` route. |
| Data services | `DATABASE_URL`, `REDIS_URL` | Point to the intended production PostgreSQL/PostGIS and Redis services. |
| Object storage | `S3_ENDPOINT_URL`, `S3_PUBLIC_ENDPOINT_URL`, `S3_REGION`, `S3_PRIVATE_BUCKET`, `S3_PUBLIC_BUCKET`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY` | Supply the external S3-compatible service, separate private/public buckets, and production credentials. |
| Cookies and tokens | `AUTH_COOKIE_SECURE=true`, `HLS_TOKEN_SECRET`, `HLS_TOKEN_KEY_ID`, `HLS_TOKEN_PREVIOUS_SECRETS` | Use an HLS secret of at least 32 characters that is independent from the authentication signing key. Previous HLS keys are a JSON object used only for bounded rotation. |
| Authentication signing | `AUTH_SIGNING_ALGORITHM`, `AUTH_KEY_ID`, `AUTH_SECRET_KEY`, `AUTH_PRIVATE_KEY`, `AUTH_JWKS_JSON` | For `HS256`, replace `AUTH_SECRET_KEY` with an independent secret of at least 32 characters. For `RS256`, supply a PEM `AUTH_PRIVATE_KEY`; use `AUTH_JWKS_JSON` for rotation-ready verification keys. |
| Bereke billing | `BILLING_ENABLED`, `BILLING_FRONTEND_URL`, `BEREKE_CHECKOUT_CREATE_URL`, `BEREKE_MERCHANT_ID`, `BEREKE_API_KEY`, `BEREKE_CALLBACK_SECRET`, `BEREKE_CALLBACK_URL`, `BEREKE_CHECKOUT_HOSTS` | Keep billing disabled until Bereke supplies the merchant-specific hosted-checkout contract and sandbox approval, the support mailbox works, and the required online cash-register/fiscal receipt flow is operational. Production URLs must use HTTPS, the callback secret must be at least 32 characters, and checkout hosts are an explicit JSON allowlist. |

Keep `APP_ENVIRONMENT=production` and `LOCAL_ADMIN_ENABLED=false`; the server overlay sets both.
The remaining operational controls are optional overrides of the validated defaults:

| Area | Variables and defaults |
| --- | --- |
| Playback and sessions | `S3_PRESIGN_EXPIRES_SECONDS=900`, `ACCESS_TOKEN_TTL_SECONDS=900`, `REFRESH_TOKEN_TTL_DAYS=30` |
| Pipeline timing | `AUDIO_JOB_TIMEOUT_SECONDS=600`, `AUDIO_JOB_TIMEOUT_PER_HOUR_SECONDS=3600`, `AUDIO_JOB_MAX_TIMEOUT_SECONDS=21600`, `PIPELINE_STALE_AFTER_SECONDS=25200` |
| Pipeline retries/results | `AUDIO_JOB_MAX_RETRIES=2`, `AUDIO_JOB_RETRY_INTERVAL_SECONDS=60`, `AUDIO_JOB_RESULT_TTL_SECONDS=3600` |
| Retention and metrics | `MEDIA_RETENTION_DAYS=30`, `WORKER_METRICS_PORT=9101` |
| Request limits | `AUTH_RATE_LIMIT=10`, `PLAYBACK_RATE_LIMIT=30`, `SEARCH_RATE_LIMIT=60`, `RATE_LIMIT_WINDOW_SECONDS=60` |

#### Email magic links

Email sign-in is fail-closed until SMTP delivery is configured. Set:

| Variable | Requirement |
| --- | --- |
| `MAGIC_LINK_CALLBACK_URL` | Absolute public HTTPS URL ending in `/api/v1/auth/magic-link/consume`. |
| `SMTP_HOST`, `SMTP_FROM_EMAIL` | Required together to enable delivery. |
| `SMTP_PORT` | SMTP port; defaults to `587`. |
| `SMTP_USERNAME`, `SMTP_PASSWORD` | Optional, but must be supplied together when the server requires authentication. |
| `SMTP_STARTTLS` | Must remain `true` in production. |
| `OAUTH_FRONTEND_URL` | Absolute public HTTPS membership URL used after authentication. |

If SMTP is omitted, magic-link requests return service unavailable rather than inventing a delivery.

#### Social OAuth

OAuth providers are optional. Configure either every variable for a provider or none of them:

- Google: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`;
- Apple: `APPLE_CLIENT_ID`, `APPLE_TEAM_ID`, `APPLE_KEY_ID`, `APPLE_PRIVATE_KEY` (P-256 PEM; escaped
  newlines are accepted);
- Facebook: `FACEBOOK_CLIENT_ID`, `FACEBOOK_CLIENT_SECRET`.

When any provider is enabled, `OAUTH_CALLBACK_BASE_URL` and `OAUTH_FRONTEND_URL` must be absolute
public HTTPS URLs without credentials, query parameters, or fragments. Never commit provider,
SMTP, signing, HLS, database, or object-storage secrets.

## Backend checks

```bash
pip install '.[dev,worker]'
python -m ruff check .
python -m pytest
alembic upgrade head
alembic check
APP_ENVIRONMENT=test RUN_MIGRATION_CYCLE_CHECK=1 \
  python -m orna_atlas.app.scripts.verify_migration_cycle
```

Real dependency smoke tests are opt-in and must target disposable local services:

```bash
RUN_INTEGRATION_TESTS=1 python -m pytest -m integration tests/integration
```

Frontend checks and browser smoke tests:

```bash
cd web
npm ci
npm run api:check
npm run test:unit
npm run typecheck
npm run lint
npm run build
npm run test:e2e
```

## Audio pipeline

Admin uploads create a `MediaAsset`, persist an `audio_pipeline` processing job, enqueue it on
Redis/RQ, and expose status through:

```http
POST /api/v1/admin/sessions/{session_id}/assets
GET /api/v1/admin/sessions/{session_id}/processing
POST /api/v1/admin/media-assets/{asset_id}/process
```

The worker can also be run directly:

```bash
python -m orna_atlas.app.workers.audio_pipeline worker
python -m orna_atlas.app.workers.storage_cleanup worker
python -m orna_atlas.app.workers.pipeline_recovery worker
```

Pipeline job timeouts scale with declared recording duration; jobs with unknown
duration receive the configured maximum timeout. Every stage persists its own
status/attempt/error, and stale queued or running jobs are failed and re-enqueued
through RQ after their heartbeat lease. See `docs/PERFORMANCE_BASELINE.md` for the
1–6 hour stage benchmark.

API/queue Prometheus metrics are exposed at `http://localhost:8000/metrics`; the
RQ worker exposes fork-safe pipeline/stage metrics at
`http://localhost:9101/metrics`. RS256 deployments publish sanitized verification
keys at `/.well-known/jwks.json`; configure signing material through the documented
`AUTH_*` environment variables rather than baking keys into an image.

## First production administrator

Keep `LOCAL_ADMIN_ENABLED=false` outside explicit local/development environments. After migrations,
register the intended owner as a normal user, then run this command once against the production
database from a secured application shell:

```bash
python -m orna_atlas.app.scripts.bootstrap_admin --email owner@example.com
```

The command takes a PostgreSQL transaction lock, refuses to run if any administrator already
exists, and writes an audit event. Further role changes must use the authenticated admin API.

## Documentation

- [Project architecture](docs/ARCHITECTURE.md)
- [Architecture context index](docs/architecture/README.md)
- [Implementation plan (RU)](docs/IMPLEMENTATION_PLAN_rus.md)
- [Current implementation](docs/CURRENT_STATE.md)
- [Domain rules](docs/DOMAIN_RULES.md)
- [Architecture decisions](docs/adr/README.md)
- [Change specifications](specs/README.md)
- [Agent evaluation registry](evals/README.md)
- [Performance baseline](docs/PERFORMANCE_BASELINE.md)
- [Contribution guide](CONTRIBUTING.md)
- [Developer and LLM guide](AGENTS.md)
