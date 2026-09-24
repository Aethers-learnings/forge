# Test results

Date: 2026-09-18

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

Socket.IO identity-bound rooms and authenticated HTTP CSRF/origin regressions are now present. Next P0 evidence: T-004 mobile HTTPS allowlisting, then T-005 debug/demo deployment configuration checks. Run those before claiming a release baseline.

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
