# Mobile plan

Status: T-205 native migration in progress; WebView remains the supported fallback while native workflows are added incrementally.

## 2026-10-09 — PR #26 API request deadline

The native API client applies one 15-second AbortController deadline to fetch and response-body consumption. An aborted body read must reject with the existing timeout message and `network=true`, `timeout=true`; it cannot become a successful null response. Every completion clears the timer. Completed malformed JSON retains the existing null-body behavior, and completed HTTP errors retain their status/body/message. Session/CSRF, server-origin restrictions and mutation semantics are unchanged; the transport never retries a mutation automatically.

Real Node fetch regressions cover immediate 200/503 headers followed by a body that never completes, accelerating only the deadline. Deterministic tests cover cleanup after body completion, body abort, late success after abort, malformed JSON and server errors. React Native currently buffers its XHR response before fetch resolves; the shared helper also protects standards-fetch environments such as Expo web. Signed iOS/Android device tests, including lifecycle/background timer behavior, remain release checks rather than claims made by the Node harness. Validation is in TEST_RESULTS. This increment does not release native social workflows or enable production v2.

## Verified implementation — T-004

The Expo WebView wrapper, Android back handling, settings and existing error display remain. Approved exact HTTPS origins are required at every server entry point. Missing configuration opens settings and permits no connection. Invalid saved addresses and storage failures are recoverable.

### Build configuration

- Supply `FORGE_MOBILE_ALLOWED_ORIGINS` as comma-separated complete HTTPS origins in the build environment. Non-default ports must be explicit. Paths, queries, fragments, credentials and wildcard hosts fail config validation. Explicit HTTPS IP origins authorize those IP/port combinations; otherwise IP origins are rejected.
- No hostname/default is embedded. Empty/missing configuration allows no server; malformed nonempty configuration fails evaluation. These values are public app configuration, not secrets.
- `app.config.js` embeds origins in `extra.forgeSecurity`. Supply the same environment for native builds and JS exports/updates. Native transport changes require a new binary. Expo Go is not release-native policy evidence.
- Optional development override requires `EAS_BUILD_PROFILE=development`, `FORGE_MOBILE_DEVELOPMENT=1`, and `FORGE_MOBILE_DEV_ORIGINS` containing explicit HTTPS origins; runtime also requires `__DEV__`. Preview/production ignore these origins. No HTTP exception exists, including development: use a trusted HTTPS endpoint.
- The Expo plugin enforces Android cleartext false; iOS ATS contains no arbitrary-load or local-network exceptions. EAS profiles were not modified.

### Manual release-device gates

On signed Android and iOS preview/release builds:

1. Inspect the final merged/packaged Android manifest and iOS Info.plist for cleartext false, no network-security override and no ATS exceptions.
2. Verify approved HTTPS login/session/CSRF workflows, back navigation and settings recovery; invalid saved values must not load or silently save.
3. Exercise redirects, links, forms, JS location changes, deceptive hosts, unexpected ports/IPs, custom schemes, target=_blank and window.open with/without user gestures. Disallowed destinations must neither load nor open an external browser/app.
4. Verify HTTP, mixed-content and untrusted/expired-certificate failures; missing configuration permits no connection and preview cannot use development overrides.
5. Verify workflows do not depend on popups or subframe navigation, both deliberately blocked. Native callback timing and WebView behavior require devices; Node screen tests mock native components.

No signed builds, packaged-binary inspection or device tests were performed. Introspection verifies generated configuration but does not replace those checks.

## Verified T-205 native progress — 2026-09-24

Native Expo workflows currently implemented and test-protected:

- authentication/session check and sign in/out;
- profile display and onboarding progress/advance/skip;
- native role-appropriate profile editing, including student/graduate skills and profile visibility controls;
- student/graduate opportunities and application toggle;
- notifications, unread counts, mark-one-read, and mark-all-read;
- role-scoped feed loading, text post creation, likes, and comments.

The WebView remains available as the full-product fallback. Native and WebView sessions are deliberately not bridged.

Native `fetch` cookie persistence and manual `Origin` behavior still require signed-device/simulator verification on iOS and Android before these flows are considered production-ready.

Native messaging remains blocked by the existing conversation/network ownership model: conversations do not yet carry secure participant identity and shared demo relationship state must not be exposed as a native production workflow until T-104/T-201 ownership and migration work is approved.

## Plan

1. T-004 implementation complete; perform the release-device gates above before release. Classification: SAFE_INCREMENTAL.
2. Establish a tested API contract shared with web, including session/CSRF behavior and error schemas. Classification: SAFE_INCREMENTAL.
3. Native authentication/session, profile/onboarding, profile editing, skills, and visibility flows are implemented; retain WebView fallback and complete signed-device session/CSRF verification. Classification: SAFE_INCREMENTAL.
4. Native opportunities/applications, notifications, and feed/post interactions are implemented. Continue safe native product slices; messaging remains blocked until ownership/realtime policy is corrected. Classification: SAFE_INCREMENTAL.
5. Add lifecycle-aware networking, caching, retry/error states, accessibility, touch/keyboard support, and device notification strategy. Classification: SAFE_INCREMENTAL.
6. Decide whether WebView retirement is appropriate only after measurable native parity, security, and support evidence. Classification: MAJOR_REVIEW.

The current Expo/WebView application remains during native-mobile parity work. A fundamental authentication change or a major third-party mobile service requires human approval.

## T-104 contract dependency (2026-09-26)

[OWNERSHIP_DESIGN](OWNERSHIP_DESIGN.md) proposes the future participant-safe contract and coordinated web/WebView transition; it does not implement native networking/messaging. Existing native authentication/profile/feed/opportunities/notifications remain unchanged, including separate native/WebView sessions. Native social work remains blocked on human approval of D-012–D-015 and T-201 migration readiness. Cached WebView compatibility, actor-scoped state and signed-device revocation checks are explicit future acceptance gates.

## Ownership approval and production gate (2026-09-28)

This update supersedes the earlier statements that D-012–D-015 await approval: the user approved all four decisions as proposed. Their target remains unimplemented; current schema, API, authentication and client behavior are unchanged. T-104 design/review is complete and T-201's design dependency is satisfied, with migration/integrity/recovery verification still required. Social networking is **not production-complete** until blocking/reporting is designed, implemented and tested under D-016 / T-107 and [OWNERSHIP_DESIGN section 8](OWNERSHIP_DESIGN.md#8-blocking-and-reporting-production-completion-gate). This includes server enforcement, private report handling, explicitly authorized audited moderation, web/WebView and released-native coverage, and security/race/rollback tests. No blanket admin private-message access or irreversible retention policy is approved.

## 2026-09-29 — shared WebView social compatibility

The static product rendered by the existing WebView now supports the explicitly configured ownership-v2 contract, including capability/version headers, paginated networking and history, real-peer conversation creation, retry-key messages, visible-message read state, read-only UI and per-account reset/stale-response guards. Native `fetch` and WebView cookies remain separate; no native social screen, session bridge, transport allowlist or fallback policy changed. Chromium narrow-screen tests verify the shared product, not signed iOS/Android WebViews. Device/session/visibility checks above remain release gates.

Production v2 is not enabled. Native networking/messaging, social socket/notification delivery, student analytics cutover, persistent rollout/FK/admin-removal review and mandatory T-107 blocking/reporting remain outstanding.
