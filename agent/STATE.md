# Forge project state

Phase: IMPLEMENTATION_1 — security containment and regression baseline

Last updated: 2026-09-24 (T-005 verified; roadmap P0 implementation complete; release-device checks pending)

## Verified current state

- Forge is a single-process Flask application (`forge_backend.py`) serving a same-origin static HTML client and JSON API, backed by a project-local SQLite database at `instance/forge.db` through Flask-SQLAlchemy.
- Flask-SocketIO runs in threading mode. The client is a single `static/forge_demo.html` file that uses `fetch`, direct DOM rendering, and Socket.IO.
- An Expo Router application in `mobile/` is a thin WebView wrapper around a user-configurable Forge server URL; it is not a native implementation of Forge workflows.
- Roles are `trade`, `grad`, `business`, and `admin`. Admin self-registration is excluded; business listing and alumni-verification approval workflows exist.
- The working tree already contains an unrelated, pre-existing modification to `mobile/src/app/index.tsx`. It was not changed by this documentation task.

## Current objective

Establish a secure, tested baseline around the existing Flask/web/WebView prototype before feature expansion or migration work.

Developer tooling now includes a deterministic local autonomous-task MVP (`scripts/forge-auto`). It is limited to dependency-satisfied `SAFE_INCREMENTAL` tasks and does not alter product architecture or behavior.

## Immediate gates

1. Continue into ownership, listing-lifecycle, and analytics hardening only after the corresponding regression baseline exists.
2. Keep the prototype architecture in place while extracting only tested seams.

## Deliberate non-decisions

- PostgreSQL is a future migration, not current project state, and requires human approval.
- A backend, web-framework, or authentication replacement is not authorized by discovery alone.

## IMPLEMENTATION_1 progress

- T-001 is complete: `build_app_config()` rejects missing, default, or short `FORGE_SECRET_KEY` values in `FORGE_ENV=production`; local development receives a process-local random key instead of a predictable fallback.
- Production session cookies are explicitly `Secure`, `HttpOnly`, and `SameSite=Lax`.
- `tests/` now provides an isolated temporary-SQLite Flask harness. It sets `FORGE_DATABASE_URI` before importing the application, creates/drops schema per test, and never uses `instance/forge.db`.
- T-002 is complete: Socket.IO rejects anonymous/suspended connections; `user:<id>` and `role:<role>` rooms derive only from authenticated Flask session identity. Client-supplied `userId`/`role` claims are ignored.
- Removed wildcard `cors_allowed_origins` in favor of default same-origin checking; the static frontend emits `join` without identity claims.
- Added `tests/test_socket_security.py`. Verified host terminal result: full suite 15 passed in 1.86s, with 17 non-blocking deprecation warnings (`datetime.utcnow()` and SQLAlchemy `Query.get()`).
- `.venv-host/` is ignored locally via `.gitignore`.
- T-003 is complete (SAFE_INCREMENTAL): unsafe `/api/` requests carrying an authenticated Flask session require a session-bound random token in `X-CSRF-Token`, compared with `secrets.compare_digest`, plus same-origin Origin/Referer validation. Missing both origin headers fails closed; anonymous authentication flows remain token-free.
- Authenticated `GET /api/auth/csrf-token` returns `csrfToken` with `Cache-Control: no-store`. Tokens rotate on register/login/demo-login and are cleared on logout. Existing Flask signed-session authentication is unchanged.
- The central static API helper and direct multipart video upload send the token; multipart Content-Type is left to the browser. Client cache is cleared for identity/session changes, successful logout, and CSRF errors; late token responses cannot repopulate an obsolete cache. Failed logout remains visible as an error.
- Same-origin checks use the direct request scheme and Host, with no ProxyFix or forwarded-header trust. Deployment must present the browser origin to Flask directly; proxy integration remains separate work.
- Full host-venv suite: 56 passed, 179 non-blocking deprecation warnings in 10.49s, including Node-based frontend helper regressions. `git diff --check` passed.
- T-005 completes the roadmap P0 implementation sequence. The next implementation task is T-101, which expands authentication/authorization and ownership regression coverage before further refactoring.

## 2026-09-18 — T-004 SAFE_INCREMENTAL

Implemented in `/home/pablo/Documents/Programming/04-Projects/forge` at starting HEAD `ea8ffc3`; the stale mirror was not used. Exact HTTPS origins come from build-time configuration with no production default. Missing configuration permits no connection. Persisted URL, Connect/save, initial WebView source and navigation share the pure policy; invalid saved values remain visible in recoverable settings without loading or automatic replacement. Existing mobile error handling is preserved. Popups and subframe navigation are blocked, mixed content is never allowed, Android cleartext is disabled through an Expo manifest plugin, and iOS ATS has no arbitrary-load/local-network exceptions.

Verified: 33 mobile tests; mobile lint, TypeScript, native preview/production config introspection and diff check pass. Isolated Forge suite: 56 passed, 179 existing deprecation warnings in 6.60s. Signed release-device tests remain a release gate (see MOBILE_PLAN.md). No commit or push from that task.

Preservation: Dockerfile hash matches the starting baseline. The static frontend changed concurrently during this session; this task never wrote it and leaves its current contents intact. The pre-existing mobile error handling remains. No existing locked dependency versions changed or entries were removed.

## 2026-09-24 — V2/profile-image checkpoint

Current checkout includes V2 navigation, mobile safe-area/account-menu/sign-out fixes, profile-image upload/delete/authenticated-serving API, Pillow image validation/canonicalization, and avatar rendering in shell/self/public profiles. Existing backend line-ending normalization is preserved. The frontend upload/replace/remove controls described in prior conversation are absent from this checkout; wiring those and broader identity propagation remain unfinished. No architecture change. Unrelated sandbox/Dockerfile remains excluded from this checkpoint.

## 2026-09-24 — T-005 SAFE_INCREMENTAL

T-005 is verified. Runtime debug and demo behavior are now explicit configuration rather than implicit deployment behavior. `FORGE_DEBUG` and `FORGE_DEMO_MODE` default off and may only be enabled with `FORGE_ENV=development`. Invalid boolean values fail startup rather than being interpreted loosely.

`FORGE_ENV` is validated against development, test, staging, production, and prod. Unknown or misspelled environment names fail closed. Staging and production/prod require a non-default secret of at least 32 characters and use Secure session cookies. The `.env.example` placeholder secret is explicitly rejected for deployments.

`/api/auth/demo-login`, the `seed-demo` CLI command, and automatic startup seeding are disabled unless explicit local demo mode is active. Flask debug mode by itself no longer enables demo authentication.

Verification: focused configuration/CSRF suite **73 passed, 288 warnings in 9.65s**; full isolated Forge suite **93 passed, 377 warnings in 10.60s**. Backend compilation, frontend CSRF/logout regressions, and `git diff --check` passed. Warnings remain existing datetime/SQLAlchemy deprecations. `sandbox/Dockerfile` remains unrelated and excluded.

All roadmap P0 implementation tasks T-001 through T-005 are now complete. T-101 is next.

## 2026-09-24 — T-101 SAFE_INCREMENTAL

T-101 is verified as a regression-baseline task with no production behavior change.

Added `tests/test_authz_regressions.py` covering public self-registration roles, admin self-registration rejection, student email-domain enforcement, duplicate usernames, failed/suspended/successful login behavior, student/business/admin role boundaries, unapproved business listing denial, alumni-verification role gating, notification list/read/read-all ownership, hidden-profile owner/admin exceptions, profile-view recording, business approval, listing approval creating a live opportunity, and alumni-verification approval.

The initial run exposed a test-fixture schema mistake (`Notification.kind` instead of the real `Notification.type`); production code was not changed. After correcting the fixture, the dedicated T-101 suite passed **25 tests with 133 warnings in 5.94s**.

Full verification: **118 passed, 510 warnings in 15.04s**. Frontend CSRF/multipart/identity/concurrency/logout regressions, backend compilation, and `git diff --check` passed. Existing datetime/SQLAlchemy deprecation warnings remain out of scope.

T-102 completed on 2026-09-24. Uploads now use request-size preflight plus bounded streaming, supported-container signature checks, isolated configurable storage, fail-closed ffmpeg processing when available, and authenticated media serving constrained to active post/feed authorization. Soft removal immediately revokes access while physical bytes remain pending a separately approved irreversible retention/deletion policy.

Dedicated T-102 verification: **10 passed, 58 warnings in 3.93s**. Full Forge verification after the autonomy-runtime additions: **139 passed, 568 warnings in 17.05s**. Backend compilation and `git diff --check` passed.

T-103 completed on 2026-09-24. Password-reset tokens are stored as SHA-256 digests; the plaintext token is restricted to the explicit local debug response, and email fallback/failure logging omits sensitive content. `sandbox/Dockerfile` remains unrelated and excluded.

## 2026-09-24 11:07 UTC — Autonomous T-105

- T-105 completed with reviewer PASS and deterministic checks passing.
- Next dependency-satisfied SAFE_INCREMENTAL task: T-106.

## 2026-09-24 14:11 UTC — Autonomous T-106

- T-106 completed with reviewer PASS and deterministic checks passing.
- Next dependency-satisfied SAFE_INCREMENTAL task: T-202.

## 2026-09-24 14:44 UTC — Autonomous T-202

- T-202 completed with reviewer PASS and deterministic checks passing.
- Next dependency-satisfied SAFE_INCREMENTAL task: T-203.

## 2026-09-24 — T-203 / Issue #1 first extraction

On `codex/t-203-backend-extraction`, added behavior tests against the original implementation, then moved six notification/onboarding handlers into `forge_routes/notifications.py` and `forge_routes/onboarding.py`. Existing application/database creation, models, login/CSRF hooks, Socket.IO, media, and clients remain in place. Explicit factory dependencies avoid importing a second app during direct-script startup. No migration or fundamental architectural decision was needed.

This is a bounded first increment of T-203 for PR review against `master`; wider extraction remains unfinished in TASKS.md. Nothing has been merged. Verification evidence is recorded in TEST_RESULTS.md.

## 2026-09-24 — T-203 / Issue #3 profile increment

Notification/onboarding PR #2 is merged in starting commit `5dafe2a`. On `codex/t-203-profile-extraction`, 50 new profile regression cases passed before moving the five required handlers to `forge_routes/profile.py`. The factory reuses the existing app/database dependencies and security policy. Image/storage/public-profile handlers remain in place (D-010); API contract, schema, clients, session/CSRF, Socket.IO, and retention are unchanged.

Full suite passes before and after: **256 tests**, no skips. Route/schema/AST comparisons and `git diff --check` pass; detailed evidence is in TEST_RESULTS.md. This increment is prepared for human review against `master`, without merging. T-203 stays open for the remaining extraction work.

## 2026-09-24 — Issue #6 web profile export

On `codex/web-profile-data-export` from `0706445`, replaced the existing student/business export links with a shared accessible button and added the same control for admins. The existing session API helper now optionally returns successful raw responses for downloading. Busy deduplication, persistent live status, retryable errors, filename fallback, and stale-account protection are covered by Node regressions invoked through pytest. Backend, mobile, API payload/auth policy, and navigation remain unchanged. Full suite: 257 passed; prepared for PR review against `master`, without merging.

## 2026-09-26 — T-203 / Issue #5 analytics increment

Starting from `2193553` on `master` (profile PR #4 and web export PR #7 merged), added 28 analytics regression cases and extended direct-script startup coverage before production extraction. The three analytics GET handlers now live in `forge_routes/analytics.py`, using explicit existing dependencies and unchanged T-106 metrics. No client, model, security-policy, or transaction changes.

Full suite before/after: **285 passed**, no skips; all **66 URL rules**, **23 tables** including constraints/indexes, and **118 original top-level definitions** match after normalizing moved dependency names. Prepared on `codex/t-203-analytics-extraction` for human PR review against `master`, without merging. T-203 stays open for identity/remaining workflow/media work.
