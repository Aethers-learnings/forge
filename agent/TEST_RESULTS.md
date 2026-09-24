# Test results

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
