# Анализ административной панели ORNA Atlas

- Дата среза: 2026-07-30
- Статус: аналитический материал; не является описанием реализованной функциональности
- Связанная спецификация: [`../specs/admin-workspace-v1.md`](../specs/admin-workspace-v1.md)

## 1. Резюме

В backend уже есть защищённый `/api/v1/admin` с командами для локаций, сессий, media pipeline,
коллекций, ролей, membership и чтения audit log. Это не полноценная админ-панель: API в основном
командный, административных list/detail-проекций почти нет, а в `web/` отсутствуют маршруты,
обвязка API, route guard, формы, таблицы и browser-тесты для `/admin`.

Главные выводы:

1. **Frontend нельзя строить поверх публичных list/detail API.** Они намеренно скрывают draft,
   private, archived и hidden сущности, а также точные координаты и operational metadata.
2. **Нельзя просто обернуть текущие mutation endpoints интерфейсом.** Изменения контента и media
   lifecycle аудируются неполно; текущая смена роли допускает опасные сценарии вроде изменения
   собственной роли и потери последнего активного администратора.
3. **Безопасный путь — staged release.** Сначала admin-only browse/edit/processing/audit workspace,
   затем user role и membership management после отдельного backend hardening. Физический purge,
   browser upload, account deactivation и доступ роли `editor` в v1 не входят.
4. **Новая схема БД для v1, вероятно, не нужна.** Существующие таблицы и индексы покрывают чтение и
   audit log; это должно быть подтверждено query-plan/integration проверками до реализации.

## 2. Подтверждённое текущее состояние

### 2.1 Авторизация

- `orna_atlas/app/core/security.py` определяет роли `member`, `editor`, `admin`.
- `get_current_admin()` принимает production token/cookie, повторно загружает пользователя из БД и
  проверяет актуальные `is_active` и `role`. Устаревший JWT с ролью admin не даёт доступ после
  изменения роли в БД.
- Локальный `X-ORNA-Admin: local` выключен по умолчанию, допустим только при явном local/development
  флаге и запрещён production-конфигурацией.
- `docs/DOMAIN_RULES.md` прямо запрещает наследование admin publication/user-management прав ролью
  `editor`.
- Первый production admin создаётся однократно через
  `orna_atlas/app/scripts/bootstrap_admin.py`; операция сериализована и аудируется.

### 2.2 Существующие admin endpoints

| Область | Реализовано сейчас | Ограничение для UI |
| --- | --- | --- |
| Identity | `GET /api/v1/admin/me` | Ответ — неименованный `dict`, нет typed schema |
| Locations | create, patch, archive через delete | Нет admin list/detail; публичный список скрывает protected/archived и exact fields |
| Sessions | create, patch, archive; register assets/segments; retry/read processing | Нет admin list/detail; публичный список видит только опубликованные и доступные записи |
| Collections | create, patch | Нет admin list/detail; нет HTTP delete, хотя repository/service delete существуют |
| Users | `PATCH /admin/users/{id}/role` | Нет поиска/list/detail; нет last-admin/self-change guard |
| Memberships | `PUT /admin/memberships/{user_id}` | Нет user-centric read endpoint для панели |
| Audit | `GET /admin/audit-events` с `event_type`, `limit`, `offset` | Нет actor/subject/date filters; mutation coverage неполный |

Авторитетный entry point — `orna_atlas/app/modules/admin/router.py`. Router корректно вызывает domain
services, а не пишет в модели напрямую.

### 2.3 Audit log

`audit_events` уже хранит actor, event type, subject, IP, user agent, metadata и timezone-aware
`created_at`. Сейчас гарантированно аудируются, среди прочего:

- bootstrap первого admin;
- смена роли;
- обновление membership;
- успешный playback grant;
- ключевые auth-события.

Не видно систематического audit trail для create/update/archive локаций и сессий, collection
mutations, регистрации media/segments, retry/archive/purge media. До появления UI это операционный
пробел; после появления UI он становится security и accountability риском.

### 2.4 Frontend

В `web/` сейчас отсутствуют:

- `web/app/admin/**`;
- admin layout/shell/navigation;
- server/client guard для admin role;
- `web/lib/api/admin.ts`;
- административные формы и таблицы;
- admin unit/Playwright coverage.

Есть пригодные строительные блоки:

- Next.js App Router;
- cookie-based auth через `credentials: "include"`;
- `fetchJson`, типизированные `ApiError` и refresh patterns;
- generated OpenAPI types в `web/lib/api/generated.ts`;
- единая dark visual system в `web/app/styles.css`;
- Playwright mock API и сценарии auth/error/responsive behavior.

Глобальный `SiteHeader` ориентирован на публичный продукт. Административный workspace должен иметь
отдельный shell и не смешивать privileged navigation с публичным меню.

## 3. Gap analysis

### P0 — блокирует безопасный релиз

1. Нет admin list/detail endpoints для основных сущностей.
2. Нет frontend route guard; проверка видимости ссылки не является авторизацией.
3. Нет полного аудита административных mutations с actor/IP/user-agent.
4. Смена роли не защищает от self-role-change и удаления последнего активного admin.
5. Нет deterministic negative tests: anonymous `401`, non-admin/editor `403`, hidden/exact admin DTO
   только после admin auth.
6. Нет optimistic concurrency/version precondition: два администратора могут молча перезаписать
   изменения друг друга через текущие PATCH/PUT операции.
7. Нет admin browser acceptance, keyboard/focus/responsive coverage.

### P1 — нужен для полезного рабочего процесса

1. Поиск и bounded filters для locations, sessions, collections, users и audit.
2. Явные loading/empty/error/conflict states и повторная загрузка после mutation.
3. Session processing view: assets, jobs, error code/message, retry status.
4. Безопасные формы exact/public coordinates, timezone и publication/access/processing как отдельных
   полей.
5. Collection ordering и выбор скрытых/draft сущностей через admin-проекции, а не публичные DTO.
6. User detail, role и membership в одном контексте, но разными явными действиями.

### P2 — сознательно отложено

- browser binary upload/presigned multipart flow;
- account activation/deactivation и удаление пользователей;
- доступ `editor` к административному workspace;
- bulk actions/import/export;
- физический media purge из UI;
- каскадный archive location из UI;
- billing/payment management;
- отдельная fine-grained permission model.

## 4. Предлагаемая information architecture

| Route | Назначение | Основные действия v1 |
| --- | --- | --- |
| `/admin` | Стартовая страница | ссылки на рабочие очереди, последние audit events |
| `/admin/locations` | Каталог локаций | search/filter, create, open edit |
| `/admin/locations/new` | Создание локации | exact/public coordinates, visibility, sensitivity, timezone |
| `/admin/locations/[id]` | Редактирование | безопасный patch; archive не показывать в v1 |
| `/admin/sessions` | Каталог сессий | filters по publication/access/processing/location |
| `/admin/sessions/new` | Создание draft | metadata и editorial state отдельно от processing |
| `/admin/sessions/[id]` | Сессия и pipeline | edit, assets/segments registration, status, bounded retry, session archive с подтверждением |
| `/admin/collections` | Каталог коллекций | public/private filter, create/edit |
| `/admin/collections/[id]` | Состав коллекции | ordered location/session selection из admin datasets |
| `/admin/users` | Пользователи | email search, role/membership filters |
| `/admin/users/[id]` | Account administration | role и membership как отдельные подтверждаемые actions |
| `/admin/audit` | Audit trail | event/actor/subject/date filters, collapsed metadata |

Для mobile таблицы должны переходить в карточки или горизонтально прокручиваемые semantic regions;
все actionable controls — минимум 44×44 CSS px. Workspace должен оставаться keyboard-usable и не
зависеть от hover.

## 5. Предлагаемый release scope

### Slice A — foundation и browse

- typed `/admin/me`;
- admin-only shell и fail-closed guard;
- admin list/detail API и UI для locations, sessions, collections;
- audit list с дополнительными bounded filters;
- no-store для privileged responses;
- отсутствие exact coordinates в любом публичном контракте подтверждается regression tests.

### Slice B — editorial mutations и processing

- create/update формами существующих schemas;
- session processing status и retry;
- register уже загруженных managed storage keys/segments;
- session archive с явным impact copy и typed confirmation;
- полный audit trail в той же service-owned transaction, что и DB mutation.

### Slice C — account administration

- user list/detail с membership projection;
- запрет self-role-change;
- сериализованный запрет потери последнего активного admin;
- role и membership mutations с независимым подтверждением и audit;
- никаких deactivation/delete/reset-password действий.

Slice C не должен включаться в production до прохождения security review exact candidate.

## 6. Threat model и обязательные меры

| Риск | Последствие | Мера v1 |
| --- | --- | --- |
| UI-only role check | прямой вызов API non-admin пользователем | каждый endpoint сохраняет `get_current_admin`; browser guard только UX |
| Exact coordinate disclosure | вред sensitive habitat | отдельные admin DTO; no-store; public regression canary |
| CSRF для cookie auth | несанкционированная mutation | SameSite=Lax плюс проверка Origin для cookie-auth admin writes; Bearer clients не ломать |
| Last-admin demotion | lockout управления | transaction/advisory lock, active-admin count, self-change forbidden |
| Stale form overwrite | незаметная потеря более свежей редакции | version/ETag precondition и typed conflict; точный контракт решить до реализации |
| Stale response после role loss | privileged UI остаётся визуально активным | каждый API request повторно валидирует БД; `401/403` очищает admin workspace state |
| Double submit/retry | повторная enqueue/mutation | disable pending controls; backend idempotency/existing-active-operation rules |
| Media purge/archive error | потеря данных | purge не показывать; archive только через существующий inventory/retention lifecycle |
| XSS через metadata/errors | захват admin session | только text rendering; JSON metadata без `dangerouslySetInnerHTML`; bounded fields |
| Audit tampering/omission | нет расследуемости | audit insert в той же service-owned transaction; нельзя сообщать success без audit commit |
| Sensitive browser caching | следы exact coordinates/PII | `Cache-Control: no-store`; не помещать payload в localStorage/analytics |

## 7. Рекомендация

Принять `specs/admin-workspace-v1.md` после ответа на открытые вопросы, затем реализовывать вертикальными
срезами: один admin workflow = backend RED → backend GREEN → regenerated contract → frontend RED →
frontend GREEN → narrow browser check. Не начинать с набора разрозненных моделей или одной большой
frontend страницы.

Отдельный ADR сейчас не нужен: направление уже следует ADR-0001, ADR-0002, ADR-0004 и существующей
канонической архитектуре. ADR понадобится только если будет принято fine-grained разделение ролей
или новый upload/permission boundary.
