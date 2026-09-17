# Forge project state

Phase: IMPLEMENTATION_1 — security containment and regression baseline

Last updated: 2026-09-17 (read-only discovery synchronization)

## Verified current state

- Forge is a single-process Flask application (`forge_backend.py`) serving a same-origin static HTML client and JSON API, backed by a project-local SQLite database at `instance/forge.db` through Flask-SQLAlchemy.
- Flask-SocketIO runs in threading mode. The client is a single `static/forge_demo.html` file that uses `fetch`, direct DOM rendering, and Socket.IO.
- An Expo Router application in `mobile/` is a thin WebView wrapper around a user-configurable Forge server URL; it is not a native implementation of Forge workflows.
- Roles are `trade`, `grad`, `business`, and `admin`. Admin self-registration is excluded; business listing and alumni-verification approval workflows exist.
- The working tree already contains an unrelated, pre-existing modification to `mobile/src/app/index.tsx`. It was not changed by this documentation task.

## Current objective

Establish a secure, tested baseline around the existing Flask/web/WebView prototype before feature expansion or migration work.

## Immediate gates

1. Resolve the remaining P0 findings in `SECURITY.md`, beginning with authenticated Socket.IO rooms.
2. Extend the new isolated Flask regression harness to authentication/authorization, tenant ownership, and upload boundaries before refactoring those paths.
3. Keep the prototype architecture in place while extracting only tested seams.

## Deliberate non-decisions

- PostgreSQL is a future migration, not current project state, and requires human approval.
- A backend, web-framework, or authentication replacement is not authorized by discovery alone.

## IMPLEMENTATION_1 progress

- T-001 is complete: `build_app_config()` rejects missing, default, or short `FORGE_SECRET_KEY` values in `FORGE_ENV=production`; local development receives a process-local random key instead of a predictable fallback.
- Production session cookies are explicitly `Secure`, `HttpOnly`, and `SameSite=Lax`.
- `tests/` now provides an isolated temporary-SQLite Flask harness. It sets `FORGE_DATABASE_URI` before importing the application, creates/drops schema per test, and never uses `instance/forge.db`.
- T-002 (Socket.IO identity-bound rooms and origin restriction) is now the highest-priority eligible task.
