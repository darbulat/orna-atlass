# Глубокое ревью ORNA Atlas

Дата ревью: 2026-07-12  
Формат: архитектура, качество кода, bugs, бизнес-риски, тесты и LLM-readiness.

## 1. Executive Summary

Проект представляет собой функциональный prototype/production foundation для аудиоатласа природных записей. Архитектурная идея здравая: FastAPI разбит на предметные модули, инфраструктурные интеграции вынесены отдельно, схема БД управляется Alembic, frontend использует строгий TypeScript, а аудиообработка оформлена как persistent job pipeline.

Общее состояние:

- Поддерживаемость текущего prototype: **6/10**.
- Готовность к production: **3/10**.
- LLM-readiness: **5/10**.
- Архитектурный фундамент хороший, но несколько временных решений уже стали частью публичного runtime-поведения.

Главные сильные стороны:

- Последовательная backend-структура models → schemas → repository → service → router.
- Явное разделение public/admin API.
- Async SQLAlchemy, Alembic, Redis, S3 wrapper и RQ worker уже интегрированы.
- Защита точных координат предусмотрена в модели.
- Есть 56 проходящих backend-тестов, typecheck и lint frontend проходят.
- Atlas корректно учитывает anti-meridian bbox.
- Persistent processing jobs и deterministic rendition keys — хорошая база для идемпотентности.

Главные риски:

1. **Critical:** admin API открывается статическим заголовком X-ORNA-Admin: local, без проверки среды. Это подтверждено запросом к живому API.
2. **Critical:** отсутствует .dockerignore; COPY . . включает .env, .git, локальные зависимости и медиа в Docker image. Это создаёт риск утечки secrets и уже приводит к образам размером 3.28–7.19 GB.
3. **High:** публичные сессии без реального аудио получают mock playback grant и воспроизводят секундный silent WAV. В текущей БД 11 из 12 public sessions не имеют assets, включая все 5 featured sessions.
4. **High:** public location/collection paths недостаточно строго применяют coordinate visibility; hidden или внутренние локации могут попасть в public detail/list flows.
5. **High:** signed URL формально обновляется, но новый URL не назначается audio element; повторный запуск той же сессии может использовать истёкший grant.
6. **High:** pipeline не защищён от одновременной обработки одного asset; возможны duplicate jobs, гонка создания rendition и противоречивые состояния.
7. **High:** publication, access policy и processing readiness смешаны. access_level=public не означает наличие готового аудио.
8. **High:** нет реальных DB/API integration tests и frontend tests; Playwright настроен только в package.json, но suite отсутствует и команда падает.
9. **Medium/High:** public list endpoints не валидируют pagination. GET /locations?limit=-1 подтверждённо возвращает 500.
10. **Medium/High:** invalid timezone молча превращается в UTC на backend и в фиктивное 05:42 на frontend.

Вердикт: проект не требует rewrite. Ему нужен короткий stabilization cycle: закрыть временный admin-доступ, сделать playback fail-closed, централизовать public visibility, добавить DB constraints и integration tests, затем укрепить pipeline и frontend player lifecycle.

Приоритеты:

- **Must fix now:** admin guard, .dockerignore, public visibility, pagination, mock playback, cache invalidation при изменении координат/публикации.
- **Should fix soon:** pipeline locking/idempotency, domain enums и constraints, signed URL refresh, DB/API integration tests.
- **Can improve later:** PostGIS viewport queries, typed generated API client, разделение больших frontend-файлов.
- **Nice to have:** OpenTelemetry, ADR, component tests, полноценный CDN/HLS lifecycle.

Ограничения ревью:

- .env намеренно не читался, чтобы не раскрывать secrets.
- Бинарные изображения и WAV не анализировались.
- Визуальное качество всех 1610 строк CSS не оценивалось построчно.
- npm audit не завершился из-за timeout registry, поэтому актуальный vulnerability status npm-зависимостей не подтверждён.
- Код и данные проекта во время ревью не изменялись.

## 2. Карта проекта

### Назначение

ORNA Atlas — map-first платформа для длинных полевых аудиозаписей. Основные flows:

1. Редактор создаёт location и recording session.
2. Редактор регистрирует source audio asset.
3. API создаёт persistent processing job и ставит RQ job в Redis.
4. Worker получает WAV из local/S3 storage, извлекает metadata, строит waveform, создаёт streaming rendition и запускает BirdNET.
5. Public API отдаёт atlas points, dawn state, collections и session detail.
6. Frontend запрашивает playback grant и воспроизводит signed URL.

### Стек

| Слой | Реализация |
|---|---|
| Backend | Python 3.12, FastAPI, Pydantic v2 |
| Persistence | PostgreSQL 16 + PostGIS extension, async SQLAlchemy |
| Миграции | Alembic |
| Jobs/cache | Redis, RQ |
| Storage | S3-compatible storage, MinIO local |
| Audio analysis | WAV processing, BirdNET/TensorFlow |
| Frontend | Next.js 14, React 18, TypeScript |
| Globe | Cesium |
| CI | GitHub Actions |
| Containers | Docker Compose |

### Ключевые директории и entry points

| Область | Файлы |
|---|---|
| FastAPI entry point | orna_atlas/app/main.py |
| Конфигурация | orna_atlas/app/core/config.py |
| DB session | orna_atlas/app/db/session.py |
| Admin API | orna_atlas/app/modules/admin/router.py |
| Locations | orna_atlas/app/modules/locations/ |
| Sessions | orna_atlas/app/modules/sessions/ |
| Atlas/search/dawn | orna_atlas/app/modules/atlas/ |
| Media pipeline | orna_atlas/app/modules/media/service.py |
| Worker entry point | orna_atlas/app/workers/audio_pipeline.py |
| S3 wrapper | orna_atlas/app/integrations/s3.py |
| Frontend root | web/app/layout.tsx |
| Atlas UI | web/components/atlas/AtlasExplorer.tsx |
| Global player | web/components/audio/PlayerProvider.tsx |
| API client/types | web/lib/api/sessions.ts |
| CI | .github/workflows/ci.yml |

### Основные сущности

- Location
- RecordingSession
- MediaAsset
- ProcessingJob
- BirdVocalPart
- Collection
- CollectionLocation
- CollectionSession

Документация также описывает User, Membership и PlaybackGrant, но соответствующие модули фактически пустые. Playback grant сейчас не хранится в БД.

### Фактические потоки данных

~~~text
Admin header
  → FastAPI admin router
  → service
  → repository
  → PostgreSQL

MediaAsset
  → ProcessingJob
  → Redis/RQ
  → worker
  → S3/local file
  → waveform + copied WAV rendition + BirdNET
  → PostgreSQL

Browser/Next server
  → public FastAPI endpoints
  → PostgreSQL / Redis cache
  → JSON
  → Cesium atlas / session player
~~~

### Фактические данные локальной БД

На момент ревью:

- 13 locations.
- 12 public sessions.
- 2 media assets.
- 1 processing job.
- 4 public collections.
- 11 public sessions имеют processing_status=pending и не имеют audio assets.
- Все 5 featured sessions не имеют audio assets.

Это не обязательно production data, но демонстрирует, что текущая модель допускает публикацию непроигрываемого контента.

## 3. Архитектурное ревью

| Область | Наблюдение | Риск | Серьёзность | Рекомендация |
|---|---|---|---|---|
| Модульность backend | Единый паттерн models/schemas/repository/service/router | Хорошая база, но часть сервисов содержит HTTP concerns | Low | Сохранить структуру; постепенно заменить HTTPException в domain service на domain errors |
| Auth boundary | Admin dependency принимает один статический header | Полный admin-доступ при доступности API | Critical | Разрешать local admin только при явных APP_ENV=local и ALLOW_LOCAL_ADMIN=true; вне local — fail closed |
| Public/private projection | Visibility реализована property модели и выборочно в repository | Разные endpoints применяют разные правила приватности | High | Ввести единый PublicLocationPolicy/query helper и public DTO builder |
| Publication model | access_level одновременно означает доступ и публикацию | Pending/необработанный контент считается публичным | High | Разделить publication_status, access_policy, processing_status |
| Audio pipeline | Pipeline оформлен одной функцией с несколькими внешними side effects | Частичный commit, гонки, тяжёлый retry всего pipeline | High | Разбить на идемпотентные steps с row locking и step status |
| Storage abstraction | Wrapper поддерживает S3 и local path | Local path и arbitrary bucket доступны через API payload | Critical при текущем admin | Запретить local references вне CLI/test; allowlist bucket и key prefix |
| Geospatial architecture | PostGIS включён, но coordinates хранятся как Float; clustering выполняется в Python | Full-table load и слабая масштабируемость | High при росте | Добавить geometry/geography column, GiST index и DB-side viewport/clustering |
| Cache architecture | Redis cache есть только для atlas/dawn | Нет централизованной invalidation policy | High | Инвалидировать cache в той же application transaction через after-commit event/outbox |
| Frontend API contracts | Типы переписаны вручную | Backend/frontend drift не обнаруживается компилятором | Medium | Генерировать TypeScript types/client из OpenAPI |
| Frontend state | PlayerProvider централизует audio element | Grant/audio lifecycle не является атомарным state machine | High | Вынести reducer/state machine и покрыть переходы тестами |
| Target vs actual | Документация описывает JWT, memberships, rate limit и audit, но код пуст | Ложное ощущение готовности и риск неверных LLM-правок | High | Добавить docs/CURRENT_STATE.md и маркировать target architecture |
| Transaction boundary | Repository-функции сами вызывают commit | Business flow нельзя атомарно объединить из нескольких repositories | High | Commit должен принадлежать service/use-case layer |
| Observability | Логи минимальны, request IDs и metrics отсутствуют | Pipeline/playback errors трудно коррелировать | Medium | Structured logs, request/job IDs, queue и processing metrics |
| Deployment | Один Dockerfile обслуживает API и ML worker | API image включает TensorFlow/BirdNET и получается гигантским | High | Разделить lightweight API image и ML worker image |

### Важнейшие архитектурные выводы

1. **Целевая архитектура выдаётся за текущую.** ARCHITECTURE_rus.md описывает JWT, refresh rotation, roles и membership. Фактически security.py содержит только local header, а auth/users/memberships состоят из пустых файлов.
2. **Commit находится слишком низко.** Repository самостоятельно commit-ит операции, что мешает атомарной invalidation, audit/outbox и rollback целого use case.
3. **Public projection не централизован.** Atlas исключает hidden_public, но public locations и collection detail используют другие правила.
4. **Pipeline выглядит идемпотентным, но не является конкурентно безопасным.** Нет unique active job, row lock, deterministic RQ job ID и compare-and-set transitions.

## 4. Code Smells и проблемы поддерживаемости

| Файл / модуль | Проблема | Почему это плохо | Серьёзность | Как исправить |
|---|---|---|---|---|
| orna_atlas/app/modules/media/service.py | 519 строк: orchestration, WAV, S3, BirdNET, Redis и statuses | Высокая связность, трудно тестировать partial failures | High | Разделить на pipeline, waveform, renditions, bird analysis и cache invalidation |
| web/components/atlas/AtlasExplorer.tsx | 794 строки: Cesium, search, polling, carousel, player и UI | God component | High | Выделить CesiumGlobe, hooks, carousel и side panel |
| web/components/audio/SessionPlayer.tsx | 442 строки и смешение timeline math, formatting и playback | Сложно локально менять UI | Medium | Вынести pure utilities и controls |
| web/app/styles.css | 1610 строк глобального CSS | Неочевидные зависимости и collision risk | Medium | CSS modules и design tokens |
| auth/users/memberships | Десятки пустых tracked-файлов | Ложные entry points и шум для LLM | Medium | Удалить до реализации либо явно пометить NOT_IMPLEMENTED |
| Schemas | _reject_required_nulls скопирован в нескольких модулях | Дублирование | Low | Общий validator helper/base model |
| Models/schemas | Statuses и policies — произвольные str | Невалидные состояния попадают в БД | High | StrEnum/Literal + DB CHECK |
| sessions/schemas.py | Большой model_validator вручную гидратирует ORM object | Хрупкий hidden mapping | Medium | Явный mapper session_detail_from_model |
| web/lib/api/sessions.ts | Все backend DTO вручную дублируются в одном файле | Contract drift | High | OpenAPI generation и resource clients |
| Fetch helpers | Ошибки поглощаются и превращаются в []/null | Outage выглядит как отсутствие контента | Medium | Typed ApiError и distinction 404/5xx/network |
| seed_atlas.py | Seed удаляет все bird parts и collection links известных сущностей | Может уничтожить production data | High | Environment guard и изменение только seed-owned records |
| sessions/service.py | Mock WAV и production grant logic живут вместе | Заглушка стала business behavior | High | Перенести mock playback в explicit dev adapter |
| integrations/sunrise.py | Невалидный timezone молча становится UTC | Ошибка данных не обнаруживается | High | Валидация timezone при write |
| AtlasExplorer.tsx | Ошибки даты/timezone дают фиксированное 05:42 | UI показывает выдуманный факт | High | Показывать Time unavailable |
| Frontend controls | Несколько кнопок визуально активны без действий | Обманчивый UI | Medium | Реализовать или disabled/скрыть |
| Dockerfile.api | Установка проекта до копирования package source | Console pytest в image не импортирует package | Medium | Копировать package до install или собирать wheel |
| README | Указан Sprint 6, хотя код включает Sprint 9 | Документация устарела | Medium | Capability matrix вместо sprint-label |
| Две ARCHITECTURE | RU и EN дублируют по 846 строк | Риск расхождения | Low | Определить canonical source |

## 5. Потенциальные bugs и runtime risks

| Сценарий / файл | Возможная ошибка | Как проявится | Серьёзность | Как проверить | Как исправить |
|---|---|---|---|---|---|
| core/security.py | Любой клиент с local header становится admin | CRUD/delete/process без identity | Critical | Подтверждено запросом /admin/me | Environment gate и настоящая auth/RBAC |
| Dockerfile.api | .env попадает в build context/image | Secrets доступны в image layer | Critical | docker history/image filesystem без вывода secrets | .dockerignore и runtime secrets |
| locations/router.py | limit=-1 не валидируется | HTTP 500 | High | Подтверждено локальным HTTP-запросом | Query ge/le |
| Sessions/collections lists | Неограниченный limit | DB overload или 500 | High | Boundary API tests | Общая pagination dependency |
| Public /locations | Hidden/unpublished locations не фильтруются | Утечка names, metadata, public coordinates | High | Hidden fixture + list/detail | Public repository policy |
| collections/service.py | Public collection возвращает все linked locations | Hidden location может утечь | High | Integration test | Filter links/validate publication |
| sessions/service.py | Missing S3/rendition возвращает mock stream | Silent success без контента | High | Pending public session | 409 session_not_ready или 503 |
| PlayerProvider.tsx | Refreshed grant не обновляет audio.src | Playback stalls после URL expiry | High | Grant TTL 10–20 сек | Replace src, restore position/state |
| PlayerProvider.tsx | Same-session fast path использует старый src | Истёкший URL переиспользуется | High | Pause до expiry, затем play | Проверять grant expiry |
| Player switch | Старое audio играет во время нового grant request | UI новой session, звук старой | High | Задержать grant и быстро переключить | Pause old audio сразу |
| media/service.py | Два workers одновременно обрабатывают asset | Duplicate analysis/unique conflict | High | Параллельный retry | Row lock + deterministic job ID |
| Pipeline upload failure | Rendition ready до успешного upload | Ready object отсутствует в S3 | High | Mock upload exception | Ready только после upload/head |
| Multiple source assets | Один rendition key на session | Retry старого master перезапишет stream | High | Два assets в обратном порядке | Asset revision и active master |
| BirdNET retry | Transient failure удаляет предыдущие результаты | Bird timeline исчезает | High | Success, затем failure | Retain last successful snapshot |
| Worker timeout | 600 секунд для long-form audio | Нормальная запись может timeout | High, гипотеза | Измерить 1–6-часовой WAV | Configurable/chunked jobs |
| Sync S3 in async route | head_object блокирует event loop | API degradation при S3 latency | Medium/High | Artificial latency/load test | Threadpool или async client |
| Atlas Redis cache | Corrupt JSON не перехватывается | Endpoint 500 до TTL | Medium | Malformed cache entry | Catch, delete, regenerate |
| Coordinate/publication update | Atlas cache не инвалидируется | Старые sensitive coordinates видны до TTL | High | Cache → hide → repeat GET | After-commit invalidation |
| Session metadata | Malformed annotation/waveform | Public endpoint 500 | Medium | Invalid metadata fixture | Validate on write/skip legacy invalid |
| BirdNET normalization | Negative start или confidence >1 | Response validation 500 | Medium | Invalid provider output | Clamp/reject |
| Atlas search pagination | Offset отдельно для двух queries | Пропуски/повторы mixed results | Medium | 20+20 records, offset 10 | UNION/cursor query |
| Frontend fetch helpers | 500/timeout превращается в пустой контент | Outage маскируется | Medium | Остановить API | Typed error handling |
| Delete session/location | DB cascade не удаляет S3 objects | Orphaned files и расходы | Medium/High | Delete + bucket check | Tombstone и cleanup job |

## 6. Бизнес-логические риски

| Бизнес-правило / flow | Где реализовано | Потенциальная ошибка | Последствия | Серьёзность | Что уточнить / исправить |
|---|---|---|---|---|---|
| Public session доступна слушателю | access_level=public | Не проверяется ready rendition | Featured session открывается, но играет silence | High | Определить publication invariant |
| Public vs members-only | Session access_level | Нет user/membership/grant persistence | Нельзя безопасно запустить protected playback | Critical перед launch | Auth/entitlement |
| Publication и access | Одна строка access_level | Смешаны разные измерения | Ошибочные transitions | High | Разделить publication и access |
| Sensitive coordinates | Location + atlas filters | Docs approximate_public, code public_only | Неоднозначные rules | High | Canonical enum + migration |
| Hidden location | Public routes/collections | Исключается не везде | Косвенная утечка | High | Единая public policy |
| Live listening | SessionPlayer/AtlasExplorer | Архивная запись называется Live | Подрыв доверия | High | Playing/Recorded, Live только для live stream |
| Dawn/Day/Dusk/Night | AtlasExplorer | Фиксированные часы вместо астрономии | Ошибки сезонов/полярных регионов | High | Authoritative solar phase с backend |
| Timezone | Schemas + silent fallback | Опечатка становится UTC | Неверный local time/dawn | High | Reject invalid IANA timezone |
| Replacement master | Media relationship | Нет active master/version | Старый retry заменяет актуальное audio | High | Asset revisions |
| Bird analysis failure | media service | Старые results удаляются | Временный outage ухудшает content | High | Last successful version |
| Collection counts | Все links | Count может включать hidden location | Count не совпадает с UI | Medium | Считать после public projection |
| Delete content | Admin hard delete | Нет archive/audit/cleanup | Потеря metadata, orphaned files | High | Archive first |
| Fake controls | Frontend | Кнопки без handlers | Продукт воспринимается сломанным | Medium | Удалить/disabled |
| Featured content | Seed | Pending session становится featured | Landing рекламирует непроигрываемый content | High | Readiness guard |
| Seed safety | seed_atlas.py | Нет environment guard | Production data может быть перезаписана | High | Local-only + explicit force |

## 7. Тесты и недостающее покрытие

Фактические результаты:

- python -m pytest -q: **56 passed**, 3 deprecation warnings.
- ruff check .: проходит.
- alembic check: новых операций не обнаружено.
- npm run typecheck: проходит.
- npm run lint: проходит.
- npm run test:e2e -- --list: падает, 0 project tests.
- В репозитории 53 backend test functions и 0 frontend test files.
- Backend-тесты почти полностью schema/unit tests с mocks; реальная PostgreSQL, Redis, MinIO и CRUD API не используются.
- Console pytest внутри API image падает с ModuleNotFoundError; python -m pytest проходит.

| Что протестировать | Тип теста | Почему важно | Приоритет | Пример сценария |
|---|---|---|---|---|
| Admin environment guard | API/security | Critical vulnerability | P0 | production + local header → отказ |
| Pagination boundaries | API | Сейчас negative limit даёт 500 | P0 | -1/0/max+1 → 422 |
| Hidden location во всех public flows | DB integration | Privacy invariant | P0 | list/detail/search/collection/session |
| Public session readiness | DB integration | Не выдавать mock playback | P0 | pending session → 409 |
| Cache invalidation visibility | Redis integration | Sensitive data stale cache | P0 | cache → hide → GET |
| Concurrent processing | DB/worker integration | Duplicate work/state | P0 | два process jobs → один active |
| S3 partial failure | Integration | Не оставлять ready rendition | P0 | upload throws |
| Multiple source assets | Domain/integration | Активный master | P1 | old retry не меняет active |
| Signed URL refresh | Component/E2E | Новый URL не применяется | P0 | TTL 10 сек |
| Session switching | Component/E2E | Старое audio не должно играть | P1 | delayed grant |
| Search pagination | DB integration | Offset логически неверен | P1 | stable cursor |
| Invalid timezone | Schema/API | Защита dawn | P0 | Mars/Olympus → 422 |
| Domain constraints | Migration | Невозможные states | P1 | raw invalid insert fails |
| Metadata validation | API | Исключает public 500 | P1 | malformed annotation |
| Delete cleanup | Integration | S3 lifecycle | P1 | cleanup job removes object |
| Seed guard | CLI test | Защита production | P1 | production → abort |
| Atlas scale | Performance | Full-table Python load | P2 | 100k locations |
| Real frontend flows | Playwright | E2E отсутствуют | P0 | atlas → play → navigate |
| Accessibility | Playwright/axe | Custom controls | P2 | keyboard/focus/labels |

Существующим unit tests можно доверять для pure transformations, но они не являются safety net для persistence, authorization, transaction boundaries и browser playback.

## 8. LLM-readiness проекта

| Критерий | Оценка |
|---|---:|
| Понятность структуры | 7/10 |
| Предсказуемость паттернов | 7/10 |
| Качество документации | 6/10 |
| Безопасность внесения правок | 4/10 |
| Тестовая защита от регрессий | 4/10 |
| Лёгкость локализации нужного кода | 6/10 |

Итог: **5.7/10**.

Что помогает LLM:

- единообразные backend filenames;
- подробная архитектурная документация;
- type hints и Pydantic schemas;
- небольшие routers/repositories;
- тесты рядом с приложением;
- явные entry points.

Что мешает:

- 57 пустых tracked-файлов;
- target architecture не отделена от implemented architecture;
- большие AtlasExplorer.tsx, SessionPlayer.tsx, media/service.py и styles.css;
- business statuses представлены строками;
- API contracts дублируются вручную;
- нет AGENTS.md и CONTRIBUTING.md;
- нет тестов реальных business flows;
- hidden side effects через repository commit;
- seed может перезаписать данные;
- frontend глотает ошибки;
- разные имена одного правила: public_only и approximate_public.

Рекомендации:

1. Создать AGENTS.md с командами, картой entry points, invariants и запрещёнными операциями.
2. Создать docs/CURRENT_STATE.md с implemented/stubbed/planned.
3. Создать docs/DOMAIN_RULES.md с truth tables для публикации, доступа, координат и processing jobs.
4. Добавить ADR для coordinate policy, playback authorization, asset versioning и transaction ownership.
5. Генерировать frontend types из OpenAPI.
6. Удалить или однозначно маркировать пустые modules.
7. Разбить файлы, объединяющие несколько responsibilities.
8. Хранить regression tests рядом с каждым business invariant.
