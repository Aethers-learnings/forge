# Forge project state

Current implementation (2026-10-09): PR #27 merged the directed blocking core. Ownership-v2 service/API/web rehearsal and Issue #28 participant-safe delivery are implemented; legacy remains the default and production v2 is not enabled. T-201 rollout/analytics/FK gates and T-107 reporting/reviewer/policy gates remain open. Dated entries below preserve their historical scope.

## 2026-09-28 — repository navigation cleanup

The root and mobile READMEs now describe the current architecture and checks; [the engineering records index](README.md) provides a starting point for decisions and status. Expo's unused starter reset command was removed, the starter Explore content became a Forge About screen at the same route, generated profile-image test directories are ignored, and TypeScript recognizes the existing CSS imports. No backend, schema, or social behavior changed. T-107 and T-201 gates remain as described below.

Phase: IMPLEMENTATION_1 — security containment and regression baseline

Last updated: 2026-10-09 (owned service/API/web and directed blocking merged; Issue #28 delivery implemented; T-201 rollout and T-107 reporting/reviewer release gates remain pending)

## Verified current state

- Forge is a single-process Flask application (`forge_backend.py`) serving a same-origin static HTML client and JSON API, backed by a project-local SQLite database at `instance/forge.db` through Flask-SQLAlchemy.
- Flask-SocketIO runs in threading mode. The client is a single `static/forge_demo.html` file that uses `fetch`, direct DOM rendering, and Socket.IO.
- The Expo Router application includes native authentication/profile/feed/opportunity/notification workflows plus an HTTPS-restricted WebView fallback. Native networking/messaging remains unimplemented.
- Roles are `trade`, `grad`, `business`, and `admin`. Admin self-registration is excluded; business listing and alumni-verification approval workflows exist.
- Issue #9 began on a clean `codex/t-104-ownership-design` branch at `d4a0516`; its changes are documentation-only. Earlier working-tree observations in session records are historical.

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

## T-104 / Issue #9 design submitted for review (2026-09-26)

Prepared [OWNERSHIP_DESIGN](OWNERSHIP_DESIGN.md): current source trace, concrete target entities, authorization matrix, proposed API/client/socket changes, SQLite migration/rollback stages, threats and future integration tests. D-012–D-015 remain proposed; T-104 is unchecked pending human architecture review, and T-201/native messaging are not unblocked. No production model, route, client, database, migration or authentication behavior changed. Current shared-state defects remain present. Validation is recorded in `TEST_RESULTS.md`; requested PR target is `master`, with no merge.

## 2026-09-28 — approved design, mandatory blocking/reporting

The user approved D-012–D-015 as proposed. PR #10 is already merged; this documentation follow-up uses `codex/t-104-approval-safety-gate` from master `7327929`. T-104 design/review is complete; prior pending-approval statements above are historical. T-201 can proceed from the approved design through its remaining gates; no migration/runtime/client work occurred here. D-016 / T-107 makes implemented and tested blocking/reporting mandatory before social production completion. Detailed block effects, report persistence/API, moderation evidence access and retention remain follow-up design work. Current ownership defects remain unfixed; no new merge is authorized.

## 2026-09-28 — T-107 / Issue #12 design proposal

[SAFETY_DESIGN](SAFETY_DESIGN.md) proposes directed blocking, pair-wide contact denial, private reporting and narrowly audited reviewer evidence, future API/client contracts, migration/rollback and executable test requirements. Marked product/policy choices await human review. This documentation-only increment does not implement or verify the safety system; T-107 and social production completion remain open. Current shared social routes remain insecure pending the D-012–D-015 implementation.

## 2026-09-28 — T-107 core design approved

The user approved directed pair-wide blocking, cancellation/disconnection and endorsement revocation with retained member-only read-only history; unblock restores nothing and follows the normal cooldown. Authenticated authorized-evidence reports, explicitly audited reviewer access without ordinary admin access, and no automatic sanction on submission are approved. Retention, erasure, appeals/notices, emergency access, reviewer provisioning, anonymous reporting, evidence-window size and rate-limit policy are separate later decisions. This status update changes documentation only; T-107 implementation, tests and the production gate remain open.

## 2026-09-28 — T-201 owned-social revision rehearsed

Implemented ordered atomic SQLite revision
`20260928_02_owned_social_schema` on top of the frozen baseline. It adds the six
approved D-012 owned-social tables without moving legacy data, switching
runtime routes, or globally enabling FK enforcement.

Migration failure injection tests now prove baseline, upgrade and downgrade DDL
roll back atomically. Copy-only rehearsal against a consistent real-database
backup proved 23→29→23→29 schema round trips, physical preservation of all five
legacy social tables, membership triggers/message retry uniqueness, clean
integrity/FK checks, live-owned-data downgrade refusal and repeatable final
upgrade. The real `instance/forge.db` remained unchanged, unmanaged and without
owned-social tables.

T-201 remains open. Before owned-social ORM/service integration, replace or
guard the historical `db.create_all()` bootstrap so migration-owned tables
cannot be created outside the ledger. Runtime ownership enforcement and D-014
client cutover remain unimplemented.

## 2026-09-28 — Issue #16 migration-managed bootstrap

On `codex/issue-16-migration-bootstrap` from current master `dac4ef8`, application import/direct-script/Flask-run startup now verifies managed HEAD before serving. Persistent databases are never created, baselined, upgraded or repaired automatically. Missing, unmanaged, behind-head, checksum-invalid and drifted databases fail with operator guidance. Recovery command discovery remains available; demo seeding verifies readiness and retains local gating.

Explicit `db-init --confirm-schema-change` exclusively reserves a new file and atomically constructs the frozen baseline, ordered revisions and ledger. Fresh in-memory development/test initialization and isolated pytest fixtures use that same migration authority, with no ORM create/drop bootstrap. Application WAL/NORMAL hooks are engine-local; persistent startup uses a separate read-only connection. Frozen baseline/revision files are unchanged; no real `instance/forge.db` was opened or mutated in this task.

This resolves the earlier bootstrap prerequisite only. T-201 remains open for social ORM/services, ownership-v2 API/client cutover, whole-schema FK review, recovery/rollout and other remaining gates. Social behavior and T-107 safety readiness are unchanged. See TEST_RESULTS for verification.

## 2026-09-29 — Issue #18 internal owned-social service, PR #21

Six ORM mappings match migration revision 02. The unwired internal service handles actor-scoped graph discovery, directed requests, transitions, general endorsements, two-member conversations, retry-key messages and explicit read cursors under serialized SQLite write transactions. PR review fixes preserve the original create precondition for same-direction pending retries, make already-current desired endorsement retries no-ops, and scope normal endorsement reads to the caller's direction. No migration, persistent database, legacy route/client/socket/notification/analytics cutover or T-107 implementation occurred. T-201 and T-107 remain open; current legacy social endpoints are not production-ready.

## 2026-09-29 — Issue #22 ownership-v2 HTTP rehearsal

A fail-closed process-wide `FORGE_SOCIAL_MODE` selects legacy (default), authenticated/CSRF-protected maintenance 503, or owned-only v2 for the nine affected route operations. V2 requires capability 2 after auth/CSRF, uses caller-scoped signed pagination, member-only retained history and explicit read cursors, and emits no social delivery. The legacy graph is quarantined in v2; no per-user cohort or dual write exists. This is not production-ready: web/WebView, sockets/notifications, student analytics, persistent rollout/FK/admin-removal review, and mandatory T-107 remain separate gates. See TEST_RESULTS for isolated process and full-suite evidence.

## 2026-09-29 — T-201 web/WebView ownership-v2 rehearsal

The shared static web/WebView product now consumes ownership-v2 networking and messaging when the process explicitly selects v2. Public no-store `/api/social-config` exposes only the already-fixed process mode; the client pins that contract for its current account/session and never falls back after errors. Legacy remains the default and its social transport is preserved. Production v2 is **not enabled** by this increment.

Implemented: incoming/outgoing requests, exact optimistic versions and desired endorsements, per-section and conversation cursors, real-peer conversation create/reuse, bounded ordered history, stable user-driven message retries, contiguous observed-message read advancement (unloaded/unobserved incoming gaps stop progress; loaded own messages do not), generic read-only/error UI, and account-generation isolation. Session changes clear all social state and retire the old socket; late responses cannot restore it. No native networking/messaging or WebView authentication/transport change.

T-201 remains open: social socket/notification delivery, student analytics cutover, persistent rollout/recovery and whole-schema FK/admin-removal review are outstanding. T-107 blocking/reporting remains mandatory before social production completion. Native social networking/messaging and signed-device verification remain outstanding. See TEST_RESULTS for executable evidence.

## 2026-10-09 — Issue #28 participant-safe ownership-v2 delivery

Started from clean fetched/pulled master `876819abd0505b1964c21aa2a68e12ccf676ab27` (merged PR #27) on `codex/t201-social-delivery`. The existing owned service now inserts generic request/accept/message Notification rows inside the same `BEGIN IMMEDIATE` business transaction. Connection-local delivery intents run after commit; each packet rechecks active endpoints, pair/block state and relevant membership/version under a short SQLite reservation through enqueue. Only authenticated user rooms receive delivery; role/admin status grants no private override. Socket failure leaves committed domain and Notification rows intact; HTTP refresh is recovery.

Message invalidation is exactly `{conversationId,lastSequence}` for both participants/devices; only the other member gets a persistent message notification. Request creation notifies its recipient, acceptance its original requester. Retries/no-ops/denials add nothing. Blocking/terminal transitions retire unread owned navigation hints transactionally without deleting rows. Notification list/count/export projection authorizes existing type/link references and fails closed; unblock/reconnect cannot restore retired contact. Moderation retires target sockets using the existing single-process room manager, with active-account checks on reconnect/join and no global cookie revocation.

Web/WebView re-fetches authorized history/list state for minimal invalidations, takes v2 notification wording/counts from HTTP, drops old-account/generation packets and retires sockets on account changes. Legacy and maintenance are preserved; production v2 was not enabled. PR #26, native social, migration/schema/default configuration, and the real `instance/forge.db` were not used or changed. T-201 remains open for analytics, persistent rollout/recovery, whole-schema FK/admin-removal review and cutover; T-107 remains open for reporting/reviewers and policy gates. See TEST_RESULTS for exact evidence.

## 2026-10-09 — PR #29 client review fixes

Resolved the four independently reproduced review findings in the shared web/WebView client: automatic message refresh preserves the current same-thread draft, focus and selection; CSRF rejection retires the obsolete socket and opens a replacement without replaying the failed mutation; ordinary notifications remain active in maintenance mode; owned message hints select the referenced conversation through authorized HTTP. Late notification-click responses cannot navigate another account. Node and Chromium coverage is recorded in TEST_RESULTS. PR #29 remains unmerged for human review; the broader T-201/T-107 and production release gates above remain open.

## 2026-10-09 — PR #29 multipart recovery follow-up

The re-review found a remaining CSRF recovery gap in the independent video-upload fetch. JSON and multipart failures now share generation-checked session invalidation: same-account CSRF rejection replaces the realtime socket without replaying the upload, while current 401 responses expire the session without reconnecting. Upload work checks the account generation after token acquisition, HTTP response and error-body parsing; obsolete successes/errors cannot refresh, sign out or disconnect another account. Maintained Node and Chromium regressions cover the repair; evidence is in TEST_RESULTS. Backend delivery, schemas, native source and default legacy mode remain unchanged. PR #29 stays unmerged and broader T-201/T-107 release gates remain open.
