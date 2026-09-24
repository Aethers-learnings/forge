# Session log

## 2026-09-18 — IMPLEMENTATION_1 T-003: authenticated API CSRF/origin protection

- Inspected current agent records, Flask signed-session authentication, unsafe API routes, central frontend helper/direct video upload, and isolated test harness in the existing host checkout. T-002 was already committed at `32b9790`; only the mobile and sandbox edits were pre-existing.
- Added session-bound `secrets.token_urlsafe(32)` CSRF tokens, constant-time comparison, and a before-request guard for authenticated unsafe `/api/` requests. Origin takes precedence over Referer; missing/foreign/malformed origins fail closed against direct scheme/Host. No ProxyFix or forwarded-header trust.
- Added authenticated `GET /api/auth/csrf-token` (`csrfToken`, no-store). Rotate on register/login/demo-login, clear on logout/invalid-session cleanup; preserve anonymous authentication/reset flows and existing authentication architecture.
- Updated central API and multipart video fetch token headers; retain browser multipart Content-Type. Centralized client identity changes, cleared token caches, deduplicated acquisition, rejected stale token responses, and made failed logout visible without pretending success.
- Added `tests/test_csrf_security.py`, `tests/test_csrf_frontend.py`, and `tests/csrf_frontend.cjs`. Corrected initial DELETE test setup to use an admin for the existing admin-only route; corrected added backend line endings without whole-file normalization.
- Full host-venv verification: **56 passed, 179 warnings in 10.49s**; warnings are existing datetime.utcnow()/SQLAlchemy Query.get() deprecations exercised by wider coverage. Node frontend regressions ran without skips; no live browser/mobile/proxy test claimed. `git diff --check` passed.
- Updated STATE, TASKS, SECURITY, TEST_RESULTS, and SESSION_LOG only after tests passed. T-003 complete; T-004 mobile HTTPS/navigation allowlisting is next P0. Security records also reconcile stale T-001 fallback-secret/cookie statements against passing implementation evidence.
- Modified this session: `forge_backend.py`, `static/forge_demo.html`, the three new test files, and the five named agent records. Baseline hashes confirm `mobile/src/app/index.tsx` and `sandbox/Dockerfile` remain byte-for-byte unchanged. No staging or commit performed.

## 2026-09-18 — T-002 completion record synchronization

- Updated only STATE, TASKS, SECURITY, TEST_RESULTS, and SESSION_LOG to reflect completed T-002, using the verified host terminal output and current implementation.
- Socket.IO rejects anonymous/suspended connections and derives user/role rooms exclusively from authenticated Flask session identity, ignoring client-supplied `userId`/`role` claims.
- Wildcard `cors_allowed_origins` removed for default same-origin checking; static frontend emits `join` without identity claims.
- `tests/test_socket_security.py` added; verified original host suite: 15 passed in 1.86s with 17 non-blocking deprecation warnings (`datetime.utcnow()` and SQLAlchemy `Query.get()`).
- Confirmed `.venv-host/` is ignored locally via `.gitignore`. T-003 CSRF/origin protection is next P0.
- Pre-existing mobile and sandbox changes must remain untouched; no commit made. Existing backend diff includes line-ending normalization from the earlier implementation, which this documentation task does not alter.

Verification: fresh `.venv-host/bin/python -m pytest -q` passed (15 passed, 17 warnings in 2.19s) after approved filesystem access for the temporary test database. `git diff --check` passed and the documentation diff was reviewed. Baseline hashes confirm only the five intended agent records changed, including byte-for-byte preservation of `mobile/src/app/index.tsx` and `sandbox/Dockerfile`. No commit created.

## 2026-09-17 — IMPLEMENTATION_1 T-001: session configuration and isolated test harness

Scope: completed the highest-priority approved safe-incremental task only; no commit created.

Changes and evidence:

- Replaced the predictable `dev-secret-change-me` fallback with `build_app_config()`. Production (`FORGE_ENV=production`) now fails startup when `FORGE_SECRET_KEY` is absent, one of the historical/default values, or shorter than 32 characters. Development/test falls back only to a process-local random secret.
- Added explicit Flask session cookie settings: `HttpOnly`, `SameSite=Lax`, and `Secure` in production.
- Added `FORGE_DATABASE_URI` configuration support and a `pytest` harness that uses temporary workspace-local SQLite files, creates/drops schema per test, and does not touch `instance/forge.db`.
- Added nine configuration/isolation regressions, including a subprocess startup failure check. Full suite result: 9 passed in 1.52s using a project-local virtual environment.
- Reviewed scope: no Flask, SQLite, frontend, mobile architecture, database technology, or authentication-model replacement. T-002 is next. Pre-existing `mobile/src/app/index.tsx` modification was preserved.

## 2026-09-17 — discovery record synchronization

Scope: documentation only. Inspected the Forge implementation, prototype web client, Expo/WebView wrapper, dependencies, Git status, durable records, route/model declarations, and security-relevant configuration. No application source, mobile source, database contents, or Git history was modified; no commit was created.

Findings recorded:

- Current system is Flask + Flask-SQLAlchemy/SQLite + Flask-SocketIO + static HTML/JS, with an Expo WebView wrapper.
- Role, approval, profile, content, notification, analytics, upload, and optional SMTP/Anthropic flows were mapped.
- P0 findings: default predictable session secret; unauthenticated Socket.IO room membership with wildcard CORS; arbitrary/insecure mobile WebView origin/transport; and no CSRF protection for cookie-authenticated mutations.
- Migration direction is incremental, test-first stabilization. Flask, current web frontend, and Expo/WebView wrapper remain current; PostgreSQL and fundamental authentication changes require human approval.
- Pre-existing dirty file observed: `mobile/src/app/index.tsx`; preserved unchanged.

Outcome: project state advanced from DISCOVERY to IMPLEMENTATION_1, with P0 containment and regression baseline as the next work.

## 2026-09-18 — T-004 SAFE_INCREMENTAL

Implemented in `/home/pablo/Documents/Programming/04-Projects/forge` at starting HEAD `ea8ffc3`; the stale mirror was not used. Exact HTTPS origins come from build-time configuration with no production default. Missing configuration permits no connection. Persisted URL, Connect/save, initial WebView source and navigation share the pure policy; invalid saved values remain visible in recoverable settings without loading or automatic replacement. Existing mobile error handling is preserved. Popups and subframe navigation are blocked, mixed content is never allowed, Android cleartext is disabled through an Expo manifest plugin, and iOS ATS has no arbitrary-load/local-network exceptions.

Verified: 33 mobile tests; mobile lint, TypeScript, native preview/production config introspection and diff check pass. Isolated Forge suite: 56 passed, 179 existing deprecation warnings in 6.60s. Signed release-device tests remain a release gate (see MOBILE_PLAN.md). No commit or push. T-005 is next P0.

Preservation: Dockerfile hash matches the starting baseline. The static frontend changed concurrently during this session; this task never wrote it and leaves its current contents intact. The pre-existing mobile error handling remains. No existing locked dependency versions changed or entries were removed.

Added missing lint tooling and repaired two small existing lint issues (apostrophe and web hydration). npm reported 14 moderate vulnerabilities, ESLint deprecation and a pending resolver script; no broad upgrades/script approvals. Updated all six requested agent records. Remaining release work is in MOBILE_PLAN.md; T-005 is next P0.

## 2026-09-24 — prepare V2/profile-image commit and push

Reviewed the real current master checkout and preserved all existing V2/profile-image source changes, including backend line-ending normalization. Intended source scope: forge_backend.py, requirements.txt, static/forge_demo.html, tests/conftest.py, tests/test_profile_images.py. Updated state and test evidence. All 69 tests and frontend/backend syntax, CSRF/logout, and whitespace checks passed. User authorized a normal push to origin/master without history rewriting. sandbox/Dockerfile excluded and preserved byte-for-byte (SHA-256 c05ebde6159325507f89fa05b66c620cb6afccf76ada0af5c017d53b6b401f75). Frontend upload/remove controls are absent and remain future work; this checkpoint does not claim they exist. Commit/push outcome is reported in the task response.

## 2026-09-24 — IMPLEMENTATION_1 T-005: debug/demo deployment containment

- Started from pushed master `872eb2ba9bba6816946c8039a77e0dcd1f79171f`; `sandbox/Dockerfile` was the only pre-existing dirty file and remained outside task scope.
- Changed runtime configuration so `FORGE_DEBUG` and `FORGE_DEMO_MODE` default off and may only be enabled in explicit `FORGE_ENV=development`.
- Added strict boolean parsing and validated environment names. Unknown/misspelled environments fail startup. Staging and production/prod use deployment secret requirements and Secure cookies.
- Added the `.env.example` placeholder secret to the rejected deployment-secret set.
- Decoupled `/api/auth/demo-login` from Flask debug. Debug alone now returns 404 from demo login. `seed-demo` and automatic startup demo seeding require explicit demo mode.
- Added configuration/import/CLI/demo-login regressions, including fail-closed environment and placeholder-secret cases.
- Verification after final hardening: focused configuration/CSRF suite **73 passed, 288 warnings in 9.65s**; full isolated Forge suite **93 passed, 377 warnings in 10.60s**; Python compilation, Node frontend CSRF/logout regressions, and `git diff --check` passed.
- Existing datetime/SQLAlchemy deprecation warnings remain out of scope. No architecture, authentication model, schema, frontend framework, or deployment platform replacement was introduced.
- T-005 completes roadmap P0 T-001 through T-005. T-101 regression coverage is next. `sandbox/Dockerfile` remains unrelated, modified, uncommitted, and excluded.

## 2026-09-24 — IMPLEMENTATION_1 T-101: authentication/authorization regression baseline

- Began from pushed T-005 master `2321515decc63ece7bd71ae2805dbcf3b7263a18`; unrelated `sandbox/Dockerfile` remained outside task scope.
- Added `tests/test_authz_regressions.py` only; no production application behavior changed.
- Covered registration/login, role gates, notification ownership, profile visibility, business/admin approval, listing approval, and alumni-verification approval behavior.
- First run: 22 passed / 3 failed because the new notification fixtures guessed `kind`; model inspection confirmed `Notification.type`. Corrected the tests only.
- Final dedicated suite: **25 passed, 133 warnings in 5.94s**.
- Full isolated Forge suite: **118 passed, 510 warnings in 15.04s**. Frontend CSRF/logout regressions, Python compilation, and `git diff --check` passed.
- T-101 complete; T-102 upload-boundary hardening is next.
- `sandbox/Dockerfile` remains modified, unrelated, uncommitted, and excluded.
# 2026-09-24 — Autonomous runtime MVP

- Added deterministic local `scripts/forge-auto` orchestration tooling, focused unit tests, governance/model-routing documentation, and decision D-008. It preserves pre-existing dirty product-task paths and does not run autonomous product work.

## 2026-09-24 — IMPLEMENTATION_1 T-102: upload boundary hardening

- Added configurable isolated upload storage, global request-size protection, route-level Content-Length preflight, and bounded streamed video writes capped at 50 MiB.
- Added supported-container signature-family validation for ISO-BMFF, EBML, and AVI instead of relying only on filename extensions.
- Changed ffmpeg handling to fail closed when processing is available but fails. When ffmpeg is absent, signature-validated originals are retained with placeholder thumbnails.
- `/uploads/<path:name>` now requires authentication, serves only media referenced by active non-removed posts, applies role-feed authorization to non-admin users, and retains admin moderation access.
- Soft removal immediately revokes media access. Physical bytes are deliberately retained because an irreversible deletion/retention lifecycle requires separate approval.
- Added isolated upload storage to the test fixture and 10 focused upload-security regressions.
- Final verification: dedicated suite **10 passed, 58 warnings in 3.93s**; full Forge suite **139 passed, 568 warnings in 17.05s**; Python compilation and `git diff --check` passed.
- Container-signature checking is not malware/deep media scanning; that limitation remains documented.
- T-102 complete; T-103 is next. `sandbox/Dockerfile` remains separate autonomous-agent infrastructure work and is excluded from this task.

## 2026-09-24 — IMPLEMENTATION_1 T-103: password-reset token hardening

- Stored password-reset tokens as SHA-256 digests; reset redemption hashes the supplied token before lookup and continues to clear the digest after use.
- Kept the plaintext development token limited to explicit Flask debug behavior, which existing T-005 configuration prohibits outside local development.
- Removed email fallback/failure logging of recipients, subjects, bodies, exception details, and therefore reset URLs/tokens. Non-debug without SMTP intentionally cannot deliver reset email but returns the existing generic anti-enumeration response.
- Added reset-token digest, redemption, non-debug response, and sensitive-log regressions; updated the existing anonymous CSRF reset test to retrieve the debug token from its intended response rather than the database.
- Verification: focused suite **44 passed, 56 warnings in 7.83s**; full suite **144 passed, 162 warnings in 22.39s**; backend compilation and `git diff --check` passed.

- 2026-09-24 11:07 UTC: autonomous T-105 completed after reviewer PASS; artifacts `.forge-agent/runs/20260924T110515Z-T-105`; checks: git diff --check => 0; /home/pablo/Documents/Programming/04-Projects/forge/.venv-host/bin/python -m py_compile forge_backend.py tests/test_authz_regressions.py => 0; /home/pablo/Documents/Programming/04-Projects/forge/.venv-host/bin/python -m pytest -q => 0.
