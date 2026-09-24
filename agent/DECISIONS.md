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
