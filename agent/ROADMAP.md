# Roadmap

Status: dependency-aware implementation roadmap. It distinguishes approved incremental work from changes needing review/approval.

## Phase 1 — security containment and regression baseline

- P0 configuration/session fail-closed behavior, secure cookie settings, and production debug guard — SAFE_INCREMENTAL.
- P0 Socket.IO authenticated room binding and origin policy — SAFE_INCREMENTAL.
- P0 web CSRF/origin policy and mobile HTTPS/allowlist transport policy — SAFE_INCREMENTAL.
- Regression-test harness and coverage for the above, role gates, ownership, uploads, and approval workflow — SAFE_INCREMENTAL.

Exit: P0 findings fixed and tested; no debug/demo exposure in production configuration.

## Phase 2 — data ownership and workflow correctness

- Define secure user-to-user connection/conversation model; replace shared demo-state behavior incrementally — MAJOR_REVIEW.
- Add durable author/actor ownership and audit semantics to posts/comments/testimonials — MAJOR_REVIEW.
- Correct opportunity visibility, listing lifecycle, analytics scoping, and moderation/retention behavior — SAFE_INCREMENTAL where no data migration is required; otherwise MAJOR_REVIEW.
- Add migration tooling and reversible additive schema changes while remaining on SQLite — MAJOR_REVIEW.

Exit: every mutable resource has an ownership and authorization rule covered by tests.

## Phase 3 — web and mobile parity

- Extract stable API contracts/documentation and test client behavior — SAFE_INCREMENTAL.
- Improve the existing web frontend incrementally for accessibility, responsive layout, error states, and security headers — SAFE_INCREMENTAL.
- Add native Expo screens one workflow at a time while retaining the WebView fallback — SAFE_INCREMENTAL.
- Replace the static web frontend only after an incremental migration path proves feature and accessibility parity — MAJOR_REVIEW.

## Phase 4 — scale and platform decisions

- Assess PostgreSQL migration, backups, operational ownership, data migration and rollback — HUMAN_APPROVAL_REQUIRED.
- Replace Flask, replace frontend framework, introduce a major third-party service, or fundamentally change authentication — HUMAN_APPROVAL_REQUIRED.

## T-104 review gate (2026-09-26)

Issue #9 submits [OWNERSHIP_DESIGN](OWNERSHIP_DESIGN.md) for human architecture review. Design preparation does not complete ownership implementation or unblock T-201/native messaging automatically. Review proposed D-012–D-015 first; then approve migration tooling/FK and legacy-data treatment, followed by regression-protected service/API/client increments and a gated cutover. T-203 extraction must continue preserving existing behavior rather than implementing this proposal incidentally.
