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
