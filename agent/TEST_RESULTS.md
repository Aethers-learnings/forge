# Test results

Date: 2026-09-17

## Verified discovery baseline

| Check | Result | Evidence / scope |
| --- | --- | --- |
| Repository inventory | PASS | Flask backend, static web client, Expo WebView app, SQLite instance directory, and all durable agent records were inspected. |
| Route inventory | PASS | 61 Flask route decorators plus Socket.IO `join` handler were mapped in `API_MAP.md`. |
| Model inventory | PASS | 22 SQLAlchemy models and their foreign-key/unique constraints were mapped in `DATA_MODEL.md`. |
| Authentication/authorization inspection | PASS (inspection only) | Session, role gates, public/admin/business routes, and ownership checks were reviewed; P0 gaps are documented in `SECURITY.md`. |
| Mobile transport inspection | PASS (inspection only) | WebView URL/configuration was reviewed; P0 permissive-origin/cleartext/mixed-content behavior is documented. |
| Working-tree diff check before documentation | PASS | Pre-existing change: `mobile/src/app/index.tsx` (30 added lines). This documentation task did not alter it. |

## Not run / not available

- No automated application test suite was discovered, so no behavior-level unit, integration, browser, mobile, or security tests were run.
- The Flask server was not started and no database command was run, because this task is documentation-only and must not modify database contents.
- Dependency installation, mobile build, lint, and production deployment checks were not run.

## Required next evidence

P0 fixes must add regression tests for secret/configuration fail-closed behavior, Socket.IO identity-bound rooms, CSRF/origin policy, and mobile HTTPS allowlisting. Run those tests before claiming an implementation release baseline.
