# Decisions

## D-001: Maintain the prototype during stabilization

Status: accepted

Forge will not receive a large rewrite merely because `forge_backend.py` and the static web client are monolithic. Incremental extraction, protected by regression tests, is the approved direction. Classification: SAFE_INCREMENTAL.

## D-002: Backend continuity

Status: accepted

Flask is the current backend. Replacing Flask is a fundamental architecture change and requires human approval. Classification: HUMAN_APPROVAL_REQUIRED.

## D-003: Web continuity

Status: accepted

The static web frontend remains the production/prototype frontend until an incremental migration path has been demonstrated against a stable contract. A wholesale frontend replacement is MAJOR_REVIEW; small accessibility, security, and testable component extractions are SAFE_INCREMENTAL.

## D-004: Mobile continuity

Status: accepted

The Expo/WebView application remains while native-mobile parity is developed. Native features must be introduced one workflow at a time without removing the wrapper prematurely. Classification: SAFE_INCREMENTAL.

## D-005: Data platform

Status: accepted

SQLite is the currently verified persistence technology. PostgreSQL is a future option only; its adoption, data migration, operational plan, and rollback require human approval. Classification: HUMAN_APPROVAL_REQUIRED.

## D-006: Authentication boundary

Status: accepted

The present signed-cookie/session mechanism remains the baseline only while P0 hardening is performed. Any fundamental authentication change (identity provider, token model, account model, or session replacement) requires human approval. Classification: HUMAN_APPROVAL_REQUIRED.

## D-007: Environment-derived session configuration

Status: accepted (2026-09-17)

Forge retains Flask's signed-cookie session model. `FORGE_ENV=production` is the explicit production boundary: it requires a non-default `FORGE_SECRET_KEY` of at least 32 characters and enables `Secure`, `HttpOnly`, `SameSite=Lax` session cookies. Development/test environments never use the historical predictable fallback; if no secret is supplied they receive a process-local random key. `FORGE_DATABASE_URI` is a supported configuration override solely to isolate tests and deployment configuration from the repository's default SQLite path. Classification: SAFE_INCREMENTAL.

## D-008: Deterministic autonomous engineering controller

Status: accepted (2026-09-24)

Forge may use the local `scripts/forge-auto` controller for dependency-satisfied `SAFE_INCREMENTAL` backlog work. Python deterministically parses the task backlog, enforces governance, snapshots dirty paths, selects checks, bounds model calls and repair loops, validates staging, records the run, and creates a local Forge Agent commit. Isolated Codex subprocesses are limited to planning when enabled, implementation, review, and repair; they do not select work or decide safety boundaries. `MAJOR_REVIEW`, `HUMAN_APPROVAL_REQUIRED`, and protected architectural/authentication/destructive-operation boundaries stop before modification. The controller never pushes. Classification: SAFE_INCREMENTAL.

## D-009: Extract small route groups with explicit existing dependencies

Status: implemented for T-203 / Issue #1 (2026-09-24), pending PR review

Use blueprint factories for notifications and onboarding, passing the existing database, login guard, and model/step mapping from `forge_backend.py`. This avoids circular imports and duplicate entrypoint initialization when run as `__main__`. Register at the former route-group location and retain all handler operations and transaction boundaries. Keep query logic in these small handlers; do not add a generic service/repository layer or app-factory redesign. Classification: SAFE_INCREMENTAL under D-001/D-002, with no fundamental architectural or schema decision.

Internal Flask endpoint names become blueprint-qualified; public route contracts remain fixed. Further extractions need their own bounded regression evidence. Ownership/schema changes, session redesign, and retention changes remain outside T-203 and require the reviews already recorded in the backlog.

## D-010: Keep Issue #3 limited to five profile workflow routes

Status: implemented for T-203 / Issue #3 (2026-09-24), pending PR review

Continue D-009's explicit blueprint-factory injection in `forge_routes/profile.py`. Preserve the original operations and transaction boundaries; retain existing shared completion/keyword helpers in the entrypoint and avoid an unnecessary service layer. Classification: SAFE_INCREMENTAL.

Leave optional profile image routes in `forge_backend.py`: they combine canonicalization, filesystem writes/unlinks, database rollback/commit ordering, private caching, and visibility-based serving. Moving that storage/security boundary would broaden this increment. This is a scope deferral, not a retention or authorization change. Public-profile reads and identity/workflow/media/analytics extraction remain follow-up work. No schema, authentication, ownership, or irreversible-data decision was needed or implemented.

## D-011: Extract only the three analytics handlers for Issue #5

Status: implemented for T-203 / Issue #5 (2026-09-26), pending PR review

Continue D-009's explicit dependency injection in one cohesive `forge_routes/analytics.py` blueprint. Retain route-local queries and the existing `daily_series`/`cumulative` helpers; no generic repository/service abstraction is needed. Add behavior regressions before moving production code and compare runtime URL/schema snapshots and normalized ASTs. Classification: SAFE_INCREMENTAL.

Preserve T-106 metrics and all existing quirks, including shared network counts, display-name post attribution, application-row demographic counting, duplicate skill tokens, and the login guard's last-seen transaction. Do not repair ownership, schema, authentication, media, or retention behavior in this extraction. T-203 remains open for identity/remaining workflow/media work.
