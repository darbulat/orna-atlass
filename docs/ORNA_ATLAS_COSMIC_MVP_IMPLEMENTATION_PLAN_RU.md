# ORNA Atlas Cosmic MVP Implementation Plan

> **For Hermes:** выполнять как вертикальные проверяемые срезы. Источник требований: `docs/CUSTOMER_TZ_ORNA_ATLAS_IDEAL_MVP_2026-08-05_RU.md`. Не расширять scope за пределы P0 без отдельного решения.

**Goal:** привести первый экран Atlas к customer ТЗ: вид всей Земли, тонкий атмосферный лимб, несколько публичных точек на глобусе, кинематографичный стартовый перелёт и согласованный zoom/reset/resize.

**Architecture:** основной owner — frontend `web/components/atlas/AtlasExplorer.tsx` и близкие browser/unit tests. Публичные координаты брать только из уже разрешённых `AtlasPoint`/`AtlasCluster` DTO; скрытые/точные защищённые координаты не реконструировать. Night lights/day-night blending — отдельный product/data decision, не блокирующий первый вертикальный срез.

**Tech Stack:** Next.js, React, Cesium runtime from `/cesium/Cesium.js`, Playwright e2e, existing `globeZoom` helpers.

---

## Acceptance scope from customer ТЗ

### Included in this branch first

1. **Full-planet first frame:** default Cesium camera and reset show a full Earth disk without starting inside the atmosphere.
2. **Shared zoom bounds:** Cesium pinch, custom wheel and `+/-` buttons use the same min/max heights and expose diagnostics.
3. **Multiple public markers:** globe renders all currently loaded public locations/allowed clusters, not only the selected contextual point.
4. **Dawn/Day/Dusk/Night visual state:** mode affects marker emphasis while preserving visible non-selected public points.
5. **Cinematic entry:** first session load starts from full planet and flies to the selected/current dawn location over 2–4s with ease-in-out semantics; repeat focus interactions may remain shorter.
6. **Resize safety:** viewer resize/orientation changes do not reset camera to the broken default.
7. **Guest membership loading:** if encountered, `401` from `/memberships/me` remains anonymous/not-entitled instead of an endless loading state.

### Explicitly deferred unless product approves now

- Checkout amount `$35` and monetization-copy decision.
- Ambient audio on arrival.
- Expanded session card data.

### Product decision — separate task

- Night-side city lights / NASA Black Marble / VIIRS blending by real-time terminator is explicitly **out of this branch scope** and will be delivered as a separate task.
- Current branch must not fake night-side visuals or invent city-light data; it may only preserve the documented follow-up and avoid blocking the P0 camera/markers/intro slice on this larger imagery/data task.

---

## Current code anchors

- Main globe component: `web/components/atlas/AtlasExplorer.tsx`
  - constants around lines 59–67: imagery URL, focus height, zoom bounds, marker heights.
  - Cesium viewer setup around lines 222–516.
  - default camera `setView` currently uses `Cartesian3.fromDegrees(74, 27, 16000000)`.
  - reset currently returns to the same `74,27,16000000` destination.
  - selected focus currently uses `focusedLocationHeight = 750000` and `duration: 0.85`.
  - entities already loop over `points` and color markers by `selected`, `locked`, `dawnActive`.
- Zoom math: `web/components/atlas/globeZoom.ts` and `web/components/atlas/globeZoom.test.cjs`.
- Browser coverage: `web/e2e/public-navigation.spec.ts` already asserts Cesium diagnostics and close zoom behavior.
- API/runtime validation: `web/lib/api/sessions.ts` validates public coordinate visibility for atlas points.

---

## Implementation tasks

### Task 1: Add first-frame camera constants and diagnostics

**Objective:** make full-planet camera intent explicit and testable before changing behavior.

**Files:**
- Modify: `web/components/atlas/AtlasExplorer.tsx`
- Modify: `web/e2e/public-navigation.spec.ts`

**Steps:**
1. Add named constants near existing globe constants:
   - `const fullPlanetCameraLongitude = 74;`
   - `const fullPlanetCameraLatitude = 27;`
   - `const fullPlanetCameraHeight = <measured value>;` initially use existing `16000000`, then adjust if browser evidence shows disk not fully visible.
   - `const cinematicIntroDurationSeconds = 3;`
2. Replace duplicated `Cartesian3.fromDegrees(74, 27, 16000000)` in `setView` and `resetGlobe` with a helper `fullPlanetCameraDestination(Cartesian3)` or direct constants.
3. Expose diagnostics on `.globe-stage`:
   - `data-full-planet-camera-height`
   - `data-maximum-zoom-distance`
   - `data-cinematic-intro-duration`
4. Add/adjust Playwright assertion in `public-navigation.spec.ts` that `/atlas` exposes those diagnostics and starts near full-planet height before selected focus begins or after reset.
5. Run targeted test expecting RED if current behavior/focus immediately violates the new assertion.

**Verification:**

```bash
cd web && npx playwright test e2e/public-navigation.spec.ts -g "globe.*full planet|full-planet|reset" --project=chromium
```

---

### Task 2: Preserve all public markers while filtering/emphasizing selected mode

**Objective:** customer sees multiple public points on the globe simultaneously, without leaking hidden coordinates.

**Files:**
- Modify: `web/components/atlas/AtlasExplorer.tsx`
- Modify: `web/e2e/public-navigation.spec.ts`

**Steps:**
1. Confirm the `points` prop passed to `CesiumGlobe` is `atlasPoints`, not only `locations`/selected contextual point.
2. If `CesiumGlobe` currently receives filtered `locations`, change it to receive `atlasPoints` or `allLocations` plus allowed clusters while card carousel remains filtered.
3. Keep marker rendering bounded to `isAtlasPoint`/`AtlasCluster` public DTOs from `web/lib/api/sessions.ts`.
4. Add marker diagnostics:
   - `data-globe-point-count`
   - `data-globe-selected-mode`
   - `data-globe-active-dawn-count`
5. In e2e mock data, assert point count is greater than one and visible marker count is not reduced to one when mode changes.

**Security invariant:** do not create or derive coordinates client-side. Only render DTO coordinates already validated as public by `validateAtlasPointsResponse`.

---

### Task 3: Implement cinematic first-session entry

**Objective:** first load tells the story: whole planet → smooth flight to current selected/dawn location.

**Files:**
- Modify: `web/components/atlas/AtlasExplorer.tsx`
- Modify: `web/e2e/public-navigation.spec.ts`

**Steps:**
1. Add a session-scoped intro gate, e.g. `sessionStorage.getItem("orna:atlas:intro-seen")`.
2. On initial viewer ready + selected location available:
   - keep initial `setView` at full planet;
   - schedule one `camera.flyTo` to selected/current dawn location;
   - duration `2–4s`, target `3s`;
   - use Cesium easing if available (`EasingFunction.QUADRATIC_IN_OUT` or equivalent).
3. Mark intro seen after scheduling/starting the first intro.
4. Keep explicit focus requests (`focusRequest`) responsive; they may use a shorter duration after user clicks.
5. Respect reduced-motion if project has an existing pattern; if not, use a reduced duration but do not skip stable camera state.
6. Add Playwright probe around `Camera.prototype.flyTo` to assert the first intro duration/easing and that repeat focus does not re-run the long intro in the same session.

---

### Task 4: Unify zoom/reset/resize behavior

**Objective:** mouse wheel, buttons, pinch and reset obey the same documented bounds and never return to the broken close-atmosphere default.

**Files:**
- Modify: `web/components/atlas/AtlasExplorer.tsx`
- Possibly modify: `web/components/atlas/globeZoom.ts`
- Modify/add tests: `web/components/atlas/globeZoom.test.cjs`, `web/e2e/public-navigation.spec.ts`

**Steps:**
1. Ensure `minimumGlobeZoomDistance` and `maximumGlobeZoomDistance` are used in all paths:
   - Cesium screen space controller;
   - custom wheel handler;
   - button `changeZoom`;
   - zoom disabled state.
2. Add reset e2e: zoom/focus away, click reset, assert camera height returns near `fullPlanetCameraHeight` and not `focusedLocationHeight`.
3. Add resize e2e: move camera to a known height, resize viewport, assert height remains within tolerance and does not snap to old/default broken value.
4. Re-run close zoom pickability canary to ensure marker heights remain below camera floor.

---

### Task 5: Atmosphere visual tuning after camera fix

**Objective:** avoid assuming camera fix alone solved the orange blob.

**Files:**
- Modify: `web/components/atlas/AtlasExplorer.tsx`
- Optional docs update if tuning is intentionally deferred.

**Steps:**
1. After full-planet camera is verified, inspect live screenshots/video on desktop and mobile viewport.
2. If atmosphere remains too intense, tune Cesium `skyAtmosphere`/globe lighting parameters in the same component.
3. Keep settings conservative and expose non-sensitive diagnostics if browser tests need to prove they are active.
4. If tuning cannot be deterministically tested locally, document manual visual smoke evidence in PR handoff rather than claiming automated proof.

---

### Task 6: Night-side product decision record

**Objective:** prevent the largest visual gap from becoming an implicit omission.

**Files:**
- Modify: `docs/ORNA_ATLAS_COSMIC_MVP_IMPLEMENTATION_PLAN_RU.md` or add a follow-up spec/ADR only if decision becomes durable.

**Steps:**
1. Record current source limitation: ArcGIS World Imagery is daylight imagery and cannot produce city lights/night side.
2. Ask product whether night lights are launch scope or post-launch.
3. If launch scope: create a separate plan for imagery layer licensing/data/performance/test approach.
4. If post-launch: leave explicit follow-up in PR handoff.

---

## Test and validation matrix

### Narrow first

```bash
cd web && npx playwright test e2e/public-navigation.spec.ts -g "globe" --project=chromium
cd web && node components/atlas/globeZoom.test.cjs
```

### Required frontend checks after code slices

```bash
cd web && npm run typecheck
cd web && npm run lint
cd web && npm run build
```

### Repository-level checks before final PR when feasible

```bash
python -m pytest
python -m ruff check .
cd web && npm run api:check
cd web && npm run test:unit
cd web && npm run typecheck && npm run lint
```

---

## Risks and guardrails

- **Privacy:** do not broaden public DTOs or reveal exact protected coordinates. Marker rendering must consume existing public atlas DTOs only.
- **False green:** diagnostics alone are not enough; pair attributes with real camera height/probe behavior and visible canvas assertions.
- **Mobile GPU variance:** atmosphere/LOD smoothness requires at least mobile viewport Playwright plus live smoke if available.
- **Empty globe risk:** with only ~6 public locations, marker design must make sparse Atlas feel intentional.
- **Night lights:** requires data/licensing/performance decision; do not fake with invented runtime data.

---

## Initial branch state

- Branch: `feat/atlas-cosmic-mvp`
- Preserved unrelated untracked files:
  - `.env.pre-billing-20260730`
  - `.hermes/plans/2026-08-03_085748-lifetime-membership-review-fixes.md`

---

## Progress checkpoint — 2026-08-06

Completed first vertical slice:

- Added explicit full-planet camera constants and diagnostics in `web/components/atlas/AtlasExplorer.tsx`.
- Kept default and reset camera aligned to the same full-planet destination.
- Added first-session cinematic intro: full planet first, then `flyTo` to selected/current dawn location with 3s ease-in-out; repeated focus in the same session remains short.
- Passed all atlas points into the globe renderer so multiple public points can render simultaneously while carousel/list filtering remains mode-specific.
- Added diagnostics for rendered point count, selected listening mode, active dawn count and zoom bounds.
- Added Playwright coverage for:
  - full-planet first frame before cinematic focus;
  - multiple point diagnostics on the globe;
  - reset returning to full-planet height;
  - resize preserving the current focused camera instead of snapping back to default.

Verification already run:

```bash
cd web && npx playwright test e2e/public-navigation.spec.ts -g "full-planet camera|10 km floor|selected location opens|markers remain selectable|bounded zoom and reset|resize preserves|manual camera controls" --project=chromium
cd web && node components/atlas/globeZoom.test.cjs
cd web && npm run typecheck
cd web && npm run lint
cd web && npm run build
```

Next remaining slices:

1. Browser/visual smoke for atmosphere limb after full-planet camera correction.
2. Run broader repository checks / final review before PR candidate.

Separate follow-up task:

- Night-side city lights / real-time day-night blending is out of scope for this branch by product decision on 2026-08-06.
