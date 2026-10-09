# Test results

## 2026-10-09 — PR #26 API timeout review repair

Starting PR head: `daf0e182b012e4cbdb99481c1c17084c116182b9`; fetched master: `e126d7de9277a20fc9f7d92a62125ab684ad7121` (merged PR #31). Existing project-local mobile dependencies were reused without lockfile changes.

- Before the fix, `node --test tests/api-timeout.test.cjs` (cwd mobile) produced **6 passed, 5 failed**. The established three assertions remained intact. Failures cover early timer cleanup, swallowed body abort, late success after abort, and real fetch stalled after 200/503 headers. The real-server tests have a cleanup watchdog so the defective implementation cannot hang the suite.
- After the fix, the same focused command produced **11 passed, 0 failed/skipped**. Only the 15-second deadline is accelerated to 250 ms in real-fetch tests; fetch, body consumption, AbortController and localhost transport remain real.
- `npm test` (cwd mobile): **64 passed, 0 failed/skipped**.
- `npm run lint`, `./node_modules/.bin/tsc --noEmit`, and `node --check` on the client/test: **passed**, each exit 0.
- `git diff --check`: **passed**.
- Current master plus the repaired PR snapshot merges cleanly, including all four project records. Its `npm test` also passes **64 tests**; lint and TypeScript each exit 0. Focused analytics/service/process-mode/frontend integration checks pass **43 tests, 158 existing warnings in 21.76s**. Backend tests use disposable migration-managed fixtures; the full backend/browser suite is not rerun for this mobile-only runtime repair.

Completed malformed success bodies still return null; malformed HTTP errors retain their status and null body; JSON HTTP errors retain their message/status/body without timeout/network flags. Cleanup is verified after successful body consumption, body timeout, network failure and server errors. No established expectation was weakened. No backend, static web, schema, migration, dependency, social default or production-v2 change; no real `instance/forge.db` access. Signed-device iOS/Android/session/background-timer checks remain release work.

## 2026-09-29 — PR #21 review fixes

- Focused owned-social model/service and migration/bootstrap suite: **74 passed, 92 existing warnings in 32.38s**. Regressions prove the original `expectedVersion:0` same-direction create retry (including concurrent calls) returns the pending edge without a second event; terminal re-request retries likewise stay no-op while older versions conflict. Already-current active and revoked endorsement retries accept the immediately preceding pre-commit version without a version/audit write; missing and older stale versions remain errors. Normal general-endorsement reads return only caller→peer, while disconnect still revokes both directions.
- Initial full runs exposed an intermittent pre-existing test-fixture reset defect: a previous test's SQLite connection could observe/recreate a reused path or WAL, causing unrelated duplicate-user or missing-table errors. The test harness now assigns a distinct migration-initialized SQLite path and application engine to every test, preventing cross-test reuse. Auth and owned-social checks after that fix: **51 passed**.
- Final full backend/web suite: **367 passed, 1486 existing deprecation warnings in 76.92s**. `git diff --check` passed. Migration history and the real `instance/forge.db` remained untouched; no existing social route, client, socket, notification or analytics cutover.

## 2026-09-28 — PR #17 review fixes

- Focused bootstrap/migration suite: `.venv/bin/python -m pytest -q --disable-warnings tests/test_database_bootstrap.py tests/test_migration_tooling.py` — **50 passed**. New subprocess cases compare bytes, size, mtime and sidecars for `db-status`/`db-verify` on existing DELETE-journal databases.
- Full backend/web suite: `.venv/bin/python -m pytest -q --disable-warnings` — **335 passed, 1394 warnings in 66.69s**.
- `git diff --check` passed. All databases in these tests were isolated fixtures; no persistent Forge instance database was inspected or modified.


## 2026-09-28 — repository cleanup

- Full backend/web suite: `.venv/bin/python -m pytest -q --disable-warnings` — **298 passed, 1394 warnings in 22.10s**.
- After `npm ci --ignore-scripts`, mobile `npm test` — **53 passed**; `npm run lint` and `npx tsc --noEmit` passed. Type checking initially found missing CSS declarations; `mobile/src/types/styles.d.ts` resolves those imports.
- After replacing starter Explore copy with the Forge About screen at the same route, mobile `npm test` again passed **53 tests**; lint and TypeScript passed.
- Documentation links and `git diff --check` verified. This cleanup does not test or implement future social safety behavior.

## 2026-09-28 — T-107 / Issue #12 design-only verification

- Isolated `.venv/bin/python -m pytest -q`: **290 passed, 1394 warnings in 28.76s**. Warnings are existing datetime and SQLAlchemy deprecations; no safety implementation tests exist yet.
- `git diff --check` and documentation link/anchor check passed. Diff contains only `agent/*.md`; no migration, runtime, client or dependency files changed.

Follow-up recording core design approval: full `.venv/bin/python -m pytest -q --disable-warnings` passed **290 tests, 1394 warnings in 34.10s**. Documentation-only status update; future blocking/reporting behavior is still unimplemented and untested.


Date: 2026-09-24

## IMPLEMENTATION_1 — T-003 CSRF/origin protection (2026-09-18)

| Check | Result | Evidence / scope |
| --- | --- | --- |
| Full host-venv suite | PASS | `.venv-host/bin/python -m pytest -q`: **56 passed, 179 warnings in 10.49s**; no skips. |
| Backend CSRF regressions | PASS | `tests/test_csrf_security.py`: valid/missing/wrong/non-ASCII tokens; session/identity binding; authenticated token access; rejected suspended access; foreign/malformed/null origins, Referer fallback and missing headers; default ports; ignored forwarded headers; GET/HEAD/OPTIONS; POST/PATCH/DELETE/PUT; multipart processing; anonymous register/login/demo/reset flows; authenticated login and logout/token rotation. |
| Frontend helper regressions | PASS | `tests/test_csrf_frontend.py` invokes Node.js on `tests/csrf_frontend.cjs`, exercising the actual inline helpers with mocked fetch/DOM: unsafe-method headers, custom-header preservation, safe/anonymous requests, concurrent token fetch deduplication, multipart Content-Type preservation, identity/same-account session changes, stale token responses, successful/failed logout. Inline JavaScript syntax is also checked. |
| Whitespace and diff review | PASS | `git diff --check`; reviewed backend/frontend/test changes. Only added/changed backend lines use LF where needed to pass the check; untouched existing line endings preserved. |
| Scope preservation | PASS | Baseline hashes confirm `mobile/src/app/index.tsx` and `sandbox/Dockerfile` byte-for-byte unchanged. Agent records updated only after the full test suite passed. No commit created. |

Warnings: 179 non-blocking `DeprecationWarning` / `LegacyAPIWarning` instances from existing `datetime.utcnow()` and SQLAlchemy `Query.get()` call sites, including `get_or_404`. The expanded suite exercises more of these existing paths; no warning suppression or modernization was included.

The first run was 55 passed / 1 failed: the DELETE test used a graduate account for an existing admin-only route. Its setup was corrected to use an administrator; production role authorization was retained. Initial diff checking also identified CR line endings on added backend lines; only those additions/changes were corrected.

Limits: frontend tests use Node mocks, not a live browser or mobile runtime. PUT has no current application route; tests prove missing CSRF is blocked and valid CSRF reaches the normal 405 response. DELETE reaches the authorized route's 404 lookup for a nonexistent post. No deployment/proxy compatibility claim is made; direct scheme/Host must match the browser origin. Original T-001/T-002 evidence below is historical.

## IMPLEMENTATION_1 — T-002 Socket.IO security

Evidence: verified user-pasted host terminal output, corroborated by inspection of the current implementation and tests.

| Check | Result | Evidence / scope |
| --- | --- | --- |
| Full suite using host venv | PASS | `python -m pytest -q`: 15 passed in 1.86s, 17 warnings. |
| Socket.IO regressions | PASS | Added `tests/test_socket_security.py`: anonymous/suspended connection rejection, private user-room isolation, ignored forged user/role claims, actual role membership, and no wildcard origins. |
| Origin and frontend inspection | PASS | Wildcard `cors_allowed_origins` removed for default same-origin checking; static frontend emits `join` without identity claims. Origin regression checks configuration, not a real browser handshake. |
| Original whitespace check | PASS | User-pasted `git diff --check` completed without output. |
| Host environment housekeeping | PASS | `.venv-host/` is ignored locally via `.gitignore`; confirmed with `git check-ignore`. |

The 17 non-blocking warnings concern deprecated `datetime.utcnow()` and SQLAlchemy `Query.get()`; no warning cleanup was included in T-002. T-003 CSRF/origin protection for HTTP mutations is next P0.

## IMPLEMENTATION_1 — T-001 session configuration and test isolation

| Check | Result | Evidence / scope |
| --- | --- | --- |
| Isolated Flask harness | PASS | `tests/conftest.py` sets a temporary `FORGE_DATABASE_URI` before app import; each test creates and drops its SQLite schema, leaving `instance/forge.db` unused. |
| Production secret fail-closed | PASS | 6 tests verify missing, historical/default, and short secrets are rejected. A subprocess test verifies actual `import forge_backend` fails with `FORGE_ENV=production` and no secret. |
| Production cookie configuration | PASS | Regression test and direct production import verify `Secure=True`, `HttpOnly=True`, `SameSite=Lax`. |
| Full available test suite | PASS | `.venv/bin/pytest -q`: 9 passed in 1.52s. |

Test environment note: the host Python lacked Forge dependencies and disallowed global package installation (PEP 668). A project-local `.venv` was used to install `requirements.txt` and run the suite; it is not application source.

## Verified discovery baseline

| Check | Result | Evidence / scope |
| --- | --- | --- |
| Repository inventory | PASS | Flask backend, static web client, Expo WebView app, SQLite instance directory, and all durable agent records were inspected. |
| Route inventory | PASS | 61 Flask route decorators plus Socket.IO `join` handler were mapped in `API_MAP.md`. |
| Model inventory | PASS | 22 SQLAlchemy models and their foreign-key/unique constraints were mapped in `DATA_MODEL.md`. |
| Authentication/authorization inspection | PASS (inspection only) | Session, role gates, public/admin/business routes, and ownership checks were reviewed; P0 gaps are documented in `SECURITY.md`. |
| Mobile transport inspection | PASS (inspection only) | WebView URL/configuration was reviewed; P0 permissive-origin/cleartext/mixed-content behavior is documented. |
| Working-tree diff check before documentation | PASS | Pre-existing change: `mobile/src/app/index.tsx` (30 added lines). This documentation task did not alter it. |

## Historical discovery limitations (before T-001/T-002)

- No automated application test suite was discovered, so no behavior-level unit, integration, browser, mobile, or security tests were run.
- The Flask server was not started and no database command was run, because this task is documentation-only and must not modify database contents.
- Dependency installation, mobile build, lint, and production deployment checks were not run.

## Required next evidence

Socket.IO identity-bound rooms, authenticated HTTP CSRF/origin protection, mobile HTTPS/navigation policy, debug/demo deployment configuration, and T-101 authentication/authorization ownership behaviors now have regression evidence. T-102 upload-boundary hardening is next.

## 2026-09-18 — documentation-session verification

- Fresh host-venv run: `.venv-host/bin/python -m pytest -q` — **15 passed, 17 warnings in 2.19s**. The original 1.86s result above is preserved as historical evidence.
- Initial sandbox run could not create the temporary test database; rerun with approved host filesystem access passed.
- `git diff --check` passed after the documentation edits. Reviewed the five-file documentation diff and compared file hashes with the pre-edit baseline: only the intended five agent records changed. `mobile/src/app/index.tsx` and `sandbox/Dockerfile` remain byte-for-byte unchanged.
- Existing `.gitignore`, backend, frontend, and untracked socket test changes are preserved. The backend already had line-ending normalization in its diff; it was not modified here. No commit created.

## 2026-09-18 — T-004 SAFE_INCREMENTAL

Implemented in `/home/pablo/Documents/Programming/04-Projects/forge` at starting HEAD `ea8ffc3`; the stale mirror was not used. Exact HTTPS origins come from build-time configuration with no production default. Missing configuration permits no connection. Persisted URL, Connect/save, initial WebView source and navigation share the pure policy; invalid saved values remain visible in recoverable settings without loading or automatic replacement. Existing mobile error handling is preserved. Popups and subframe navigation are blocked, mixed content is never allowed, Android cleartext is disabled through an Expo manifest plugin, and iOS ATS has no arbitrary-load/local-network exceptions.

Verified: 33 mobile tests; mobile lint, TypeScript, native preview/production config introspection and diff check pass. Isolated Forge suite: 56 passed, 179 existing deprecation warnings in 6.60s. Signed release-device tests remain a release gate (see MOBILE_PLAN.md). No commit or push. T-005 is next P0.

Preservation: Dockerfile hash matches the starting baseline. The static frontend changed concurrently during this session; this task never wrote it and leaves its current contents intact. The pre-existing mobile error handling remains. No existing locked dependency versions changed or entries were removed.

### Reproduction and limits

- `npm --prefix mobile test`: 33 passed, 0 failed in 2.39s. Node built-in runner and existing TypeScript transpilation; no test-framework dependency. Covers URL attacks, explicit ports/IPs, config defaults/isolation, persisted settings, Connect/save validation and storage errors, initial source, navigation and popup callbacks/props.
- Two tests run actual Expo `config --type introspect --json` for preview/production with development override variables set. Assert origins, development exclusion, Android cleartext false/no network-security override, and restrictive iOS ATS/no exception domains. Default-empty configuration was separately introspected successfully.
- `npm --prefix mobile run lint`: PASS without warnings. Added missing ESLint/Expo lint dev dependencies and configuration. Initial lint found two pre-existing issues: an apostrophe in the mobile error heading and the web theme hydration effect. Escaped the apostrophe without visible text changes and used useSyncExternalStore for server/client hydration snapshots.
- `mobile/node_modules/.bin/tsc --project mobile/tsconfig.json --noEmit`: PASS.
- `.venv-host/bin/python -m pytest -q`: 56 passed, 179 existing datetime/SQLAlchemy deprecation warnings in 6.60s; temporary SQLite harness only, no real application database use.
- `git diff --check`: PASS.
- Install warnings: 14 moderate npm audit vulnerabilities, deprecated ESLint 9.39.5 and pending/unapproved unrs-resolver postinstall script. No broad audit fix or script approval was applied; lint passed. Dependency remediation is separate work.
- Screen tests use mocked React/native components; installed WebView native handlers were inspected but not exercised on devices. No signed native build/device tests or final packaged native config inspection. HTTPS subresource/CSP restrictions are outside this navigation policy.

## 2026-09-24 — V2/profile-image checkpoint

- `.venv-host/bin/python -m pytest -q`: 69 passed, 251 deprecation warnings in 11.65s, including 13 profile-image tests.
- `node tests/csrf_frontend.cjs`: passed CSRF, multipart, identity, concurrency and logout regressions; parses all inline script blocks with vm.Script.
- Backend AST syntax check and `git diff --check`: passed.
- Tests use isolated database/image storage. No manual desktop/phone verification performed in this session.

## 2026-09-24 — T-005 debug/demo deployment configuration

| Check | Result | Evidence / scope |
| --- | --- | --- |
| Backend syntax | PASS | `python -m py_compile forge_backend.py` completed without error. |
| Focused configuration + CSRF suite | PASS | `pytest -q tests/test_configuration.py tests/test_csrf_security.py`: **73 passed, 288 warnings in 9.65s**. |
| Full isolated Forge suite | PASS | `pytest -q`: **93 passed, 377 warnings in 10.60s**. |
| Frontend regressions | PASS | `node tests/csrf_frontend.cjs`: CSRF helper, multipart, identity, concurrency, and logout regressions passed. |
| Whitespace validation | PASS | `git diff --check` completed without output. |
| Debug defaults | PASS | Debug and demo mode default off. Explicit local development can enable them; ambiguous boolean values are rejected. |
| Deployment environment validation | PASS | Unknown/misspelled `FORGE_ENV` values fail closed. Staging/production/prod require deployment-grade secrets and Secure cookies. |
| Demo isolation | PASS | Flask debug alone cannot enable demo login. Demo endpoint, CLI seeding, and automatic startup demo seeding require explicit local demo mode. |
| Placeholder secret | PASS | `.env.example` placeholder `change-me-to-something-random` is rejected for staging/production deployment configuration. |
| Scope preservation | PASS | Intended T-005 files only plus agent records; unrelated `sandbox/Dockerfile` remains modified but excluded. |

Warnings are existing `datetime.utcnow()` deprecations and SQLAlchemy `Query.get()` legacy warnings exercised by the wider suite; T-005 does not attempt their cleanup.

Limits: these checks validate application configuration and import behavior, not a real reverse-proxy or production-host deployment. Binding policy, TLS termination, signed mobile release-device verification, operational secret provisioning, and remaining non-P0 security concerns require separate verification.

## 2026-09-24 — T-101 authentication/authorization regression baseline

| Check | Result | Evidence / scope |
| --- | --- | --- |
| Dedicated T-101 suite | PASS | `pytest -q tests/test_authz_regressions.py`: **25 passed, 133 warnings in 5.94s**. |
| Registration/login | PASS | Self-register roles, admin exclusion, student-domain enforcement, duplicate username handling, failed/suspended login rejection, successful identity/session establishment. |
| Role gates | PASS | Student/business/admin separation, unapproved business listing denial, alumni-verification role restriction. |
| Notification ownership | PASS | Caller-only listing, cross-user read rejection, read-all constrained to caller. |
| Profile visibility | PASS | Hidden profiles unavailable to ordinary users, available to owner/admin; visible-profile views recorded with correct viewer/target identity. |
| Approval actions | PASS | Non-admin business approval rejected; admin business approval, listing approval/live opportunity creation, and alumni verification approval verified. |
| Full Forge suite | PASS | `pytest -q`: **118 passed, 510 warnings in 15.04s**. |
| Frontend regression suite | PASS | CSRF helper, multipart, identity, concurrency, and logout regressions passed. |
| Syntax / whitespace | PASS | `python -m py_compile forge_backend.py` and `git diff --check`. |

| Production behavior | UNCHANGED | T-101 adds regression coverage only; no application source modified. |

Initial T-101 execution had 3 test failures because the new fixture used `Notification.kind`; inspection confirmed the real model field is `Notification.type`. The test fixture was corrected without changing production behavior.

Warnings remain existing `datetime.utcnow()` deprecations and SQLAlchemy `Query.get()` legacy warnings.

## 2026-09-24 — Autonomous runtime MVP

| Check | Result | Evidence |
| --- | --- | --- |
| Focused runtime unit tests | PASS | `.venv/bin/python -m pytest -q tests/test_agent_runtime.py`: **11 passed**; tests use injected subprocess runners and never invoke Codex. |
| Runtime syntax | PASS | `.venv/bin/python -m py_compile agent_runtime/__init__.py agent_runtime/runtime.py scripts/forge-auto`. |
| Whitespace | PASS | `git diff --check`. |

## 2026-09-24 — T-102 upload boundary hardening

| Check | Result | Evidence / scope |
| --- | --- | --- |
| Dedicated upload-security suite | PASS | `.venv-host/bin/python -m pytest -q tests/test_upload_security.py`: **10 passed, 58 warnings in 3.93s**. |
| Request-size handling | PASS | Multipart Content-Length preflight plus bounded streamed writes reject oversized uploads and clean partial files. |
| Content validation | PASS | Unsupported extensions, invalid signatures, and extension/container mismatches are rejected; supported container families are checked from file bytes. |
| Processing failure behavior | PASS | ffmpeg failures fail closed; when ffmpeg is unavailable, signature-validated originals remain usable with placeholder thumbnails. |
| Upload authorization | PASS | Anonymous access is rejected; active media follows role-feed authorization; admins retain moderation access; orphan and soft-removed media are unavailable. |
| Retention behavior | PASS / DEFERRED | Soft removal immediately revokes access while physical bytes remain. Automated irreversible deletion is deferred pending an approved retention policy. |
| Full Forge suite | PASS | `.venv-host/bin/python -m pytest -q`: **139 passed, 568 warnings in 17.05s**. |
| Syntax / whitespace | PASS | `.venv-host/bin/python -m py_compile forge_backend.py` and `git diff --check`. |

Limits: content inspection is container-signature-level validation, not malware scanning or deep codec/media validation. The global Flask request-size ceiling currently applies application-wide. Physical cleanup of removed media remains intentionally deferred.

## 2026-09-24 — T-103 password-reset token hardening

| Check | Result | Evidence / scope |
| --- | --- | --- |
| Reset and CSRF regressions | PASS | `.venv/bin/python -m pytest -q tests/test_password_reset_security.py tests/test_csrf_security.py`: **44 passed, 56 warnings in 7.83s**. |
| Token secrecy | PASS | New reset tokens are persisted only as SHA-256 digests, can be redeemed once, and are cleared after redemption. |
| Non-debug delivery/logging | PASS | Non-debug responses omit development tokens; unconfigured SMTP emits no recipient, subject, body, or token content. |
| Full Forge suite | PASS | `.venv/bin/python -m pytest -q`: **144 passed, 162 warnings in 22.39s**. |

## 2026-09-24 11:07 UTC — T-105 autonomous verification

- Reviewer: PASS
- Deterministic checks: git diff --check => 0; /home/pablo/Documents/Programming/04-Projects/forge/.venv-host/bin/python -m py_compile forge_backend.py tests/test_authz_regressions.py => 0; /home/pablo/Documents/Programming/04-Projects/forge/.venv-host/bin/python -m pytest -q => 0
- Run artifacts: `.forge-agent/runs/20260924T110515Z-T-105`

## 2026-09-24 14:11 UTC — T-106 autonomous verification

- Reviewer: PASS
- Deterministic checks: git diff --check => 0; /home/pablo/Documents/Programming/04-Projects/forge/.venv-host/bin/python -m py_compile forge_backend.py tests/test_authz_regressions.py => 0; /home/pablo/Documents/Programming/04-Projects/forge/.venv-host/bin/python -m pytest -q => 0
- Run artifacts: `.forge-agent/runs/20260924T140842Z-T-106`

## 2026-09-24 14:44 UTC — T-202 autonomous verification

- Reviewer: PASS
- Deterministic checks: git diff --check => 0; /home/pablo/Documents/Programming/04-Projects/forge/.venv-host/bin/python -m py_compile tests/test_api_contract.py => 0; /home/pablo/Documents/Programming/04-Projects/forge/.venv-host/bin/python -m pytest -q => 0
- Run artifacts: `.forge-agent/runs/20260924T141111Z-T-202`

## 2026-09-24 — T-203 / Issue #1 pre-extraction baseline

- Starting commit: `e03c0a3` on the existing `codex/t-203-backend-extraction` branch.
- Added 30 cases in `tests/test_account_routes.py` before moving production code: anonymous/suspended access for all six notification/onboarding routes, global CSRF rejection on all four mutations, role-specific onboarding progress/clamping/fallback and skip persistence, notification ordering/50-row window versus total unread count, repeated marking, missing-resource HTML 404, route methods, and direct-script startup without a second app import.
- `.venv/bin/python -m pytest -q`: **206 passed, 965 existing deprecation/legacy warnings in 17.10s**, no skips. This includes the unchanged security, API, upload, profile, Socket.IO, frontend Node, and agent-runtime regressions.
- Tests run against the original handlers, with isolated SQLite/storage from the existing harness. No application source changed in this baseline commit.

## 2026-09-24 — T-203 / Issue #1 extraction verification

- Focused route/API/authorization suite: `.venv/bin/python -m pytest -q tests/test_account_routes.py tests/test_api_contract.py tests/test_authz_regressions.py` — **64 passed, 522 warnings in 5.77s**.
- Full Forge suite after extraction: `.venv/bin/python -m pytest -q` — **206 passed, 965 warnings in 16.03s**, no skips. Warning count matches the pre-extraction run; existing datetime/SQLAlchemy deprecations remain out of scope.
- Compared runtime URL rules with starting commit `e03c0a3`: all **66 rules** (including Flask static) preserve paths, methods, subdomains, and strict-slash behavior. Compared SQLAlchemy table/column metadata: all **23 tables** match. No production database was opened; the comparison used in-memory database configuration.
- AST comparison: all **129 original class/function definitions** match after normalizing only `blueprint`/`app`, `notification_model`/`Notification`, and `steps_by_role`/`ONBOARDING_STEPS` identifiers in the six moved handlers.
- `git diff --check` passes. Source review confirms only the six handlers' location/registration changed; global security hooks and remaining handlers/models are unchanged. No dependency, web, mobile, or sandbox changes.
- Limits: automated Flask/Node and direct-script startup checks; no manual browser, mobile-device, or deployment testing. Broader T-203 extraction remains in the backlog.

## 2026-09-24 — T-203 / Issue #3 profile baseline before extraction

- Starting commit: `5dafe2a` on `codex/t-203-profile-extraction`, including merged notification/onboarding PR #2.
- Added 50 cases in `tests/test_profile_routes.py` against the original handlers: authentication/suspension, CSRF/origin rejection, all-role CV keyword/substring/merge behavior, empty/malformed JSON, student-only skill edits, role-specific portfolio allowlists and clearing, session identity, completion recalculation, visibility truthiness/partial updates, and caller-only export contents/order/full history/download headers.
- Extended the existing direct-script startup regression to require the five profile routes exactly once without a second entrypoint import.
- Focused baseline: `.venv/bin/python -m pytest -q tests/test_profile_routes.py` — **50 passed, 311 warnings in 1.64s**.
- Full baseline: `.venv/bin/python -m pytest -q` — **256 passed, 1276 warnings in 44.68s**, no skips. Existing datetime/SQLAlchemy deprecations remain out of scope.
- `git diff --check` passed. Only tests and this evidence record changed; production handlers remain untouched in this commit. Existing harness isolates SQLite and image/upload storage.

## 2026-09-24 — T-203 / Issue #3 extraction verification

- Full Forge suite after extraction: `.venv/bin/python -m pytest -q` — **256 passed, 1276 warnings in 44.47s**, no skips. Count and existing datetime/SQLAlchemy warnings match the pre-extraction baseline. Includes image/upload authorization, public-profile visibility, API, CSRF/session, Socket.IO, frontend Node, and agent-runtime regressions.
- Direct-script startup test confirms all five profile routes register exactly once and `forge_backend` is not imported again when executed as `__main__`.
- Compared all **123 original top-level class/function definitions** to `5dafe2a`: identical ASTs after normalizing only the five moved handlers' blueprint/dependency names and docstring indentation. Initial raw comparison detected only the moved multiline docstring indentation; normalized comparison passed.
- Runtime snapshots preserve all **66 URL rules** (paths, methods, subdomains, strict-slash behavior) and **23 tables** (column types, nullability, primary keys, foreign keys). Snapshot imports used an in-memory database; tests use the existing isolated harness, never the application database.
- `git diff --check` passes. Production diff is restricted to importing/registering the new blueprint and moving the five handlers. Models, shared helpers, image storage/serving, global security hooks, and clients remain unchanged.
- Limits: automated Flask/Node and script-startup verification; no manual browser/mobile-device/deployment testing. Optional image extraction and broader T-203 remain deferred.

## 2026-09-24 — Issue #6 web profile export

- `.venv/bin/python -m pytest -q tests/test_profile_export_frontend.py tests/test_web_quality.py tests/test_csrf_frontend.py tests/test_security_headers.py`: **17 passed in 1.06s**.
- `.venv/bin/python -m pytest -q`: **257 passed, 1276 existing datetime/SQLAlchemy warnings in 48.03s**, no skips.
- Node executes the actual static API/profile functions: exactly one semantic export button for trade/grad/business/admin; same-origin GET with no-store; exact response bytes, server filename and fallback; busy/re-render/concurrent-click protection; 500/401/403/network failure and successful retry; object URL cleanup; no stale-account download. Existing script syntax, CSRF, CSP, responsive and keyboard assertions remain green.
- `git diff --check` passes. Production changes are web-only; backend and mobile files are unchanged. No dependencies added.
- Limits: mocked DOM/download behavior plus Flask/Node regressions; no manual browser, screen-reader, mobile-device, or deployment testing.

## 2026-09-26 — T-203 / Issue #5 analytics baseline before extraction

- Branch base: `2193553` (`master`, including merged profile PR #4 and web export PR #7).
- Added 28 cases in `tests/test_analytics_routes.py` before moving production code: anonymous/missing/suspended sessions; every role/dashboard combination; exact empty response shapes; caller scope; 14-day series versus all-time totals; shared connection counts; display-name post attribution; peer filtering/truncation; case-sensitive search aggregation/top-five/tie order; application-row and repeated-skill counting; pipeline order; unspecified demographics; zero/rounded/over-100% rates; cumulative student-board impressions; exact trailing-30-day MAU inclusion; pending approval composition; registration/content counts.
- Extended direct-script startup coverage to require all three analytics routes exactly once without a second entrypoint import.
- `.venv/bin/python -m pytest -q`: **285 passed, 1394 existing SQLAlchemy legacy warnings in 16.35s**, no skips. Existing T-106 owner/admin scope regression remains unchanged and passing. Isolated SQLite/storage harness only.
- Captured runtime baseline: **66 URL rules**, **23 tables**, including SQLite DDL constraints/defaults and indexes, with an in-memory database. `git diff --check` passed. No production source changed in this baseline commit.

## 2026-09-26 — T-203 / Issue #5 extraction verification

- `.venv/bin/python -m pytest -q`: **285 passed, 1394 existing SQLAlchemy legacy warnings in 15.83s**, no skips; test/warning counts match the pre-extraction baseline. Includes the unchanged T-106 owner/admin regression, new analytics semantics, direct-script startup, API/auth/CSRF, media, Socket.IO, frontend Node, and runtime coverage.
- Runtime snapshots taken before/after extraction with `FORGE_DATABASE_URI=sqlite://` match exactly: **66 URL rules** (paths, methods, subdomains, strict slashes) and **23 tables** (SQLite DDL, constraints/defaults, and indexes). No production database opened.
- AST comparison against `2193553`: all **118 original top-level class/function definitions** match, including the three moved handlers, normalizing only `blueprint`/`app` and injected model parameter names. The remaining monolith definitions are unchanged.
- `git diff --check` passes. Production diff contains only the new analytics module and entrypoint import/registration. Internal Flask endpoint names gain `analytics.`; repository search found no old endpoint-name consumers. Direct-script startup registers all three paths exactly once without importing a second entrypoint.
- Limits: automated Flask/Node/startup verification; no manual browser, mobile-device, or deployment testing. No unrelated ownership/schema/retention defects addressed; broader T-203 remains open.

## 2026-09-26 — T-104 / Issue #9 design-only verification

- `.venv/bin/python -m pytest -q`: **285 passed, 1394 warnings in 23.77s**, no skips. Existing SQLAlchemy legacy/datetime deprecation warnings; no executable tests or runtime files changed. The initially absent local virtual environment was created from the repository's unchanged `requirements.txt` before running the suite.
- `git diff --check` passes. Scope verification against `d4a0516` confirms all changed/added tracked paths are `agent/*.md`; production source, clients, model definitions, route contracts, dependencies, tests and database files are unchanged.
- Source review traces all seven social routes, their model/seed/socket/notification effects, shared network analytics and web/native/WebView consumers. The design explicitly covers all eight Issue #9 deliverables and separates verified behavior from proposed D-012–D-015.
- Tests use the existing isolated SQLite/storage harness; no application database was opened for design analysis and no production migration was created or run. The proposed SQL is documentation only.
- Limits: this validates the unchanged runtime baseline, not the proposed ownership model. Three-user isolation, migration/restore, independent-connection races, new API/client behavior, post-commit recipient delivery and release-device checks remain required in later approved implementation. T-104 remains pending architecture review; no merge.

## 2026-09-28 — design approval and blocking/reporting gate

- Full `.venv/bin/python -m pytest -q`: **285 passed, 1394 existing deprecation warnings in 17.05s**. No new executable tests; this is a documentation-only approval/backlog update.
- `git diff --check` passed. All changed paths are `agent/*.md`; production code, schema, database files, dependencies and web/mobile behavior are unchanged. Removed only the temporary profile-image fixture directory generated by this test run.
- Reviewed accepted D-012–D-015, new D-016, completed design-only T-104, remaining T-201 gates and open T-107 for consistency. Historical pending-approval records are explicitly superseded by the dated approval update.
- Blocking/reporting, ownership enforcement and their future race/privacy/migration/client tests remain unimplemented; the passing existing suite is not evidence of social production readiness.

## 2026-09-28 — T-201 migration tooling foundation

- `tests/test_migration_tooling.py`: **5 passed**.
- Full Forge suite: **290 passed, 1394 existing warnings**, no failures.
- Frozen baseline contains **23 existing application tables**.
- Baseline adoption is explicit, checksum-validated and idempotent.
- Schema drift is rejected before the migration ledger is created.
- Verification runs SQLite `integrity_check` and `foreign_key_check` without changing `PRAGMA foreign_keys`.
- SQLite backup uses the backup API, verifies integrity, and refuses overwrite.
- Missing-database `db-status` is read-only and does not create a SQLite file.
- `git diff --check` passes.
- No persistent application database was baselined or migrated during validation.

## 2026-09-28 — T-201 owned-social ordered revision

- Focused migration suite: **13 passed**.
- Full Forge suite: **298 passed, 1394 existing warnings**, no failures.
- `git diff --check` passed.
- Frozen `migrations/baseline_schema.json` remained unchanged.
- Revision-02 manifest contains **29 application tables**: frozen 23 plus six
  owned-social tables.
- Injected baseline failure rolls back migration-ledger DDL completely.
- Injected upgrade failure rolls back partial schema DDL and leaves the
  baseline revision intact.
- Injected downgrade failure restores the revision-02 schema and ledger.
- Physical constraint tests verify endpoint-only membership, member-only
  message authorship, 4,000-character message bound, ownership-event
  single-target rule and message client-retry uniqueness.
- Copy rehearsal created a consistent backup without changing source hash,
  mtime or size.
- Copy baseline and revision-02 upgrade passed checksum, schema,
  `integrity_check` and `foreign_key_check`.
- Upgraded copy contained 29 application tables, all six owned tables, both
  membership triggers and all five quarantined legacy social tables.
- Empty downgrade restored exactly the frozen 23-table baseline.
- Re-upgrade succeeded.
- A controlled `network_edge` row caused downgrade to refuse safely while
  preserving the revision-02 ledger/schema.
- After removing controlled owned data, downgrade and final re-upgrade both
  succeeded.
- Final verification showed the real `instance/forge.db` byte/stat-identical,
  without a migration ledger and without any owned-social tables.
- Global FK enforcement remains unchanged/off by default; no production/local
  persistent rollout occurred.

## 2026-09-28 — Issue #16 migration-managed bootstrap

- Focused: `.venv/bin/python -m pytest -q tests/test_database_bootstrap.py tests/test_migration_tooling.py --basetemp=.git/pytest-issue16-reviewed-focused` — **46 passed in 43.37s**.
- Full backend/web suite: `.venv/bin/python -m pytest -q --basetemp=.git/pytest-issue16-reviewed-full` — **331 passed, 1394 existing deprecation warnings in 73.47s**, no skips. Adds 33 bootstrap cases to the 298-test master baseline.
- Fresh file/memory bootstrap reaches HEAD with both ledger rows, six owned tables, endpoint insert/update triggers, pair/retry uniqueness, message bound and author FK. ORM create_all methods are patched to fail in independence tests. Existing migration tests now create baseline fixtures from the frozen manifest, not application metadata.
- Current HEAD succeeds without persistent DB mutation in development/test/staging/production, including databases initialized through explicit baseline+upgrade. Refused states cover unmanaged/behind-head, column drift, checksums, missing/replaced trigger body, revised message CHECK, added baseline CHECK, extra view and ledger-column tampering. File hash/mtime/size and sidecar comparisons prove refusal non-mutation; WAL test detects an uncheckpointed tampered ledger and preserves database/WAL bytes (shared-memory read locks excluded).
- Actual subprocess import/WSGI readiness, direct-script and Flask-run refusal, CLI confirmation/new-file refusal, explicit baseline/upgrade recovery, demo gating/initialization order and deployment memory rejection are covered. RuntimeError, KeyboardInterrupt, SystemExit and SIGKILL injection leave no committed partial schema or ledger; SQLite recovery occurs only on the test-owned crash file.
- AST comparison with `dac4ef8`: every existing model class and HTTP/socket handler is unchanged; only the pragma registration and seed CLI readiness differ among pre-existing definitions. `git diff --check` passes. All files under `migrations/`, including baseline JSON and revision-02 source/manifest/checksum inputs, are byte-identical to master.
- No real `instance/forge.db` was opened, baselined, upgraded, seeded or used in tests. Tests use newly allocated workspace-local fixture files, pytest temporary databases or in-memory SQLite. No live-database hash probe or copy rehearsal was needed. Removed only test-owned temporary directories generated during validation.
- Root/mobile README startup guidance changed; no static/mobile code changed, so separate mobile lint/device checks were not run. No global FK enablement, social ORM/API/client work or production rollout. T-201 and T-107 remain open.
## 2026-09-28 — Issue #19 real browser web quality

- Playwright 1.55.0 / Chromium 140.0.7339.16: **8 browser cases passed**, exercising the 13 Issue #19 acceptance areas across role parameters, desktop/mobile viewports and reduced motion. Optional third-party CDN requests were blocked; Forge CSP and same-origin API requests remained unchanged.
- Focused browser plus existing web/security checks: **23 passed**.
- Full Python suite with browser dependency installed: **343 passed**, 1394 existing deprecation warnings, in 78.56s. `git diff --check` passed.
- The browser server used only a fresh, migration-managed temporary test database and isolated upload directories. No real `instance/forge.db` access. No Issue #18 social ORM/service or migration history change; no static-client defect was reproduced in this scope, so no client change was made.

## 2026-09-29 — Issue #22 ownership-v2 HTTP gate

- Dedicated process-mode regressions use migration-managed disposable databases: v2 route/auth/CSRF/capability ordering, same-direction request retry, endpoint authorization, desired-state endorsement retry and directional projection, conversation create/reuse, member-only paging/read/send, signed cursor tamper/cross-user/wrong-scope, SQL trace against all nine operations, and no delivery; independent legacy and maintenance process checks verify graph exclusivity. The v2 subprocess runs its own six integration cases; the outer suite reports three mode/configuration checks.
- Focused owned-social models/service/HTTP plus migration/bootstrap: `.venv/bin/pytest -q --disable-warnings tests/test_owned_social_models.py tests/test_owned_social_service.py tests/test_owned_social_http_subprocess.py tests/test_migration_tooling.py tests/test_database_bootstrap.py` — **77 passed, 92 warnings in 33.56s**.
- The full backend/web suite includes real Chromium coverage using the existing Playwright test dependency. Final counts are recorded below. All databases were isolated and migration-initialized; no real `instance/forge.db` was opened. Migration history, static web/WebView, sockets, notifications and analytics were not changed. T-107 remains unimplemented and production readiness is not claimed.
- Final full suite: `.venv/bin/pytest -q --disable-warnings` — **370 passed, 1486 warnings in 70.80s**, no skips. `git diff --check` passed. This is route-only API rehearsal, not client/delivery/analytics/T-107 completion.

## 2026-09-29 — T-201 ownership-v2 static web/WebView client

Starting master: `dcea0d9a4dc1570f40c2a0f903411c547e62274c` (merged PR #23). Branch: `codex/ownership-v2-web-client`. Commands below run from the repository root unless marked mobile. The old checkout's venv interpreter was unavailable; an isolated `.git/client-venv` was installed from the unchanged `requirements.txt` and `requirements-browser.txt`. Chromium 140 / Playwright 1.55 was installed under `.git/playwright`.

| Exact command | Result |
| --- | --- |
| `node --test tests/owned_social_frontend.cjs` | **42 passed, 0 failed, 0 skipped**. Actual source functions: explicit config/capability/CSRF, incoming/outgoing actions and version bodies, desired endorsement state, 409 refresh/no replay, independent cursor/dedup behavior, bounded list/history, create 200/201, observed reads, read-only UI, retry-key preservation/new-key/double-submit/conflict, account/session/CSRF invalidation and late reads/writes. |
| `.git/client-venv/bin/python -m pytest -q tests/test_owned_social_frontend.py tests/test_csrf_frontend.py tests/test_profile_export_frontend.py tests/test_web_quality.py --basetemp=.git/pytest-client-focused-final` | **14 passed in 1.18s**; includes the 42-case Node runner and existing frontend regressions. |
| `PLAYWRIGHT_BROWSERS_PATH=.git/playwright .git/client-venv/bin/python -m pytest -q tests/test_browser_owned_social.py tests/test_browser_web_quality.py --basetemp=.git/pytest-client-browser` | **12 passed in 13.87s**. Four new owned-flow cases plus eight existing browser cases. Final full-suite run below also includes the additional real creation-201 assertion. |
| `.git/client-venv/bin/python -m pytest -q --disable-warnings tests/test_owned_social_models.py tests/test_owned_social_service.py tests/test_owned_social_http_subprocess.py tests/test_migration_tooling.py tests/test_database_bootstrap.py --basetemp=.git/pytest-client-backend` | **77 passed, 92 warnings in 34.01s**. Subprocess checks also verify public no-store configuration in legacy/maintenance/v2 and captured-mode immutability. |
| `.git/client-venv/bin/python -m pytest -q --disable-warnings tests/test_authz_regressions.py tests/test_csrf_security.py tests/test_security_headers.py tests/test_socket_security.py --basetemp=.git/pytest-client-security` | **78 passed, 373 warnings in 13.29s**. |
| `PLAYWRIGHT_BROWSERS_PATH=.git/playwright .git/client-venv/bin/python -m pytest -q --disable-warnings --basetemp=.git/pytest-client-full` | Intermediate full suite: **375 passed, 1486 existing deprecation warnings in 80.02s**, no skips. |
| `npm test` (cwd `mobile`) | **53 passed, 0 failed, 0 skipped**. |
| `npm run lint` (cwd `mobile`) | Passed, exit 0. |
| `npx tsc --noEmit` (cwd `mobile`) | Passed, exit 0. |
| `.git/client-venv/bin/python -m py_compile forge_routes/owned_social_http.py tests/test_owned_social_frontend.py tests/test_browser_owned_social.py tests/_mode_contract.py tests/_v2_contract.py` | Passed. |
| `node tests/csrf_frontend.cjs` and `node tests/profile_export_frontend.cjs` | Passed; the former also syntax-compiles all inline scripts. |
| `git diff --check` | Passed. |

Initial browser invocation preceded completion of browser installation and had 12 executable-not-found setup errors. With Chromium installed, new test assertions initially had two failures, then one, because they waited for a busy button's old name to disappear rather than the completed data update; one state poll also conflicted with CSP. Corrected tests observe completed rows/messages and the actual read response, without relaxing CSP or existing tests. The browser suite then passed all 12 cases.

Real browser evidence includes versioned request actions, suggested paging, desired endorsements, server-created/reused threads, 55-message bounded history and older paging, a single real send with no synthetic reply, visible read POST, disconnection/read-only retained history, keyboard operation, 390px layout and generic 426 handling. Node mocks additionally exercise all required error codes and deliberately late asynchronous results. These tests do not replace signed-device WebView/native session checks.

Only disposable migration-managed databases in test-owned directories or in-memory fixtures were used. The real `instance/forge.db` was never opened, hashed, copied, upgraded or modified. No migration history, native source, default mode or production database was changed. Production v2 is not enabled; sockets/notifications, analytics, persistent rollout/FK/admin-removal review, T-107 and native social remain deferred.

Final frozen-source verification: `PLAYWRIGHT_BROWSERS_PATH=.git/playwright .git/client-venv/bin/python -m pytest -q --disable-warnings --basetemp=.git/pytest-client-final` — **375 passed, 1486 existing deprecation warnings in 80.81s**, **0 failed / 0 skipped**. This includes all 12 Chromium cases with real new-conversation 201 and reused-thread behavior, and the final 42-case Node runner. Final `git diff --check` passed.

## 2026-09-29 — PR #24 contiguous observed-read correction

Starting PR head: `8006aa01f65d307a068555eed16009eb7087440f`; existing branch `codex/ownership-v2-web-client`. The expanded pre-fix Node run reproduced **5 failures / 43 passes**: skipping incoming gaps, own-message gap ordering, unloaded history, hidden-tab advancement and repeated failed-read submission. Tests were corrected to assert the approved contiguous contract; none were removed or weakened. The existing observer test uses a confirmed cursor of 2 when observing sequence 3; the real-server browser test now explicitly rejects read writes while sequences 1–5 are unloaded.

The client retains a per-thread observed-sequence Set across history pagination/refresh. Starting at the latest confirmed `lastReadSequence`, it advances only across loaded own messages or observed incoming messages, stopping at every unknown or unobserved incoming sequence. It never uses `lastSequence` as observation evidence. One in-flight read and a submitted-cursor high-water mark prevent duplicate/lower posts; later contiguous observations drain after completion using current thread state. Hidden-tab and account-generation guards remain active; retained read-only histories may advance their own cursor.

Commands below were run from the repository root unless marked mobile. Python dependencies came from unchanged requirements files in a fresh local `.venv`; browser tests used Playwright 1.55 / Chromium 140. All database fixtures were disposable and migration-managed.

| Exact validation command | Final result |
| --- | --- |
| `node --test tests/owned_social_frontend.cjs` | **49 passed, 0 failed, 0 skipped**. Incoming gaps, own-message gaps, unloaded pages then merge, hidden tab and in-flight drain, monotonic concurrency, failed-post deduplication, read-only history, stale observer/account and late read response. |
| `.venv/bin/python -m pytest -q tests/test_owned_social_frontend.py tests/test_csrf_frontend.py tests/test_profile_export_frontend.py tests/test_web_quality.py` | **14 passed in 1.27s**. |
| `.venv/bin/python -m pytest -q tests/test_browser_owned_social.py tests/test_browser_web_quality.py` | **13 passed in 15.24s**. Real observer sees only sequence 3 first (no POST), then 1 (POST 1), then 2 (POST 3 using remembered observation of 3), with no duplicate after revisiting 3. Existing browser coverage remains. |
| `.venv/bin/python -m pytest -q --disable-warnings tests/test_owned_social_models.py tests/test_owned_social_service.py tests/test_owned_social_http_subprocess.py tests/test_migration_tooling.py tests/test_database_bootstrap.py` | **77 passed, 92 warnings in 35.89s**. |
| `.venv/bin/python -m pytest -q --disable-warnings tests/test_authz_regressions.py tests/test_csrf_security.py tests/test_security_headers.py tests/test_socket_security.py` | **78 passed, 373 warnings in 12.77s**. |
| `.venv/bin/python -m pytest -q --disable-warnings` | **376 passed, 1486 existing warnings in 80.85s; 0 failed / 0 skipped**. |
| `npm test` (mobile) | **53 passed, 0 failed, 0 skipped**. |
| `npm run lint` (mobile) | Passed, exit 0. |
| `npx tsc --noEmit` (mobile) | Passed, exit 0. |
| `node --check tests/owned_social_frontend.cjs` | Passed. |
| `node tests/csrf_frontend.cjs` | Passed, including compilation of all inline client scripts. |
| `node tests/profile_export_frontend.cjs` | Passed. |
| `.venv/bin/python -m py_compile tests/test_browser_owned_social.py tests/test_owned_social_frontend.py` | Passed. |
| `git diff --check` | Passed. |

The new Chromium fixture initially had one failure because flex layout prevented the intended scroll viewport, then because four pixels of message 2 intersected due to thread padding. Test-only fixed sizing and zero padding establish the asserted visibility; no product CSS, browser assertions, CSP or existing tests were weakened. Backend/service/API semantics, migrations and native source remain unchanged. The real `instance/forge.db` was never opened, copied, inspected or modified. Production v2 remains disabled/default legacy; delivery, analytics, T-107 and all other release gates remain deferred. This fixes existing PR #24 without merging it.

## 2026-10-09 — Issue #28 participant-safe owned-social delivery

Starting clean fetched/pulled master: `876819abd0505b1964c21aa2a68e12ccf676ab27` (merged PR #27). Branch `codex/t201-social-delivery`; dedicated Issue #28. Python 3.14 dependencies are from unchanged `requirements.txt` / `requirements-browser.txt` in project-local `.venv-delivery`. Playwright 1.55 / Chromium 140 uses its Ubuntu 24.04 fallback build on this host, stored under ignored `.playwright-delivery`.

| Actual validation command (repository root unless stated) | Result |
| --- | --- |
| `.venv-delivery/bin/python -m pytest -q --disable-warnings tests/test_owned_social_models.py tests/test_owned_social_service.py tests/test_owned_social_delivery.py tests/test_blocking_core_service.py tests/test_blocking_core_migration.py tests/test_owned_social_http_subprocess.py tests/test_authz_regressions.py tests/test_csrf_security.py tests/test_socket_security.py tests/test_migration_tooling.py tests/test_database_bootstrap.py tests/test_owned_social_frontend.py tests/test_csrf_frontend.py` | **185 passed, 585 warnings in 106.45s**. Broad focused service/blocking, auth/CSRF/socket/notification ownership, model/migration/bootstrap and frontend gates. This run preceded seven further delivery regressions; those pass in the final focused/full runs below. |
| `.venv-delivery/bin/python -m pytest -q --disable-warnings tests/test_owned_social_delivery.py` | **24 passed, 96 warnings in 7.34s** after race/suppression coverage expansion. |
| `FORGE_SOCIAL_MODE=v2 .venv-delivery/bin/python -m pytest -q --disable-warnings tests/_v2_delivery.py tests/_v2_contract.py tests/test_owned_social_delivery.py` | **45 passed, 666 warnings in 10.93s**: 21 real HTTP/socket contracts and 24 service-delivery cases. |
| `TMPDIR=/home/pablo/Documents/Programming/04-Projects/forge/test-results/runtime-tmp FORGE_SOCIAL_MODE=v2 .venv-delivery/bin/python -m pytest -q --disable-warnings --basetemp=test-results/pytest-delivery-v2 tests/_v2_delivery.py tests/_v2_contract.py tests/test_owned_social_delivery.py tests/test_owned_social_service.py tests/test_blocking_core_service.py` | **80 passed, 807 warnings in 30.78s**. Final owned service, blocking and v2 HTTP/socket/notification gate; 22 existing owned service, 13 blocking, 24 new delivery and 21 v2 contract cases. |
| `node tests/owned_social_frontend.cjs` | **63 passed, 0 failed / skipped**. Includes 11 added minimal-invalidation, error/no-replay, stale socket generation, late-refresh, generic notification and legacy compatibility cases. |
| `PLAYWRIGHT_BROWSERS_PATH=.playwright-delivery PLAYWRIGHT_HOST_PLATFORM_OVERRIDE=ubuntu24.04-x64 .venv-delivery/bin/python -m pytest -q --disable-warnings tests/test_browser_owned_social.py tests/test_browser_web_quality.py` | **14 passed in 36.53s**, no skips: six owned-social and eight existing quality cases. Actual Chromium, disposable migrated server, keyboard/mobile 390px, authorized no-store capability refresh, packet-text rejection and retired-account handlers. The added browser case stubs the offline CDN transport; independent Socket.IO clients/sessions are exercised by `_v2_delivery.py`. |
| `PLAYWRIGHT_BROWSERS_PATH=.playwright-delivery PLAYWRIGHT_HOST_PLATFORM_OVERRIDE=ubuntu24.04-x64 .venv-delivery/bin/python -m pytest -q --disable-warnings` | **416 passed, 1634 existing deprecation warnings in 196.71s; 0 failed / skipped**. Includes browser, all backend/web checks, Node wrappers and legacy/maintenance/v2 subprocess contracts. The v2 subprocess separately runs 21 contract/socket cases. |
| `npm --prefix mobile test` | **53 passed, 0 failed / skipped**. PR #26 was not applied. |
| `npm --prefix mobile run lint` | PASS, exit 0. |
| `./node_modules/.bin/tsc --noEmit` (cwd `mobile`) | PASS, exit 0. |
| `.venv-delivery/bin/python -m py_compile forge_backend.py forge_routes/owned_social.py forge_routes/owned_social_http.py forge_routes/notifications.py forge_routes/profile.py tests/test_owned_social_delivery.py tests/_v2_delivery.py tests/test_owned_social_http_subprocess.py tests/test_owned_social_service.py tests/test_browser_owned_social.py` | PASS. |
| `node tests/csrf_frontend.cjs` and `node tests/profile_export_frontend.cjs` | PASS; CSRF harness compiles all inline scripts. |
| `git diff --check` | PASS. |

Added failure evidence: request/accept/send notification-insert and commit failures leave domain, ownership audit and Notification rows identical to the pre-operation snapshot, with no packet. Service and HTTP emission failures preserve committed results/notifications and recover through authorized HTTP; same-key retries add no packet or row. Logs contain no injected exception/message/identity/block content. Independent connections cover block holding the write reservation before request/accept/send, commit-before-block suppression, block/suspension/deletion/corrupt-membership eligibility change before enqueue, final enqueue reservation versus block, concurrent identical send, block-suppression rollback and unblock/reconnect non-restoration. Retained member history/own read are preserved; no actor/direction/reason appears in contact delivery.

The first executable focused run had **50 passed / 2 failed**: the established service assertion expected deferred zero notifications, and a new corrupt-membership fixture incorrectly expected an otherwise valid accepted-edge notification to vanish. The established test now requires the approved three generic durable rows while continuing to forbid legacy emission helpers. The new fixture now distinguishes valid relationship notification authorization from invalid conversation membership; message packets/notifications remain suppressed. No established security assertion was weakened.

Environment-only failures were resolved: old venvs lacked pytest/pip; network sandbox denied package/CDN DNS; Playwright's old platform map required the documented local-source fallback override; sandbox denied localhost sockets and Expo's Node subprocess (`EPERM`). Required Git/network/subprocess/browser actions were rerun with explicit sandbox escalation. No automated test was skipped. Signed-device WebView/native-session checks remain release gates, not claims made by these automated tests.

All database fixtures were disposable and migration-managed. The real `instance/forge.db` was never opened, copied, hashed, seeded, baselined, migrated or modified. No new schema/migration, global FK change, queue/service, native social feature, analytics cutover, production v2 enablement, default-mode change, or PR #26 work. No unresolved schema/policy blocker is required for the implemented conservative unread-hint suppression; historical generic rows remain stored.

## 2026-10-09 — PR #29 client review fixes

Starting PR head: `0e9f1a865373ca5119cdde0aa2ff49f71d9a0cd8`; fetched master remains `876819abd0505b1964c21aa2a68e12ccf676ab27`. Reused the existing isolated review checkout and its installed dependencies. Before repair the independent review reproduced three browser assertion failures (empty draft, no realtime refresh after CSRF recovery, null conversation selection) and one Node failure (maintenance unread count remained zero). These reproductions are now covered by maintained tests in `tests/test_browser_social_delivery.py` and `tests/owned_social_frontend.cjs`.

| Command from repository root unless stated | Result |
| --- | --- |
| `node --test tests/owned_social_frontend.cjs` | **73 passed**, no failures/skips. Ten added cases cover legacy/v2 socket recovery, no mutation replay, retired callbacks, maintenance notification delivery, selected-thread navigation, malformed hints and late account-switch navigation. |
| `PLAYWRIGHT_BROWSERS_PATH=.review-browsers PLAYWRIGHT_HOST_PLATFORM_OVERRIDE=ubuntu24.04-x64 .review-venv/bin/python -m pytest -q --disable-warnings tests/test_browser_social_delivery.py tests/test_browser_owned_social.py tests/test_browser_web_quality.py` | **21 passed in 47.86s**, no failures/skips. Seven added Chromium cases cover in-flight typing and focus/selection at 390px/1280px, automatic CSRF socket recovery, fresh/prior-thread notification selection, draft scoping and unavailable hint lookup; 14 established browser cases still pass. |
| `PLAYWRIGHT_BROWSERS_PATH=.review-browsers PLAYWRIGHT_HOST_PLATFORM_OVERRIDE=ubuntu24.04-x64 .review-venv/bin/python -m pytest -q --disable-warnings` | **423 passed, 1634 existing deprecation warnings in 220.36s; 0 failed / skipped**. Includes all browser tests, backend/web, Node wrappers and isolated legacy/maintenance/v2 HTTP/socket contracts. |
| `npm test && npm run lint && node_modules/.bin/tsc --noEmit` (cwd `mobile`) | **53 tests passed**, no failures/skips; lint and TypeScript passed, combined exit 0. |
| `node tests/csrf_frontend.cjs` and `node tests/profile_export_frontend.cjs` | Passed; inline product scripts compile and existing CSRF/export flows remain covered. |
| `.review-venv/bin/python -m py_compile tests/test_browser_social_delivery.py`, `node --check tests/owned_social_frontend.cjs`, `git diff --check` | Passed. |

No established assertion was weakened. Chromium invokes actual client handlers through the existing offline transport approach with real same-origin, capability-protected HTTP against disposable migrated servers. Real authenticated Socket.IO clients are exercised separately by the v2 subprocess gate; signed-device WebView/session tests remain release gates. All database work was confined to disposable migration-managed fixtures; no real `instance/forge.db`, native source, schema/migration, backend delivery semantics, default mode or PR #26 change. The PR remains unmerged.

## 2026-10-09 — PR #29 multipart CSRF recovery repair

Starting head: `d73b6938a0ab12c8105026da8c36d8b57f07d47e`. The re-review independently reproduced a remaining video-upload recovery failure in Node (legacy/v2) and Chromium: one socket created, one retired, none present after a current upload CSRF rejection. Nine new maintained Node cases initially failed against the original implementation; the existing 73 passed. They now cover recovery without replay, multipart headers/body, retired callbacks, current token/upload 401 expiry, stale success/401/CSRF/error-body responses and an account change during token acquisition. The post-repair Node run initially exposed an uninitialized unread count in the new legacy test fixture; initializing that fixture to zero resolved it without a product-code change or weakening an assertion.

| Command from `review-t201` | Result |
| --- | --- |
| `node tests/owned_social_frontend.cjs` | **82 passed**, no failures/skips. |
| `PLAYWRIGHT_BROWSERS_PATH=.review-browsers PLAYWRIGHT_HOST_PLATFORM_OVERRIDE=ubuntu24.04-x64 .review-venv/bin/python -m pytest -q --disable-warnings tests/test_browser_social_delivery.py tests/test_browser_owned_social.py tests/test_browser_web_quality.py` | **22 passed in 42.70s**, no failures/skips. Added actual video-handler CSRF recovery, one upload attempt, retired-callback rejection and fresh-handler authorized history refresh. |
| `PLAYWRIGHT_BROWSERS_PATH=.review-browsers PLAYWRIGHT_HOST_PLATFORM_OVERRIDE=ubuntu24.04-x64 .review-venv/bin/python -m pytest -q --disable-warnings` | **424 passed**, 1634 existing deprecation warnings in **209.64s**, no failures/skips. Includes all maintained browser/backend/web tests, Node wrappers and isolated legacy/maintenance/v2 HTTP/socket contracts. |
| `node tests/csrf_frontend.cjs`; `node tests/profile_export_frontend.cjs` | Passed; inline scripts compile and existing multipart/CSRF/export flows remain covered. |
| `git diff --check` | Passed. |

Network permission was required for disposable localhost servers. Browser transport uses the established offline Socket.IO stub with real HTTP; authenticated room delivery remains covered by the separate v2 subprocess contract. Mobile source/dependencies are unchanged from the preceding review's 53 passing mobile tests, lint and TypeScript; those unchanged checks were not repeated for this repair. No real `instance/forge.db`, native source, backend delivery, schema/migration, default mode, production v2 or PR #26 change. Temporary untracked review reproducers were replaced with maintained regressions. PR #29 remains unmerged for human review; broader release gates remain open.

## 2026-10-09 — Issue #30 student analytics ownership isolation

Starting clean fetched/pulled master: `3686256c561c36cbc2b7d07864d29d33b7b6999e` (merged PR #29). Branch `codex/t201-student-analytics-isolation`. Existing project-local `.venv-delivery` dependencies and Playwright 1.55/Chromium 140 were reused without dependency changes. All database fixtures are disposable and migration-managed; the real `instance/forge.db` was never accessed, inspected, copied, hashed or modified.

| Validation | Result |
| --- | --- |
| `.venv-delivery/bin/python -m pytest -q --disable-warnings tests/test_analytics_routes.py tests/test_owned_social_analytics.py tests/test_analytics_modes_subprocess.py tests/test_analytics_frontend.py` (final with workspace TMPDIR/basetemp) | **43 passed, 158 existing warnings in 22.91s**: 28 unchanged legacy baseline cases, 10 pure service cases, 4 process/startup gates, one Node wrapper. |
| Broad focused analytics/service/blocking/mode/auth/CSRF/socket/model/migration/bootstrap run (same interpreter; files named below) | **208 passed, 675 warnings in 128.25s**. This preceded adding the actual unknown-mode startup case, which passed in the final focused/full run. |
| `FORGE_SOCIAL_MODE=legacy ... pytest -q --disable-warnings tests/_analytics_contract.py` | **6 passed, 10 warnings in 1.43s**. |
| `FORGE_SOCIAL_MODE=maintenance ... pytest -q --disable-warnings tests/_analytics_contract.py` | **6 passed, 10 warnings in 1.33s**. |
| `FORGE_SOCIAL_MODE=v2 ... pytest -q --disable-warnings tests/_analytics_contract.py` | **16 passed, 28 warnings in 4.23s**. |
| `node tests/analytics_frontend.cjs` | **5 passed, 0 failed/skipped**: stable/zero rendering, optional maintenance and stale responses during HTTP/JSON completion. |
| `node tests/owned_social_frontend.cjs` | **82 passed, 0 failed/skipped**. |
| `node tests/csrf_frontend.cjs`; `node tests/profile_export_frontend.cjs` | Passed, including inline script compilation. |
| Browser-enabled `... pytest -q --disable-warnings tests/test_browser_analytics.py` | **3 passed in 8.84s**, real Chromium with desktop/mobile 390px, keyboard navigation, owned count 1/empty count 0 despite demo rows, optional maintenance profile controls. |
| `TMPDIR=/home/pablo/Documents/Programming/04-Projects/forge/test-results/runtime-tmp PLAYWRIGHT_BROWSERS_PATH=.playwright-delivery PLAYWRIGHT_HOST_PLATFORM_OVERRIDE=ubuntu24.04-x64 .venv-delivery/bin/python -m pytest -q --disable-warnings --basetemp=test-results/pytest-analytics-full` | **442 passed, 1674 existing deprecation warnings in 236.97s; 0 failed/skipped**. Includes all **25 Chromium** cases, Node wrappers and existing v2 HTTP/socket plus new analytics mode subprocesses. |
| `npm --prefix mobile test` | **53 passed, 0 failed/skipped**; rerun, not reused evidence. |
| `npm --prefix mobile run lint`; `./node_modules/.bin/tsc --noEmit` (cwd mobile) | Passed, exit 0. |
| `.venv-delivery/bin/python -m py_compile` on all 3 changed production modules and 5 new Python tests | Passed. |
| `git diff --check`; business/admin handler AST comparison to starting HEAD | Passed; both unrelated handlers exactly unchanged. |

Broad focused files: `test_analytics_routes`, `test_owned_social_analytics`, `test_analytics_modes_subprocess`, `test_analytics_frontend`, `test_owned_social_service`, `test_blocking_core_service`, `test_owned_social_http_subprocess`, `test_authz_regressions`, `test_csrf_security`, `test_socket_security`, `test_owned_social_models`, `test_database_bootstrap`, `test_migration_tooling`, `test_blocking_core_migration` (all under tests/, .py).

Before implementation, all **10** new service cases failed on the absent helper and the process wrapper reproduced maintenance returning 200 and v2 returning the legacy total 23. Existing legacy tests/expectations were not changed or weakened. Independent mode contracts test matching-name A/B/C/admin totals 1/2/2/1, request timestamps 30 days before acceptance, acceptance at day 0/13/14, pending/ignored/cancelled/disconnected/block/unblock, empty owned with 23 legacy connections, forged identity/mode/capability, all four authenticated roles and missing-timestamp generic failure. The helper's trace contains SELECTs only, with zero audit/notification/write/emission.

Inspected actual route SQL under each process mode: legacy selects accepted `network_request` ordered by created_at and counts `connection_npc`; v2 selects only `network_edge.accepted_at WHERE state = ? AND (user_low_id = ? OR user_high_id = ?)`; maintenance has no social query. Assertions cover all five forbidden legacy tables and all owned graph tables, rather than result checks alone.

Initial browser sandbox run could not create localhost sockets; rerunning with authorized network/process permission passed. Initial mobile sandbox run could not execute Expo config subprocesses; authorized rerun passed all 53. No test was skipped or weakened to accommodate permissions. Chromium maintenance rendering uses a controlled 503 response; actual maintenance auth/no-graph/business/admin behavior is tested in its independent backend process. Signed-device WebView/native-session tests remain release work. No schema/migration/native/default-mode/production-v2/PR #26 changes.

## 2026-10-09 — T-201 whole-schema FK/admin-removal safety / Issue #32

Starting clean fetched/pulled master: `825e7e5d8392506f1496dd5db3cd8a54ccf24042`. Branch `codex/t201-fk-admin-removal-review`. Existing project-local `.venv-delivery`, `.playwright-delivery` and mobile dependencies reused; no dependency change/install. Every test/experiment database was new, workspace-local and migration-managed. The real `instance/forge.db` was never accessed, opened, enumerated, copied, hashed, migrated or modified.

| Validation | Exact result |
| --- | --- |
| New whole-schema/admin tests: `.venv-delivery/bin/python -m pytest -q --disable-warnings --tb=short --basetemp=test-results/pytest-fk-final tests/test_whole_schema_fks.py tests/test_admin_removal_safety.py` with workspace TMPDIR | **142 passed, 342 warnings in 33.78s**, 0 failed/skipped. Includes 42 parent-delete experiments with OFF and 42 with ON, plus all 28 user bindings, pooling/transaction pragma, ORM/final-state, orphans, schema/seed, migration/copy restore, races/failures/security/devices. |
| Broad focused migration/bootstrap/model/service/blocking/delivery/admin/socket/analytics/mode/account/profile/export gate (files below) with `--basetemp=test-results/pytest-fk-gate` | **427 passed, 1592 warnings in 172.16s**, 0 failed/skipped. |
| Full browser-enabled release gate: `TMPDIR=$PWD/test-results/runtime-tmp PLAYWRIGHT_BROWSERS_PATH=.playwright-delivery PLAYWRIGHT_HOST_PLATFORM_OVERRIDE=ubuntu24.04-x64 .venv-delivery/bin/python -m pytest -q --disable-warnings --tb=short --basetemp=test-results/pytest-fk-full-authorized` | **584 passed, 2016 deprecation warnings in 269.48s**, 0 failed/skipped. Includes all **25 real Chromium** regressions, backend/web/Node wrappers and independent legacy/maintenance/v2 HTTP/socket/analytics subprocess gates. |
| `node tests/analytics_frontend.cjs`; `node tests/owned_social_frontend.cjs` | **5 + 82 passed**, 0 failed/skipped. Also `node --test` file wrappers passed 2/2. |
| `node tests/csrf_frontend.cjs`; `node tests/profile_export_frontend.cjs` | Both passed, including inline script compilation and CSRF/export behavior. |
| `npm --prefix mobile test` (authorized process/network rerun) | **64 passed**, 0 failed/skipped in 2044.60643ms; includes merged PR #26 response-body timeout regressions. |
| `npm --prefix mobile run lint`; `./node_modules/.bin/tsc --noEmit` (cwd mobile) | Both passed, exit 0. |
| `.venv-delivery/bin/python` compile of all tracked Python plus new Python files | **56 files compiled**, no errors. |
| `.venv-delivery/bin/python scripts/review_foreign_keys.py` plus maintained canonical-evidence test | Generated physical-schema evidence successfully; fresh migrated DB has **31 application tables / 42 FKs / 28 user references / 22 RESTRICT / 20 default NO ACTION / FK OFF / zero violations**. No database argument accepted. |
| AST/diff safety review and `git diff --check` | Passed. **122 original definitions unchanged**; only `admin_user_action` and `_retire_account_sockets` changed in the entrypoint. Config/connect hook, ORM classes, migration history/tooling, static/mobile sources unchanged. |

Broad focused files (under tests/, .py): `test_whole_schema_fks`, `test_admin_removal_safety`, `test_migration_tooling`, `test_database_bootstrap`, `test_owned_social_models`, `test_owned_social_service`, `test_blocking_core_service`, `test_blocking_core_migration`, `test_owned_social_delivery`, `test_owned_social_http_subprocess`, `test_authz_regressions`, `test_socket_security`, `test_owned_social_analytics`, `test_analytics_modes_subprocess`, `test_analytics_routes`, `test_account_routes`, `test_profile_images`, `test_profile_routes`, `test_profile_export_frontend`.

Before the production fix, the two maintained removal regressions failed: the linked target disappeared, and the clean target was reported removed rather than failing closed. A fixture's missing required alumni document field was corrected before that confirmed reproduction. An independent FK-off ORM experiment inspects emitted SQL: only DELETE FROM user, no child UPDATE/DELETE; final children stay unchanged while FK-check reports orphans. A separate independent-connection experiment proves BEGIN IMMEDIATE alone cannot prevent a stale child insert after hard-delete commit.

The final route tests prove every direct user-FK binding preserves all child fields and changes only target suspension; nullable references, owned messages/member/read state, endorsements/audit, blocks/events are untouched. Both race commit orders preserve the identity and zero violations. Under-lock active-admin reauthorization, protected admin targets, missing/anonymous/non-admin/CSRF/origin failures, repeated clean removal without name-based links, only-target multi-device retirement/reconnect rejection and unsuspend pass. Reservation, preflight, UPDATE and commit injection return generic 503, preserve history, retain live sockets on failed transactions and allow a subsequent successful request. Commit-event failure initially exposed SQLAlchemy logical rollback leaving SQLite's physical transaction open; explicit DBAPI rollback fixed it. Socket tests initially exposed v2-only retirement; the bounded all-mode hook fixes default legacy as required. No established test was weakened.

All 42 physical constraints have a matching non-NULL fixture. ON rejects parent deletion and leaves child fields intact; OFF allows deletion and diagnostics include the selected constraint's own FK index, including the composite message-author FK. Several graph references can restrict the same parent simultaneously; the OFF orphan assertions independently verify each selected binding. New invalid child insertion rejects with ON, accepts with OFF and is detected without contents by FK-check, migration verify and read-only startup verify. Valid full fixtures and seed, ON initialization/empty downgrade/upgrade, and a verified backup-restored disposable copy pass. No intrinsic clean-schema blocker was found; persistent integrity remains unknown by design.

Sandbox evidence: initial full run passed **559 tests** but had **25 Chromium setup errors** because socket creation raised EPERM; a one-case probe reproduced that exact error. The authorized full rerun above passed all 584 with no skips. Initial mobile sandbox file-wrapper run failed its real-fetch timeout and Expo native-config subprocess files; authorized rerun passed all 64. Git writes/network/gh also required sandbox escalation. No test was weakened/skipped to avoid permissions. Temporary fixture corrections (complete block version-1/version-2 history) preserved migration semantic checks.

Final diff explicitly excludes global `PRAGMA foreign_keys=ON` in production, CASCADE/SET NULL changes, child/message/audit/block deletion, legacy cleanup, guessed ownership, real-database access, frozen migration edits, reporting/reviewer scope creep, production-v2/default-mode changes and broad refactoring. ON pragmas occur only on owned disposable test connections. Linked users suspend; clean users also suspend temporarily because FK-off competing writers prevent safe hard deletion. This is the user-authorized fail-closed fallback, not an irreversible policy.

No automated checks skipped. Signed-device WebView/native-session/release checks and persistent-copy rollout/recovery remain separate operator/device gates; this environment did not run them. This audit did not convert the full app suite to global ON or enable production v2. T-201 stays open for reviewed global-FK implementation, persistent recovery rehearsal and production cutover, with T-107 reporting/reviewer/deferred policy still required.
