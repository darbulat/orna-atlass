# Complete UX funnel delivery plan

## Scope
Implement remaining deterministic requirements from `docs/UX_FUNNEL_SPEC_RU.md` §§3–10. Keep §11 open questions out of runtime behavior: no autoplay, no anonymous listening cap, no offline/download promise until product policy is decided.

## Invariants
- Public exploration/playback remains ungated.
- Members-only summaries may be teased only for published sessions at publicly discoverable/generalized locations; detail/playback remains entitlement-gated and hidden coordinates never appear.
- Soft paywall appears only after a locked marker/card interaction or an actual 403 restriction.
- Existing audio continues through session-panel close via global PlayerProvider.
- Analytics payload is a bounded enum pair without user/session/location identifiers.
- No fictional checkout or magic-link delivery without configured e-mail infrastructure.

## Vertical slices
1. Contract + backend Atlas teaser summaries: access level in atlas summary, public-coordinate privacy canaries, frontend generated type sync.
2. Locked UI + soft paywall: locked marker/card, Join free, membership learn-more, close/focus management, canaries and analytics.
3. Session experience completion: favorite login hint, clickable species timeline, help tooltip, player actions/analytics, mini-player continuity; truthful disabled prev/next unless actual queue exists.
4. Discovery/home IA: popular cards with duration/inline play/session overlay, see-all/collections links, move mission/pricing/FAQ off home into about/membership.
5. Globe controls: configure Cesium inertia/zoom/pole/touch settings, drag threshold, explicit zoom/reset controls and interruption behavior with deterministic Cesium mock canaries.
6. Registration/membership: preserve real email/password + OAuth free signup, return-to session parameter, truthful early-access subscription-intent events. Magic-link transport is excluded because no mail provider/configuration exists; do not invent a successful send.
7. Analytics: add all required bounded §9–10 event names/placements end-to-end with API rejection canaries and browser request assertions.
8. Update current-state/domain docs, OpenAPI generated types, full backend/frontend/integration/E2E verification, exact staged review, PR/CI/Codex, reviewed commit deployment and post-deploy verification.

## Acceptance
- RED canary precedes each behavior-changing implementation.
- Backend privacy contract proves hidden locations stay absent and anonymous locked summaries reveal no detail/media.
- Existing 68 browser scenarios remain green; new flow canaries cover locked/public distinction, soft paywall timing, inline card play, favorite hint, timeline seek/help, controls, return URL, and analytics.
