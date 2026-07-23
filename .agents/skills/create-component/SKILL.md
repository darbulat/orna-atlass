---
name: create-component
description: "Create or extend ORNA Atlas Next.js and React UI components. Use for TSX routes, interactive controls, typed API consumption, player integration, responsive styling, accessibility, or component-level browser behavior."
---

# Create an ORNA Component

## Shape the behavior

1. Read `AGENTS.md`, `docs/CURRENT_STATE.md`, and relevant domain rules.
2. Inspect the owning route, nearby components, shared styles, API client, generated types, and existing Playwright scenarios.
3. Define loading, empty, success, locked, unavailable, invalid-response, and network-error states before editing.
4. Add the narrowest failing reducer, resource, or Playwright regression first.

## Build within existing boundaries

- Prefer server components and add `"use client"` only around interaction or browser state.
- Reuse existing layout, Atlas, navigation, authentication, and player primitives instead of creating parallel state owners.
- Keep playback in the persistent global player; preserve grant refresh, seek, abort, and session-switch behavior.
- Consume `web/lib/api/generated.ts` through the established typed clients. Fail closed on malformed responses.
- Prevent stale requests from overwriting newer selections and clean up effects, media resources, and listeners.
- Render truthful unavailable states; never fabricate dawn times, media, coordinates, membership, or API success.

## Guard users and public data

- Preserve keyboard access, visible focus, semantic controls, labels, status announcements, and responsive touch targets.
- Avoid exposing exact coordinates, internal object keys, grant tokens, arbitrary metadata, or service timestamps.
- Keep conversion analytics bounded to approved event-name and placement pairs; never send personal data, URLs, coordinates, or session identifiers.
- Preserve anonymous public playback and show membership gates only when the access policy requires them.

## Verify

1. Run the closest frontend unit or Playwright test first.
2. Run `cd web && npm run typecheck && npm run lint`.
3. Run `cd web && npm run test:e2e` for changed journeys when dependencies are available.
4. Run backend contract tests and `cd web && npm run api:check` when the component depends on a changed API shape.
5. Inspect mobile and keyboard behavior, truthful error copy, request races, and the final diff.
