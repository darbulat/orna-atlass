# Архитектура проекта ORNA Atlas

Это перевод канонического `ARCHITECTURE.md` и описание целевой архитектуры.
Фактическое состояние runtime фиксируется только в `CURRENT_STATE.md`.

## 1. Цель продукта

ORNA Atlas - это аудиоплатформа, построенная вокруг карты: каждая запись привязана к реальному природному месту. Пользователь исследует атлас планетарного масштаба, следует за движущейся линией рассвета, открывает активные точки и переходит к длинным ORNA Sessions: непрерывным записям лесов, болот, пустынь, гор, побережий, дождя, ветра, рассвета, сумерек и ночи.

Система должна сохранять три продуктовых принципа:

1. **Место важнее трека:** аудио организовано вокруг реальных локаций, координат, среды обитания, местного времени и полевого контекста.
2. **Доверие и чистота:** каждая сессия включает происхождение записи, флаги качества, политику по человеческому шуму и технические метаданные.
3. **Опыт атласа:** API должны поддерживать быстрое исследование карты, обнаружение рассветной линии, воспроизведение сессий и насыщенную редакционную подачу.

## 2. Целевой стек

| Слой | Технология | Ответственность |
| --- | --- | --- |
| Frontend-приложение | Next.js / React + TypeScript | UI атласа, страницы сессий, оболочка воспроизведения, сценарии членства |
| Рендеринг карты и глобуса | Three.js или MapLibre GL | 3D-планета, 2D-атлас, терминатор рассвета, маркеры локаций |
| API-приложение | FastAPI | Публичный API, admin API, auth, оркестрация домена |
| База данных | PostgreSQL + PostGIS | Источник истины для пользователей, локаций, сессий, геозапросов и метаданных |
| Кеш | Redis | Горячие данные карты, карточки сессий, метаданные signed URL, rate limits, состояние фоновых задач |
| Объектное хранилище | S3-совместимое хранилище | Аудиомастера, потоковые версии, изображения, waveform-ассеты, транскрипты/аннотации |
| Фоновые воркеры | RQ с Redis broker | Обработка аудио, генерация waveform, извлечение метаданных, прогрев кеша |
| Миграции | Alembic | Версионированная эволюция схемы |
| Наблюдаемость | OpenTelemetry + структурированные логи | Трейсы запросов, задержки, диагностика воркеров, мониторинг playback URL |

## 3. Высокоуровневая схема системы

```mermaid
flowchart LR
    Web[Web client / ORNA Atlas UI] --> API[FastAPI application]
    Mobile[Future mobile app] --> API
    Admin[Editorial admin] --> API

    API --> PG[(PostgreSQL + PostGIS)]
    API --> Redis[(Redis cache)]
    API --> S3[(S3 audio and media storage)]

    API --> Worker[Background workers]
    Worker --> Redis
    Worker --> PG
    Worker --> S3

    S3 --> CDN[CDN]
    CDN --> Web
```

## 4. Архитектура frontend

Frontend - первоклассная часть ORNA Atlas. Продукт не является обычным аудиокаталогом; это иммерсивный интерфейс атласа, где пользователь открывает записи через географию, время, свет и звук. Поэтому frontend должен проектироваться вокруг производительности рендеринга, непрерывности аудио и спокойной кинематографичной модели взаимодействия.

Рекомендуемый frontend-стек:

| Область | Рекомендация | Примечания |
| --- | --- | --- |
| Фреймворк приложения | Next.js with App Router | Серверно-рендеримые редакционные страницы, atlas experience с высокой долей клиентской логики |
| Язык | TypeScript | Общие API-контракты и более безопасное UI-состояние |
| Стилизация | Tailwind CSS плюс design tokens | Быстрая реализация со строгой визуальной системой |
| 3D-глобус | Three.js / React Three Fiber | Hero-планета, терминатор рассвета, атмосферные эффекты |
| Режим 2D-карты | MapLibre GL | Детальное исследование атласа, clustering, viewport queries |
| Загрузка данных | TanStack Query или SWR | Кеширование atlas payloads, sessions, collections, playback grants |
| Состояние | Zustand | Глобальное состояние плеера, выбранная локация, UI-режим |
| Аудио | HTMLAudioElement или обертка над Web Audio API | Длинное воспроизведение, будущие cross-fades, синхронизация waveform |
| Анимация | Framer Motion | Переходы входа в место, карточки, панели, route transitions |
| Тестирование | Playwright + Vitest | Основные пользовательские сценарии и поведение компонентов |

### 4.1 Структура frontend-приложения

Рекомендуемая структура пакетов:

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
    atlas/
      AtlasShell.tsx
      GlobeView.tsx
      MapView.tsx
      DawnTerminator.tsx
      LocationMarker.tsx
      LocationDrawer.tsx
    audio/
      GlobalPlayer.tsx
      SessionPlayer.tsx
      WaveformTimeline.tsx
      BirdPartsTimeline.tsx
      PlaybackGrantBoundary.tsx
    sessions/
      SessionHero.tsx
      RecordingIntegrity.tsx
      AnnotationTimeline.tsx
    layout/
      Header.tsx
      Navigation.tsx
      PageTransition.tsx
  lib/
    api/
      client.ts
      atlas.ts
      sessions.ts
      playback.ts
    audio/
      playerStore.ts
      usePlaybackGrant.ts
    geo/
      dawnTerminator.ts
      projections.ts
    design/
      tokens.ts
  tests/
```

### 4.2 Основные frontend-маршруты

| Route | Назначение | Режим рендеринга |
| --- | --- | --- |
| `/` | Кинематографичная landing page с живым глобусом, текущим рассветом и featured sessions | Серверная оболочка + клиентский глобус |
| `/atlas` | Полноценный интерактивный атлас с переключением глобус/карта, фильтрами и dawn mode | Client-heavy |
| `/sessions/[slug]` | Глубокая страница сессии с плеером, метаданными, аннотациями и integrity notes | Серверно-рендеримый контент + клиентский плеер |
| `/collections/[slug]` | Редакционные страницы коллекций | Server-rendered |
| `/membership` | Ценность членства, вход, правила доступа | Server-rendered |
| `/about` | Манифест, принципы записи, экологические обязательства | Server-rendered |

### 4.3 Ключевые UI-концепции

#### Оболочка атласа

Оболочка атласа владеет viewport карты/глобуса, выбранной локацией, активным временным режимом, фильтрами и боковыми панелями. Она вызывает `GET /api/v1/atlas/points` для видимых точек и `GET /api/v1/atlas/dawn/current` для текущего рассветного опыта.

`GET /api/v1/atlas/points` должен принимать `bbox`, `zoom`, фильтры среды обитания, режим времени и лимит ответа. На низких zoom levels backend может возвращать clusters или агрегированные точки, на высоких - отдельные локации. Контракт должен учитывать анти-меридиан и иметь стабильный cache key для Redis.

#### Терминатор рассвета

Frontend должен визуально рендерить движущуюся линию рассвета, но backend остается авторитетным источником для определения локаций, которые считаются активными рядом с рассветом. Это сохраняет плавность визуального движения и одновременно обеспечивает согласованную продуктовую логику для featured dawn sessions.

#### Переход входа в место

Выбор точки не должен ощущаться как открытие трека. Взаимодействие должно приближать или плавно вести пользователя к маркеру, приглушать окружающий UI, показывать местное время и координаты, а затем открывать drawer сессии или маршрут.

#### Глобальный аудиоплеер

Воспроизведение должно продолжаться при переходах между маршрутами. Глобальный store плеера должен хранить текущую сессию, состояние воспроизведения, текущую позицию, длительность, срок действия signed URL и режим отображения mini-player/full-player.

Lifecycle плеера должен быть явным: `idle -> requesting_grant -> ready -> playing -> paused -> refreshing_grant -> stalled -> ended -> error`. Если signed URL истекает во время воспроизведения, frontend заранее переводит плеер в `refreshing_grant`, запрашивает новый playback grant и продолжает воспроизведение без смены пользовательского контекста. Реальный audio element должен жить в корневом layout/provider, а route-level компоненты должны только управлять состоянием и подписками.

#### Партии птиц в плеере

Плеер должен показывать партии каждой птицы на timeline записи. Эти данные не вычисляются на frontend: backend отдает интервалы, виды, confidence и дополнительные метаданные из PostgreSQL. Пользователь должен видеть, какая птица звучит в конкретный момент, переключаться по партиям и фильтровать timeline по виду или уровню уверенности.

#### UI целостности записи

Каждая страница сессии должна показывать данные происхождения и качества: отсутствие петель, отсутствие студийных слоев, уровень человеческого шума, настройку микрофонов, длительность записи, дату, местное время, погоду и среду обитания. Это ключевая функция доверия, а не вторичные метаданные.

### 4.4 Поток данных frontend

```mermaid
sequenceDiagram
    participant UI as Frontend UI
    participant API as FastAPI
    participant Redis as Redis cache
    participant PG as PostgreSQL
    participant S3 as S3/CDN

    UI->>API: GET /api/v1/atlas/dawn/current
    API->>Redis: Read atlas:dawn:now
    Redis-->>API: Cached dawn payload
    API-->>UI: Dawn locations + session cards

    UI->>API: POST /api/v1/sessions/{id}/playback-grants
    API->>PG: Check session access and membership
    API->>S3: Create signed playback URL
    API-->>UI: Playback grant + signed URL
    UI->>S3: Stream audio through CDN or signed URL
```

### 4.5 Требования к производительности frontend

Начальные цели:

- Largest contentful paint landing page менее 2.5 секунд на типичном broadband-соединении.
- Первое пригодное взаимодействие с атласом менее 3 секунд после загрузки маршрута.
- Взаимодействия с глобусом и картой на уровне 45-60 FPS на современных ноутбуках.
- Старт аудио после playback grant менее 1 секунды при нормальной задержке S3/CDN.
- Метаданные страницы сессии должны рендериться до того, как аудиоплеер запросит защищенные media.

Приоритеты оптимизации:

1. Lazy-load для 3D-глобуса и тяжелых библиотек карт.
2. Использовать упрощенные marker payloads для atlas views.
3. Держать изображения высокого разрешения за responsive image sizes.
4. Откладывать загрузку waveform и аннотаций до видимости плеера.
5. Не блокировать route transitions генерацией signed playback URL.

### 4.6 Требования к доступности и fallback на frontend

Атлас должен быть иммерсивным, но не зависеть только от WebGL-взаимодействия. Обязательные fallback:

- Режим списка для локаций и коллекций как полноценный вариант `/atlas?view=list`, а не вторичный fallback.
- Доступные с клавиатуры карточки, маркеры, drawers и элементы управления плеером.
- Reduced-motion режим для переходов глобуса и анимации рассветной линии.
- Текстовые эквиваленты для локации, времени, погоды и целостности записи.
- Базовая поддержка воспроизведения без полного 3D-глобуса.

### 4.7 Контракт frontend-backend

Использовать сгенерированные TypeScript-типы из OpenAPI-схемы, которую создает FastAPI. Frontend не должен вручную дублировать формы API. Рекомендуемый процесс:

1. FastAPI предоставляет `/openapi.json`.
2. CI генерирует `web/lib/api/generated.ts`.
3. Frontend API wrappers преобразуют сгенерированные DTO в удобные для UI view models только там, где это необходимо.
4. Breaking API changes ловятся TypeScript и frontend-тестами.

## 5. Границы backend-сервисов

Первая версия может быть модульным монолитом. FastAPI следует разделить по доменным модулям, а не только по техническим слоям. Это сохраняет простоту деплоя и одновременно поддерживает четкие границы для будущего выделения сервисов.

Рекомендуемая структура пакетов:

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
  router.py        # HTTP endpoints only
  schemas.py       # Pydantic request/response DTOs
  service.py       # use cases and orchestration
  repository.py    # database queries
  models.py        # SQLAlchemy models
  permissions.py   # authorization decisions
  events.py        # domain events and worker triggers
```

Admin endpoints не должны обходить доменные сервисы. `modules/admin` содержит только HTTP-обертки и admin-specific schemas, а публикация, архивирование, asset uploads и audit events выполняются через сервисы соответствующих доменов.

## 6. Доменная модель

### 6.1 Основные сущности

#### User

Представляет слушателя, участника, администратора, редактора или полевого recordist.

Важные поля:

- `id`
- `email`
- `display_name`
- `role`: listener, member, editor, admin, recordist
- `membership_status`
- `created_at`
- `last_login_at`

#### Location

Реальное географическое место в атласе.

Важные поля:

- `id`
- `slug`
- `title`
- `subtitle`
- `country`
- `region`
- `coordinates`: PostGIS geography point
- `elevation_m`
- `habitat_type`: forest, wetland, mountain, coast, desert, tundra, river, grassland
- `timezone`
- `description`
- `conservation_notes`
- `is_public`
- `created_at`
- `updated_at`

#### AudioSession

Непрерывная запись, связанная с локацией.

Важные поля:

- `id`
- `location_id`
- `slug`
- `title`
- `format`: dawn, day, dusk, night, rain, wind, marsh, forest, ocean, expedition
- `starts_at_utc`
- `starts_at_local`
- `duration_seconds`
- `processing_status`: uploaded, processing, ready, failed
- `publication_status`: draft, published, unpublished, archived
- `access_policy`: public_preview, members_only, private
- `human_noise_level`: none_detected, minimal, present, unknown
- `purity_notes`
- `weather_summary`
- `temperature_c`
- `wind_mps`
- `humidity_percent`
- `moon_phase`
- `is_featured`
- `is_public`

Технический lifecycle записи и редакционная публикация должны быть разделены. `processing_status` отражает готовность media pipeline, `publication_status` - редакционное состояние, а `access_policy` - правила доступа к воспроизведению. Сессия может быть `ready`, но не `published`, и может быть опубликована как public preview или members-only.

#### MediaAsset

Файл в S3, связанный с сессией или локацией.

Важные поля:

- `id`
- `owner_type`: location, session, collection
- `owner_id`
- `asset_type`: audio_master, audio_stream, image, waveform, spectrogram, ambient_video
- `s3_bucket`
- `s3_key`
- `content_type`
- `size_bytes`
- `duration_seconds`
- `checksum`
- `processing_status`
- `created_at`

Для MVP допустим polymorphic ownership через `owner_type` + `owner_id`, но сервисы должны валидировать существование owner и запрещать dangling assets. При ужесточении схемы можно заменить это на nullable foreign keys `location_id`, `session_id`, `collection_id` с CHECK constraint, что ровно один owner заполнен.

#### SessionAnnotation

События на timeline внутри сессии.

Примеры: первый птичий зов, начало дождя, пик рассветного хора, порыв ветра, слой насекомых, далекий гром.

Важные поля:

- `id`
- `session_id`
- `offset_seconds`
- `duration_seconds`
- `label`
- `annotation_type`: species, weather, acoustic_event, editorial_note
- `confidence`
- `metadata_json`

#### BirdVocalPart

Распознанная партия конкретной птицы внутри записи. Метаданные партий хранятся в PostgreSQL и используются плеером для отображения видовой timeline. Расчет выполняется сторонним сервисом анализа аудио, а backend сохраняет нормализованный результат.

Важные поля:

- `id`
- `session_id`
- `species_code`
- `species_common_name`
- `species_scientific_name`
- `starts_at_seconds`
- `ends_at_seconds`
- `confidence`
- `channel`
- `call_type`: song, call, alarm, drumming, unknown
- `analysis_provider`
- `analysis_model_version`
- `metadata_json`
- `created_at`

#### Collection

Редакционная группировка локаций или сессий.

Примеры: Dawn Archive, Wetlands, Northern Forests, Rain After Dusk, No Human Noise.

Важные поля:

- `id`
- `slug`
- `title`
- `description`
- `cover_asset_id`
- `is_public`
- `sort_order`

Связи коллекций должны храниться в отдельных таблицах `collection_locations` и `collection_sessions` с `sort_order`, чтобы поддерживать ручную редакционную сортировку и смешанные подборки без дублирования сущностей.

#### PlaybackGrant

Короткоживущая запись доступа для защищенного воспроизведения аудио.

Важные поля:

- `id`
- `user_id`
- `session_id`
- `expires_at`
- `signed_url_hash`
- `created_at`

## 7. Стратегия схемы PostgreSQL

Использовать PostgreSQL как источник истины. Добавить PostGIS для запросов по локациям и расстояниям.

Рекомендуемые расширения:

```sql
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS unaccent;
```

Для чувствительных экологических объектов нужно хранить разные координаты:

- `exact_coordinates`: точная точка, доступная только admin/editor при разрешении.
- `public_coordinates`: публичная точка, которая может быть приблизительной.
- `coordinate_visibility`: `exact_public`, `approximate_public`, `hidden_public`.
- `sensitivity_level`: `none`, `low`, `medium`, `high`.

Публичные API атласа возвращают только `public_coordinates`, если `coordinate_visibility` не равно `exact_public`.

Ключевая стратегия индексирования:

- GiST index на `locations.coordinates` для viewport карты и distance queries.
- B-tree indexes на slugs, status fields и foreign keys.
- Composite indexes для публичных atlas queries, например `(is_public, habitat_type)`.
- Trigram indexes для поиска локаций по title, region и country.
- Partial indexes только для опубликованных сессий.

## 8. Использование Redis

Redis не должен быть источником истины. Использовать его для скорости и координации.

Рекомендуемые ключи:

| Key pattern | TTL | Назначение |
| --- | --- | --- |
| `atlas:viewport:{hash}` | 30-120s | Кешированные точки карты для viewport и zoom level |
| `atlas:dawn:now` | 30-60s | Текущие кандидаты рассветной линии |
| `session:card:{session_id}` | 5-30m | Public card payload для страниц с высоким трафиком |
| `playback:url:{session_id}:{user_id}` | 1-10m | Кешированные signed playback metadata |
| `rate:user:{user_id}` | short | API rate limiting |
| `job:audio:{asset_id}` | until completion | Состояние задачи обработки аудио |

Invalidation rules:

- При публикации или скрытии location/session инвалидировать `session:card:*`, affected viewport caches и dawn cache рядом с локацией.
- При изменении coordinates или timezone инвалидировать viewport, dawn и search projections.
- При замене media assets инвалидировать session detail, waveform/spectrogram payloads и CDN-объекты, если они публичные.
- При отзыве membership или смене access policy инвалидировать playback grant cache для затронутых пользователей/сессий.

## 9. Дизайн S3 object storage

Использовать private buckets для мастеров и controlled public/CDN access для производных ассетов.

Рекомендуемая структура buckets:

```text
orna-audio-private/
  sessions/{session_id}/master/original.wav
  sessions/{session_id}/processed/stream_320.mp3
  sessions/{session_id}/processed/stream_hls/master.m3u8
  sessions/{session_id}/processed/waveform.json
  sessions/{session_id}/processed/spectrogram.webp

orna-media-public/
  locations/{location_id}/cover.webp
  locations/{location_id}/gallery/{asset_id}.webp
  collections/{collection_id}/cover.webp
```

Правила доступа:

- Аудиомастера всегда private.
- Stream renditions могут быть private с signed URLs для members-only sessions.
- Public previews можно распространять через CDN.
- S3 keys хранятся в `media_assets`; никогда не хранить full signed URLs в PostgreSQL.

Long-form playback должен проектироваться как rendition-based с первого дня. MVP может начинать воспроизведение с `stream_320.mp3`, но модель asset-ов, API и storage layout должны быть совместимы с HLS (`stream_hls/master.m3u8`) без миграции домена.

## 10. Audio processing pipeline

Когда редактор загружает новую master recording:

1. API создает `MediaAsset` с `processing_status=uploaded`.
2. Worker валидирует тип файла, checksum, duration и loudness range.
3. Worker извлекает технические metadata.
4. Worker создает streaming renditions.
5. Worker генерирует waveform и опциональный spectrogram.
6. Worker отправляет запись или производный аудиофрагмент во внешний сервис анализа птиц.
7. Worker сохраняет распознанные `BirdVocalPart` в PostgreSQL.
8. Worker сохраняет производные файлы в S3.
9. Worker обновляет `AudioSession.processing_status=ready`, если необходимые assets существуют; публикация остается отдельным редакционным действием.
10. Worker прогревает Redis cache для session cards, bird parts payloads и atlas views.

Интеграция с сервисом анализа птиц:

- Сторонний сервис является вычислительным источником, но не источником истины.
- Backend сохраняет нормализованные партии птиц в `bird_vocal_parts`.
- Повторный анализ той же записи должен обновлять партии по `analysis_provider` и `analysis_model_version` идемпотентно.
- Плеер читает партии только через API ORNA Atlas, а не напрямую из внешнего сервиса.

Обработка ошибок:

- Processing steps должны быть idempotent.
- Failed jobs должны сохранять `error_code`, `error_message` и retry count.
- Masters нельзя автоматически удалять после processing failure.
- Ошибка анализа птиц не должна блокировать публикацию сессии, если аудио и обязательные media assets готовы; в этом случае UI показывает запись без bird parts timeline.

Состояние обработки должно храниться не только в Redis, но и в PostgreSQL таблице `processing_jobs`: `id`, `asset_id`, `job_type`, `status`, `attempt_count`, `error_code`, `error_message`, `started_at`, `finished_at`, `created_at`. Redis используется для оперативного состояния, PostgreSQL - для аудита, retries и диагностики.

Каждый шаг pipeline должен иметь idempotency rule: deterministic S3 keys для производных файлов, upsert результатов анализа по `session_id`, `analysis_provider` и `analysis_model_version`, безопасный повтор waveform/rendition generation.

## 11. Архитектура рассветной линии и местного времени

Рассветный опыт должен вычисляться из координат, даты и timezone. Backend должен отдавать готовых для API dawn candidates, не заставляя frontend вычислять все самостоятельно.

Рекомендуемый подход:

- Явно хранить timezone каждой локации.
- Вычислять sunrise/sunset и civil dawn windows с помощью детерминированной astronomy library или внутреннего сервиса.
- Кешировать текущих dawn candidates в Redis.
- Обновлять dawn cache каждые 1-5 минут.
- Явно определить окно рассвета, например `near_dawn_window_minutes_before=45` и `near_dawn_window_minutes_after=30`, чтобы frontend и backend одинаково понимали `is_near_dawn_now`.
- Timezone локации вычисляется из coordinates при создании, может быть переопределен редактором, валидируется при изменении coordinates и аудируется.

Важные API-концепции:

- `current_dawn_locations`: точки, где местный рассвет происходит сейчас или в пределах настраиваемого окна.
- `next_dawn_locations`: ближайшие точки, отсортированные по времени начала рассвета.
- `follow_dawn`: упорядоченный список локаций рядом с текущей terminator line.

## 12. Дизайн API

### Public atlas endpoints

```http
GET /api/v1/atlas/points
GET /api/v1/atlas/dawn/current
GET /api/v1/atlas/dawn/follow
GET /api/v1/locations/{slug}
GET /api/v1/sessions/{slug}
GET /api/v1/collections
GET /api/v1/collections/{slug}
GET /api/v1/search?q={query}
```

### Playback endpoints

```http
POST /api/v1/sessions/{session_id}/playback-grants
GET /api/v1/sessions/{session_id}/waveform
GET /api/v1/sessions/{session_id}/annotations
GET /api/v1/sessions/{session_id}/bird-parts
```

### Auth and membership endpoints

```http
POST /api/v1/auth/login
POST /api/v1/auth/logout
GET /api/v1/users/me
GET /api/v1/memberships/me
```

### Admin endpoints

```http
POST /api/v1/admin/locations
PATCH /api/v1/admin/locations/{id}
POST /api/v1/admin/sessions
PATCH /api/v1/admin/sessions/{id}
POST /api/v1/admin/sessions/{id}/assets
POST /api/v1/admin/collections
PATCH /api/v1/admin/collections/{id}
```

Endpoints, возвращающие списки (`collections`, `search`, atlas views), должны поддерживать `limit` и cursor/page параметры. Public detail endpoints могут использовать `slug`, но protected playback mutations должны использовать stable `session_id`, полученный из detail response.

Единая форма ошибок API:

```json
{
  "error": {
    "code": "playback_membership_required",
    "message": "Membership is required to play this session.",
    "request_id": "req_01JABC"
  }
}
```

## 13. Примеры ответов

### Atlas point

```json
{
  "id": "loc_01HXYZ",
  "slug": "bialowieza-forest",
  "title": "Białowieża Forest",
  "country": "Belarus / Poland",
  "lat": 52.7001,
  "lng": 23.8662,
  "timezone": "Europe/Warsaw",
  "habitat_type": "old_growth_forest",
  "active_session": {
    "id": "ses_01HXYZ",
    "slug": "belarus-dawn",
    "title": "Belarus Dawn",
    "format": "dawn",
    "duration_seconds": 20820,
    "human_noise_level": "none_detected"
  },
  "dawn_state": {
    "is_near_dawn_now": true,
    "local_time": "05:42",
    "sunrise_at_local": "05:51"
  }
}
```

### Session detail

```json
{
  "id": "ses_01HXYZ",
  "slug": "belarus-dawn",
  "title": "Belarus Dawn",
  "location": {
    "title": "Białowieża Forest",
    "country": "Belarus / Poland",
    "coordinates": [23.8662, 52.7001]
  },
  "duration_seconds": 20820,
  "format": "dawn",
  "recording_integrity": {
    "human_noise_level": "none_detected",
    "post_processing": "No loops, no studio layers, no artificial ambience",
    "microphone_setup": "ORTF field pair",
    "recordist_notes": "Unattended recording before sunrise after light rain."
  }
}
```

### Bird parts

```json
{
  "session_id": "ses_01HXYZ",
  "analysis_provider": "external-bird-audio-service",
  "analysis_model_version": "2026-06",
  "parts": [
    {
      "id": "bird_part_01JABC",
      "species_code": "turdus_merula",
      "species_common_name": "Common blackbird",
      "species_scientific_name": "Turdus merula",
      "starts_at_seconds": 184.2,
      "ends_at_seconds": 191.8,
      "confidence": 0.93,
      "call_type": "song"
    }
  ]
}
```

## 14. Аутентификация и авторизация

Рекомендуемая модель первой версии:

- JWT access token с коротким сроком действия.
- Refresh token хранится server-side и выдается клиенту через secure httpOnly cookie с rotation.
- Role-based access control для admin/editor operations.
- Membership-based playback rules для защищенных sessions и entitlement checks на выдаче playback grants.

Правила авторизации:

- Public users могут просматривать public atlas points и public previews.
- Members могут запрашивать signed playback grants для members-only sessions.
- Editors могут создавать и редактировать draft locations и sessions.
- Admins могут публиковать, архивировать и управлять users.

## 15. Требования к производительности

Начальные цели:

- Ответ atlas point viewport: менее 150 ms из кеша, менее 500 ms из базы данных.
- Ответ session detail: менее 250 ms из кеша, менее 600 ms из базы данных.
- Создание playback grant: менее 300 ms без учета S3 latency.
- Dawn cache refresh: каждые 1-5 минут.

Приоритеты оптимизации:

1. Кешировать map point payloads по viewport и zoom.
2. Предвычислять lightweight session cards.
3. Использовать CDN для images, waveform assets и public previews.
4. Держать генерацию signed audio URL на server-side.
5. Не отправлять тяжелые session metadata в atlas point responses.

## 16. Безопасность и приватность

Обязательные controls:

- Private S3 bucket для source audio.
- Signed URLs для protected playback.
- Строгие проверки admin role.
- Rate limiting на auth, search и playback grant endpoints.
- Валидация input через Pydantic schemas.
- Никаких secrets в source code.
- Структурированные audit events для publishing, asset uploads и admin changes.

Чувствительные экологические локации требуют coordinate obfuscation по `coordinate_visibility`. Некоторые protected habitats публично показывают approximate coordinates или скрываются из публичного atlas, сохраняя exact coordinates видимыми только администраторам и редакторам с соответствующим разрешением.

## 17. Переменные окружения

```text
APP_ENV=local
APP_SECRET_KEY=change-me
DATABASE_URL=postgresql+asyncpg://orna:orna@postgres:5432/orna_atlas
REDIS_URL=redis://redis:6379/0
S3_ENDPOINT_URL=https://s3.amazonaws.com
S3_REGION=eu-central-1
S3_PRIVATE_BUCKET=orna-audio-private
S3_PUBLIC_BUCKET=orna-media-public
CDN_BASE_URL=https://cdn.orna.example
JWT_ACCESS_TOKEN_TTL_SECONDS=900
JWT_REFRESH_TOKEN_TTL_SECONDS=2592000
```

## 18. Рекомендуемые этапы реализации

### Phase 1: Архитектурный фундамент

- Next.js frontend skeleton.
- FastAPI app skeleton.
- Настройка PostgreSQL + PostGIS.
- Redis connection.
- S3 integration wrapper.
- Alembic migrations.
- Health checks.

### Phase 2: Content model и minimal admin

- Locations CRUD.
- Sessions CRUD.
- Media assets model.
- Admin upload shell.
- Publication/access policy lifecycle.
- Audit events for publishing and asset changes.

### Phase 3: Public session и audio foundation

- Session detail endpoint.
- Session page frontend с global player.
- Playback lifecycle и grant refresh.
- S3 private master storage.
- Streaming rendition model.

### Phase 4: Atlas experience

- Public atlas points endpoint.
- Atlas frontend shell с `/atlas?view=list` fallback.
- Backend clustering/viewport contract.
- Search.

### Phase 5: Audio pipeline

- Background processing worker.
- Persistent `processing_jobs`.
- Waveform generation.
- Streaming renditions.
- Интеграция внешнего сервиса анализа птиц.
- Сохранение `BirdVocalPart` metadata в PostgreSQL.

### Phase 6: Рассветный опыт

- Sunrise и local-time calculations.
- Current dawn endpoint.
- Follow-dawn endpoint.
- Frontend dawn terminator rendering.
- Redis cache warming.

### Phase 7: Membership и protected playback

- Auth.
- User roles.
- Membership state and entitlements.
- Signed playback grants.
- Rate limits и audit logs.

### Phase 8: Редакционная полировка

- Collections.
- Featured sessions.
- Recording integrity display.
- Bird parts timeline в session player.
- Protected-coordinate mode для sensitive locations.

## 19. Принятые решения

1. Для long-form playback использовать rendition-based модель; MVP может стартовать с MP3 rendition, но storage/API должны быть HLS-ready.
2. Для первого релиза использовать hybrid globe/map interface с обязательным list fallback.
3. В качестве worker framework использовать RQ.
4. Для auth использовать internal JWT + server-side refresh-token rotation через secure httpOnly cookies.
5. Exact coordinates публичны только для `coordinate_visibility=exact_public`; sensitive locations используют approximate или hidden public coordinates.
6. Memberships реализуются внутри системы через membership state и entitlements, с возможностью будущей интеграции billing provider.
