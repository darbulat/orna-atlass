# Frontend role

## Mission

Deliver accessible Next.js behavior through generated API contracts and explicit UI state, including
truthful loading, denial, unavailable and recovery paths.

## Inputs

- accepted user journey and responsive/accessibility behavior;
- generated OpenAPI DTOs, API wrapper behavior and typed backend errors;
- relevant domain privacy/access rules and persistent player state transitions;
- existing component, unit-resource/reducer and Playwright coverage.

## Outputs

- minimal route/component/API-wrapper changes with typed state;
- keyboard, focus, ARIA, reduced-motion and non-WebGL/list fallback behavior where applicable;
- deterministic unit and browser regression coverage;
- explicit backend contract gaps rather than locally invented fields or policy;
- screenshots only when useful for human review and never committed user media by accident.

## Boundaries

- `web/app` composes routes, `web/components` owns interaction, and `web/lib/api` owns transport and
  generated DTO consumption.
- Do not hand-copy backend schemas, reconstruct protected coordinates or infer access from missing
  fields.
- Do not report dependency failure, malformed payload, locked content or missing media as success.
- Route components control the root player/provider; they do not create competing audio ownership.
- A visual workaround cannot redefine membership, publication, readiness or grant policy.

## Checks

Run the narrow unit or Playwright scenario, then `npm run api:check`, `npm run test:unit`,
`npm run typecheck`, `npm run lint` and `npm run build` as applicable. Run browser smoke for route,
player, authentication, responsive or accessibility behavior.

## Handoff

State the user-visible flow, API fields/errors consumed, state and accessibility paths covered,
checks run, browser limitations, backend dependencies and any deferred visual/performance risk.
