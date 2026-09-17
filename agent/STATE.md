# Forge project state

Phase: IMPLEMENTATION_1 — security containment and regression baseline

Last updated: 2026-09-18 (T-002 completion records)

## Verified current state

- Forge is a single-process Flask application (`forge_backend.py`) serving a same-origin static HTML client and JSON API, backed by a project-local SQLite database at `instance/forge.db` through Flask-SQLAlchemy.
- Flask-SocketIO runs in threading mode. The client is a single `static/forge_demo.html` file that uses `fetch`, direct DOM rendering, and Socket.IO.
- An Expo Router application in `mobile/` is a thin WebView wrapper around a user-configurable Forge server URL; it is not a native implementation of Forge workflows.
- Roles are `trade`, `grad`, `business`, and `admin`. Admin self-registration is excluded; business listing and alumni-verification approval workflows exist.
- The working tree already contains an unrelated, pre-existing modification to `mobile/src/app/index.tsx`. It was not changed by this documentation task.

## Current objective

Establish a secure, tested baseline around the existing Flask/web/WebView prototype before feature expansion or migration work.

## Immediate gates

1. Resolve the remaining P0 findings in `SECURITY.md`, beginning with T-003 CSRF/origin protection for state-changing cookie routes.
2. Extend the new isolated Flask regression harness to authentication/authorization, tenant ownership, and upload boundaries before refactoring those paths.
3. Keep the prototype architecture in place while extracting only tested seams.

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
- T-003 (CSRF/origin protection) is the next P0 task. Pre-existing changes to `mobile/src/app/index.tsx` and `sandbox/Dockerfile` are preserved; no commit is authorized for this session.
