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

## D-012: User-pair ownership and participant authorization

Status: **PROPOSED / REQUIRES HUMAN APPROVAL** (2026-09-26, T-104 / Issue #9)

Recommend one canonical user-pair edge for request/accepted relationship state, derived discoverable-user suggestions, actor-owned revocable endorsements, unique direct conversations with explicit immutable membership, session-authored messages and per-member read cursors. Accepted connections may create/send; disconnected members retain read-only history. Admin status does not grant private-message access. Existing Flask/session/CSRF/SQLite architecture remains. See [OWNERSHIP_DESIGN sections 2–3](OWNERSHIP_DESIGN.md#2-target-model-and-invariants) for constraints, transitions and authorization.

Human decision: approve user-to-user scope (or require a separate organizational model), discovery/cooldown, connected-only messaging, endorsement context and text limit. Separate request/connection tables and open messaging are alternatives with more reconciliation/moderation complexity. Classification: MAJOR_REVIEW; no schema/runtime approval or implementation occurs in this PR.

## D-013: Preserve and quarantine unprovable legacy ownership

Status: **PROPOSED / REQUIRES HUMAN APPROVAL** (2026-09-26, T-104 / Issue #9)

Keep all five ownerless legacy social tables intact and inaccessible through the future real-user APIs; start a separate empty owned graph. No guessed identity from display names, seed text or `me/them`, and no dual-read/dual-write. Independently proven imports require an approved mapping manifest. New identity references use RESTRICT; review current admin-remove fallback before enforcing FKs. Permanent erasure, anonymization, legacy cleanup and retention remain separate decisions. See [migration stages](OWNERSHIP_DESIGN.md#5-staged-sqlite-migration-and-rollback-plan-not-executable-here).

Human decision: accept loss of legacy UI visibility while retaining its data, or commission evidence-based mapping. Automatic reassignment/discard is rejected without evidence and explicit approval. Classification: MAJOR_REVIEW; destructive policy remains HUMAN_APPROVAL_REQUIRED.

## D-014: Explicit social API compatibility boundary

Status: **PROPOSED / REQUIRES HUMAN APPROVAL** (2026-09-26, T-104 / Issue #9)

Recommend preserving existing paths behind an ownership-v2 capability header and coordinated web/WebView transition. Required preconditions, desired-state endorsements, pure GET plus explicit read, paged results, stable send retry keys and real participant-relative messages deliberately change the social contract. Old clients must receive an update response rather than reinterpret legacy NPC IDs. Participant-only sockets carry minimal invalidations after committed writes; persistent notification shape remains stable. The capability header does not authorize access. See [endpoint mapping](OWNERSHIP_DESIGN.md#4-api-and-client-transition--proposed-contract-boundary).

Human decision: approve the header boundary and listed status/body/semantic changes, or choose explicit versioned paths before coding; no transparent unsafe fallback. Native messaging remains unimplemented and blocked on the approved contract. Classification: MAJOR_REVIEW. This record does not amend the currently implemented API_CONTRACT.

## D-015: Migration gates and secure rollback

Status: **PROPOSED / REQUIRES HUMAN APPROVAL** (2026-09-26, T-104 / Issue #9)

T-201 must provide migration/version tooling, consistent SQLite backups and restore rehearsals before additive tables/indexes/constraints. Enabling foreign keys needs whole-schema orphan and admin-removal review. Future implementation proceeds behind a gate with three-user authorization, independent-connection race, client, notification/socket, migration and rollback tests. Include the shared network analytics consumer in cutover. After new writes, rollback preserves new data and uses a secure compatible release or maintenance response, never an ownerless legacy fallback or an older snapshot over new messages.

Human decision: approve staged rollout/maintenance and recovery ownership after reviewing the [plan and required tests](OWNERSHIP_DESIGN.md#6-threat-model-and-required-future-tests). Any unrelated data repair, irreversible cleanup or fundamental authentication change stops for separate review. Classification: MAJOR_REVIEW; this design authorizes none of those operations.
