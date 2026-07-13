# ORNA Atlas review: remediation appendix

Основной анализ находится в PROJECT_REVIEW_RU.md. Этот файл содержит атомарный план, roadmap, вопросы, checklist и prompt для слабой модели.

## 9. План исправлений для более слабой модели

### Шаг 1. Build и baseline

**Цель:** воспроизводимый Docker/CI без secrets.

**Файлы:** Dockerfile.api, README.md, CI, новый .dockerignore.

**Действия:** исключить .env/.git/caches/node_modules/.next/media; устанавливать package после source либо через wheel; использовать python -m pytest и npm ci.

**Не трогать:** logic, migrations, .env, user media.

**Проверка/тесты:** Docker build, import вне cwd, pytest, Ruff, npm typecheck/lint.

**Критерий готовности:** checks проходят; .env отсутствует в image.

**Риск:** Medium. **Rollback:** откатить Dockerfile/CI, оставить .dockerignore.

### Шаг 2. Local admin guard

**Цель:** убрать production bypass.

**Файлы:** core/config.py, core/security.py, .env.example, security tests.

**Действия:** app_env + allow_local_admin=false; header разрешён только в local с explicit flag; tests local allowed/disabled и production denied.

**Не трогать:** JWT/membership/public API.

**Проверка/тесты:** production + local header → отказ; полный pytest.

**Критерий готовности:** staging/production без bypass.

**Риск:** High operational. **Rollback:** flag только в local env.

### Шаг 3. Pagination

**Цель:** убрать 500/unlimited queries.

**Файлы:** locations/sessions/collections routers, новый pagination helper.

**Действия:** limit 1..100, offset от 0, featured max 50; boundary tests.

**Не трогать:** response shape/sorting/DB.

**Проверка/тесты:** invalid bounds → 422.

**Критерий готовности:** bounds в OpenAPI.

**Риск:** Low. **Rollback:** вернуть signatures, оставить tests.

### Шаг 4. Enums и constraints

**Цель:** запретить impossible states.

**Файлы:** domain models/schemas, новый domain_types.py, migration.

**Действия:** enums visibility/access/publication/processing/job/media; public_only → approximate_public; CHECK constraints; IANA timezone; coordinate/readiness/interval/confidence invariants.

**Не трогать:** UUID/slug/exact coordinates.

**Проверка/тесты:** legacy value mapping, schema/raw SQL/migration tests.

**Критерий готовности:** unknown state нельзя записать.

**Риск:** Medium/High. **Rollback:** downgrade migration.

### Шаг 5. Public coordinate policy

**Цель:** hidden/internal location не появляется публично.

**Файлы:** locations layers, atlas repository, collections service, sessions repository, DTO.

**Действия:** truth table; единый predicate; Admin/Public DTO; убрать internal metadata; применить ко всем public flows.

**Не трогать:** exact DB data/admin CRUD.

**Проверка/тесты:** exact/approximate/hidden fixtures через все endpoints.

**Критерий готовности:** единый privacy invariant.

**Риск:** High. **Rollback:** вернуть DTO, оставить tests.

### Шаг 6. Fail-closed playback

**Цель:** grant только для ready content.

**Файлы:** sessions layers, errors, S3 tests, seed.

**Действия:** убрать production mock; not-ready → 409; storage outage → 503; mock только explicit local; featured/public требуют ready rendition.

**Не трогать:** real S3 presign.

**Проверка/тесты:** missing rendition/object, outage, ready object, mock disabled.

**Критерий готовности:** silent success невозможен.

**Риск:** High. **Rollback:** local-only mock flag.

### Шаг 7. Player state machine

**Цель:** безопасные switch и URL refresh.

**Файлы:** PlayerProvider.tsx, SessionPlayer.tsx, component tests.

**Действия:** reducer; pause old audio; grant expiry check; replace src и restore state; abort stale request; cleanup.

**Не трогать:** visual redesign.

**Проверка/тесты:** fake audio, short TTL, component/E2E.

**Критерий готовности:** нет stale URL/old audio/race.

**Риск:** High. **Rollback:** сохранить tests и immediate pause fix.

### Шаг 8. Pipeline concurrency

**Цель:** один asset/version — один active job.

**Файлы:** media layers, worker, migration.

**Действия:** partial unique constraint; deterministic RQ ID; row lock; valid transitions; ready после upload/head; rollback; configurable retry/timeout; no blocking API I/O.

**Не трогать:** source master/last successful rendition.

**Проверка/тесты:** parallel retry и S3 partial failure.

**Критерий готовности:** ready rendition всегда имеет object.

**Риск:** High. **Rollback:** downgrade + advisory lock.

### Шаг 9. Asset versioning/lifecycle

**Цель:** безопасная замена/удаление.

**Файлы:** media/session models, media service, admin router, migration.

**Действия:** revision/active master; versioned key; atomic activation; archive + cleanup; запрет arbitrary path/bucket.

**Не трогать:** legacy objects до migration.

**Проверка/тесты:** old retry не меняет active; activation/rollback/cleanup.

**Критерий готовности:** retry/delete не теряют playback.

**Риск:** High. **Rollback:** nullable columns/legacy read.

### Шаг 10. Dawn/time и UI semantics

**Цель:** UI без invented facts.

**Файлы:** sunrise.py, atlas/service.py, AtlasExplorer.tsx, SessionPlayer.tsx.

**Действия:** backend solar phase; убрать fixed windows/05:42; Live только для live; disabled/скрыть fake controls.

**Не трогать:** sunrise formula без эталонной проверки.

**Проверка/тесты:** Tokyo/Kathmandu/Helsinki, polar/DST.

**Критерий готовности:** UI соответствует backend.

**Риск:** Medium. **Rollback:** client classification без fake time.

### Шаг 11. Integration/E2E

**Цель:** реальные flow tests.

**Файлы:** новый integration suite, playwright config/e2e, package.json, CI.

**Действия:** migration-backed DB; Redis/MinIO; Playwright testDir; atlas/playback/navigation; CI health checks.

**Не трогать:** production DB/.env.

**Проверка/тесты:** test list только project tests; suite проходит.

**Критерий готовности:** CI ловит auth/DB/cache/S3/browser regressions.

**Риск:** Medium. **Rollback:** временно non-blocking E2E.

### Шаг 12. Docs/LLM guide

**Цель:** отделить current от target.

**Файлы:** README, architecture docs, новые CURRENT_STATE, DOMAIN_RULES, AGENTS, CONTRIBUTING.

**Действия:** capability matrix; truth tables; commands; transaction/cache ownership; local-only seed; safety rules.

**Не трогать:** product vision — пометить target.

**Проверка/тесты:** links и README commands.

**Критерий готовности:** docs не противоречат code/API.

**Риск:** Low. **Rollback:** откатить неточные assertions.

## 10. Roadmap

### Sprint 1: Stabilization

Статус на 2026-07-13: **выполнен**.

- [x] Docker/CI/admin guard/pagination.
- [x] Fail-closed playback.
- [x] Public coordinate policy и cache invalidation.
- [x] P0 tests.

Ограничения Sprint 1: дальнейшее усиление DB constraints и унификация transaction ownership были вынесены в Sprint 2; защита публичных координат остаётся прикладным инвариантом и должна проверяться для каждого нового публичного DTO.

### Sprint 2: Architecture cleanup

Статус на 2026-07-13: **реализован в PR #23**.

- [x] Enums/constraints/transaction ownership.
- [x] Разделение media service и крупных frontend components.
- [x] Generated API types.
- [x] Удаление/маркировка пустых modules.

Ограничения Sprint 2: generated types пока подключены только к collections API; `AtlasExplorer` и orchestration-часть `SessionPlayer` требуют дальнейшей декомпозиции по мере развития UI; разделение publication/access semantics остаётся задачей Sprint 3.

### Sprint 3: Business logic hardening

- Publication/access/processing model.
- Active master/versioning/concurrency.
- Last successful BirdNET.
- Archive/cleanup/player refresh/solar phase.

### Sprint 4: LLM-readiness

Статус на 2026-07-12: **выполнен baseline**.

- [x] DB/Redis/S3 integration: opt-in suite `tests/integration/test_dependencies.py`, запуск против disposable compose services и CI.
- [x] Playwright: `web/playwright.config.ts` и smoke flow `web/e2e/public-navigation.spec.ts`, запуск локально и в CI.
- [x] Guides: `AGENTS.md`, `CONTRIBUTING.md`, `docs/CURRENT_STATE.md`, `docs/DOMAIN_RULES.md`.
- [x] ADR: public coordinate projection, fail-closed playback, versioned assets и service-owned transactions в `docs/adr/`.
- [x] Structured logs: JSON request completion event, correlation ID, status и duration в `core/logging.py`.
- [x] Performance baseline: воспроизводимый протокол и таблица результатов в `docs/PERFORMANCE_BASELINE.md`.

Ограничения baseline: Playwright пока покрывает public navigation, но не player races/accessibility; локальные performance-числа записаны, однако замер всё ещё нужно повторить на целевом dataset/environment. Эти пункты являются последующим расширением покрытия, а не скрытой декларацией готовности production.

## 11. Вопросы владельцу

### Бизнес

1. Может ли public session быть не ready?
2. Mock silence только development?
3. Сохранять last successful BirdNET?
4. Что считается Live?
5. Public collection может включать hidden location?

### Архитектура

1. Какой doc authoritative?
2. Ожидаемый scale?
3. Несколько masters допустимы?
4. Когда нужен HLS?

### Эксплуатация

1. Compose только local?
2. API доступен извне?
3. Максимальный WAV?
4. Backup/retention/CDN requirements?

### Тесты и безопасность

1. Проходит ли GitHub Actions?
2. Какие E2E release-blocking?
3. Насколько чувствительны coordinates/metadata?
4. Какая identity system заменит local header?

## 12. Финальный checklist

- [ ] Current/target architecture разделены.
- [ ] Transactions принадлежат services.
- [ ] Enums/constraints добавлены.
- [ ] Publication/access/processing разделены.
- [ ] Public projection централизована.
- [ ] Local admin закрыт вне local.
- [ ] .env отсутствует в image.
- [ ] Arbitrary paths/buckets запрещены.
- [ ] Hidden coordinates не публичны.
- [ ] Invalid pagination → 422.
- [ ] Pending session не выдаёт grant.
- [ ] URL refresh и switch работают.
- [ ] Один active processing job.
- [ ] S3 failure не оставляет ready state.
- [ ] Last successful BirdNET сохраняется.
- [x] Integration/E2E baseline tests добавлены; component/player tests остаются follow-up.
- [x] AGENTS/CURRENT_STATE/DOMAIN_RULES/CONTRIBUTING/ADR созданы.
- [x] README содержит воспроизводимые команды и ссылки на authoritative guides.
- [ ] Нет новых smells/regressions.

## Краткий prompt для слабой модели

~~~text
Работай в /home/bulat/PycharmProjects/orna-atlass.

Цель: добавить .dockerignore, исправить package install в Docker,
закрыть local admin вне local, валидировать pagination и добавить tests.

Открой Dockerfile.api, .env.example, core/config.py, core/security.py,
locations/sessions/collections routers, security tests, CI и README.

Требования:
- исключи .env/.git/caches/venv/node_modules/.next/local media;
- import orna_atlas должен работать независимо от cwd;
- APP_ENV + ALLOW_LOCAL_ADMIN=false;
- local header только при local + explicit flag;
- limit 1..100, offset >=0, featured max 50;
- tests для environment guard и invalid pagination;
- CI: python -m pytest и npm ci.

Не читай .env, не меняй migrations/playback/pipeline/UI, не удаляй
media, не используй destructive git и не ослабляй tests.

Проверки:
docker compose build api
docker compose run --rm api python -m pytest -q
docker compose run --rm api ruff check .
cd web && npm run typecheck && npm run lint

Готово: tests проходят, invalid limit → 422, production отвергает
local admin, package импортируется, .env отсутствует в image.
~~~
