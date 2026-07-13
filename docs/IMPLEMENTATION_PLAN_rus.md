# План реализации ORNA Atlas

Этот документ фиксирует практический план реализации первой production-версии ORNA Atlas на основе текущей архитектуры проекта.

## 0. Продуктовые ориентиры

Реализация не должна превращаться в обычный аудиокаталог. Все технические решения должны поддерживать три принципа продукта:

1. **Место важнее трека** - аудио организовано вокруг реальных локаций, координат, среды обитания, местного времени и полевого контекста.
2. **Доверие и чистота записи** - каждая сессия содержит происхождение записи, флаги качества, политику по человеческому шуму и технические метаданные.
3. **Опыт атласа** - интерфейс и API поддерживают исследование карты, рассветную линию, воспроизведение сессий и редакционную подачу.

## 1. Phase 1: Архитектурный фундамент

### Цель

Поднять минимально рабочую инфраструктуру проекта: frontend skeleton, backend skeleton, базу данных, кеш, миграции, object storage wrapper и health checks.

### Backend

Создать модульный FastAPI-монолит со следующей структурой:

```text
orna_atlas/
  app/
    main.py
    core/
      config.py
      security.py
      logging.py
      errors.py
    db/
      session.py
      base.py
      migrations/
    modules/
      auth/
      users/
      locations/
      sessions/
      media/
      atlas/
      collections/
      memberships/
      admin/
    workers/
      audio_pipeline.py
      cache_warming.py
    integrations/
      s3.py
      redis.py
      sunrise.py
      bird_analysis.py
    tests/
```

Каждый доменный модуль должен иметь одинаковые внутренние слои:

```text
modules/<domain>/
  router.py
  schemas.py
  service.py
  repository.py
  models.py
  permissions.py
  events.py
```

### Frontend

Создать Next.js App Router skeleton:

```text
web/
  app/
    layout.tsx
    page.tsx
    atlas/
      page.tsx
    sessions/
      [slug]/
        page.tsx
    collections/
      [slug]/
        page.tsx
    about/
      page.tsx
    membership/
      page.tsx
  components/
  lib/
  tests/
```

### Инфраструктура

- PostgreSQL + PostGIS.
- Redis.
- S3-compatible storage wrapper.
- Alembic migrations.
- Health checks.
- `.env.example`.
- Docker Compose для локальной разработки.

### Definition of Done

- `GET /health` возвращает статус API, PostgreSQL и Redis.
- `/openapi.json` доступен.
- Frontend открывается на `/`.
- Есть базовая CI-проверка lint/test/build.
- Alembic умеет создавать и применять пустую миграцию.

## 2. Phase 2: Content model и minimal admin

### Цель

Смоделировать главные сущности: locations, sessions, media assets, publication lifecycle, access policy и audit events.

### Основные модели

Начать с сущностей:

- `User`
- `Location`
- `AudioSession`
- `MediaAsset`
- `SessionAnnotation`
- `BirdVocalPart`
- `Collection`
- `PlaybackGrant`

### Location

`Location` хранит реальные географические места и включает:

- `id`
- `slug`
- `title`
- `subtitle`
- `country`
- `region`
- `coordinates`
- `elevation_m`
- `habitat_type`
- `timezone`
- `description`
- `conservation_notes`
- `is_public`

Для чувствительных экологических объектов сразу заложить:

- `exact_coordinates`
- `public_coordinates`
- `coordinate_visibility`
- `sensitivity_level`

Публичные API должны возвращать только `public_coordinates`, если точные координаты не разрешены к публикации.

### AudioSession

`AudioSession` должна разделять:

- `processing_status` - техническая готовность media pipeline;
- `publication_status` - редакционное состояние;
- `access_policy` - правила доступа к воспроизведению.

Сессия может быть `ready`, но не `published`, и может быть опубликована как public preview или members-only.

### Admin API

Реализовать минимальные admin endpoints:

```http
POST /api/v1/admin/locations
PATCH /api/v1/admin/locations/{id}
POST /api/v1/admin/sessions
PATCH /api/v1/admin/sessions/{id}
POST /api/v1/admin/sessions/{id}/assets
POST /api/v1/admin/collections
PATCH /api/v1/admin/collections/{id}
```

Admin endpoints не должны обходить доменные сервисы. `modules/admin` содержит HTTP-обертки и admin-specific schemas, а публикация, архивирование, asset uploads и audit events выполняются через сервисы соответствующих доменов.

### Definition of Done

- Admin может создать локацию.
- Admin может создать сессию.
- Admin может привязать media asset к сессии.
- Есть audit events на публикацию и загрузку asset.
- Публичные endpoints не показывают draft/unpublished сущности.

## 3. Phase 3: Public session и audio foundation

### Цель

Сделать первую полноценную страницу сессии и базовый playback lifecycle.

### Backend

Реализовать endpoints:

```http
GET /api/v1/sessions/{slug}
POST /api/v1/sessions/{session_id}/playback-grants
GET /api/v1/sessions/{session_id}/waveform
GET /api/v1/sessions/{session_id}/annotations
```

### Frontend

Создать route `/sessions/[slug]`, который отображает:

- session hero;
- location metadata;
- recording integrity;
- player shell;
- annotation timeline;
- waveform placeholder.

### Global player

Реализовать global player store. Воспроизведение должно продолжаться при переходах между маршрутами.

Store хранит:

- текущую сессию;
- playback state;
- текущую позицию;
- длительность;
- срок действия signed URL;
- режим mini/full player.

Lifecycle плеера:

```text
idle -> requesting_grant -> ready -> playing -> paused -> refreshing_grant -> stalled -> ended -> error
```

### Definition of Done

- Пользователь может открыть public session page.
- Metadata рендерятся до запроса защищенного audio URL.
- Player запрашивает playback grant только при попытке воспроизведения.
- Playback grant можно обновить до истечения signed URL.
- Recording integrity отображается на странице.

## 4. Phase 4: Atlas experience

### Цель

Сделать карту/атлас как основной способ навигации по продукту.

### Backend

Реализовать endpoints:

```http
GET /api/v1/atlas/points
GET /api/v1/locations/{slug}
GET /api/v1/search?q={query}
```

`GET /api/v1/atlas/points` должен принимать:

- `bbox`
- `zoom`
- habitat filters
- time mode
- response limit

На низком zoom backend может отдавать clusters, на высоком - отдельные локации. Контракт должен учитывать anti-meridian и иметь стабильный Redis cache key.

### Frontend

Реализовать `/atlas`:

- globe/map toggle;
- filters;
- selected location state;
- side drawer;
- location markers;
- list fallback через `/atlas?view=list`.

List fallback должен быть first-class режимом, а не вторичной деградацией.

### Performance targets

- Landing page LCP менее 2.5 секунд.
- Первое пригодное взаимодействие с атласом менее 3 секунд.
- Globe/map interaction на уровне 45-60 FPS.
- Старт аудио после playback grant менее 1 секунды при нормальной S3/CDN latency.
- Session metadata рендерятся до запроса protected media.

### Definition of Done

- `/atlas` показывает точки из API.
- Можно выбрать точку и открыть drawer.
- Можно перейти из drawer на session page.
- `/atlas?view=list` работает без WebGL.
- Viewport responses кешируются в Redis.

## 5. Phase 5: Audio pipeline

### Цель

Добавить фоновые задачи обработки аудио: валидация, metadata extraction, streaming renditions, waveform, bird analysis.

### Pipeline

При загрузке master recording процесс должен быть таким:

1. API создает `MediaAsset` с `processing_status=uploaded`.
2. Worker валидирует файл, checksum, duration и loudness range.
3. Worker извлекает технические metadata.
4. Worker создает streaming renditions.
5. Worker генерирует waveform и optional spectrogram.
6. Worker отправляет запись во внешний сервис анализа птиц.
7. Worker сохраняет `BirdVocalPart` в PostgreSQL.
8. Worker сохраняет производные файлы в S3.
9. Worker обновляет `AudioSession.processing_status=ready`, если необходимые assets существуют.
10. Worker прогревает Redis cache для session cards, bird parts payloads и atlas views.

### Persistent jobs

Состояние обработки хранить не только в Redis, но и в PostgreSQL-таблице `processing_jobs`:

- `id`
- `asset_id`
- `job_type`
- `status`
- `attempt_count`
- `error_code`
- `error_message`
- `started_at`
- `finished_at`
- `created_at`

Redis используется для оперативного состояния, PostgreSQL - для аудита, retries и диагностики.

### Idempotency

Каждый шаг pipeline должен быть идемпотентным:

- deterministic S3 keys для производных файлов;
- upsert результатов анализа по `session_id`, `analysis_provider` и `analysis_model_version`;
- safe retry для waveform/rendition generation.

### Definition of Done

- Admin upload запускает background job.
- Processing status виден в admin.
- Waveform доступен через API.
- Streaming rendition создается и сохраняется в S3-compatible storage.
- Ошибка bird analysis не блокирует публикацию сессии, если обязательные media готовы.

## 6. Phase 6: Рассветный опыт

### Цель

Сделать уникальную механику ORNA Atlas: текущий рассвет, follow dawn и визуальный terminator.

### Backend

Реализовать endpoints:

```http
GET /api/v1/atlas/dawn/current
GET /api/v1/atlas/dawn/follow
```

Backend должен быть авторитетным источником для определения локаций, которые считаются активными рядом с рассветом, даже если frontend визуально рендерит движущуюся линию.

### Dawn model

Нужно:

- хранить timezone каждой локации;
- вычислять sunrise/sunset и civil dawn windows;
- кешировать dawn candidates в Redis;
- обновлять dawn cache каждые 1-5 минут;
- явно задать окно near dawn, например 45 минут до и 30 минут после рассвета.

### Frontend

Добавить:

- dawn terminator rendering;
- current dawn locations;
- next dawn locations;
- follow dawn mode.

### Definition of Done

- `/api/v1/atlas/dawn/current` возвращает актуальные dawn locations.
- `/api/v1/atlas/dawn/follow` возвращает упорядоченный список локаций.
- Frontend визуально показывает dawn line.
- Backend и frontend используют одинаковую настройку dawn window.
- Dawn payload кешируется в Redis.

## 7. Phase 7: Membership и protected playback

### Цель

Добавить auth, роли, membership entitlements и защищенное воспроизведение.

### Auth

Рекомендуемая модель:

- short-lived JWT access token;
- refresh token server-side;
- secure httpOnly cookie;
- RBAC для admin/editor;
- membership-based playback rules.

### Roles

Правила авторизации:

- public users видят public atlas points и public previews;
- members могут запрашивать signed playback grants;
- editors создают и редактируют draft locations/sessions;
- admins публикуют, архивируют и управляют users.

### Security controls

Обязательные controls:

- private S3 bucket для source audio;
- signed URLs для protected playback;
- strict admin role checks;
- rate limiting на auth/search/playback grants;
- Pydantic validation;
- no secrets in source code;
- structured audit events.

### Definition of Done

- Login/logout работает.
- `/api/v1/users/me` возвращает пользователя.
- `/api/v1/memberships/me` возвращает entitlement state.
- Members-only session нельзя воспроизвести без membership.
- Playback grant audit event создается.
- Rate limit защищает auth и playback grant endpoints.

## 8. Phase 8: Редакционная полировка

### Цель

Довести продукт до ощущения полноценного atlas/audio experience.

### Collections

Реализовать endpoints:

```http
GET /api/v1/collections
GET /api/v1/collections/{slug}
```

Collections - это редакционные группировки локаций или сессий: Dawn Archive, Wetlands, Northern Forests, Rain After Dusk, No Human Noise.

### Recording integrity

Каждая session page должна показывать:

- отсутствие loops;
- отсутствие studio layers;
- human noise level;
- microphone setup;
- duration;
- recording date;
- local time;
- weather;
- habitat.

### Bird parts timeline

Плеер должен показывать партии птиц на timeline записи. Эти данные не считаются на frontend: backend возвращает intervals, species, confidence и metadata из PostgreSQL.

### Definition of Done

- Collections доступны публично.
- Featured sessions управляются редакционно.
- Recording integrity стабильно отображается на session page.
- Bird parts timeline работает в player.
- Sensitive locations используют protected-coordinate mode.

## 9. Рекомендуемый порядок разработки по спринтам

### Sprint 1

- Monorepo/project skeleton.
- Docker Compose.
- FastAPI health check.
- Next.js landing placeholder.
- PostgreSQL/PostGIS, Redis.
- Alembic baseline.

### Sprint 2

- SQLAlchemy/Pydantic core.
- Locations model + CRUD.
- Sessions model + CRUD.
- MediaAsset model.
- Admin auth stub или local admin mode.

### Sprint 3

- Public session detail API.
- Session page frontend.
- Global player store.
- Playback grant mock.
- Recording integrity UI.

### Sprint 4

- Real S3 wrapper.
- Private/public bucket conventions.
- Upload shell.
- Streaming asset model.
- Signed URL generation.

### Sprint 5

- Atlas points endpoint.
- Redis viewport caching.
- `/atlas` UI.
- List fallback.
- Search.

### Sprint 6

- Worker/RQ.
- Processing jobs.
- Waveform generation.
- Audio metadata extraction.
- Processing status UI.

### Sprint 7

- Dawn calculations.
- Dawn cache refresh.
- Dawn endpoints.
- Dawn terminator frontend.
- Follow-dawn mode.

### Sprint 8

Статус: реализован 2026-07-12. Проверен unit/contract suite, Alembic upgrade/downgrade, runtime auth flow и browser smoke.

- Auth.
- Membership.
- Protected playback.
- Rate limits.
- Audit logs.

### Sprint 9

- Collections.
- Featured sessions.
- Bird parts timeline.
- Sensitive coordinates.
- Accessibility and performance pass.

## 10. Технические решения, которые нужно принять сразу

1. **Long-form playback делать rendition-based с первого дня.** MVP может начинаться с `stream_320.mp3`, но storage/API должны быть совместимы с HLS без миграции домена.
2. **Frontend не должен вручную дублировать API-типы.** FastAPI должен отдавать `/openapi.json`, CI должен генерировать `web/lib/api/generated.ts`, а frontend wrappers должны преобразовывать DTO в UI view models только при необходимости.
3. **Redis не источник истины.** Его нужно использовать для скорости, кеша и координации, но canonical state должен жить в PostgreSQL.
4. **Admin endpoints не должны обходить доменные сервисы.** Admin должен быть HTTP-оберткой, а публикация, архивирование, asset uploads и audit events должны проходить через соответствующие domain services.
5. **Публичные координаты sensitive locations должны быть отдельными от точных координат.** Это важно заложить в схему сразу, иначе позже придется мигрировать API, кеши и UI.
