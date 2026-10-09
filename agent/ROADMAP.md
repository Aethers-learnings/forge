# Roadmap

Current implementation (2026-10-09): PR #27 merged directed blocking and PR #29 merged participant-safe delivery. Issue #30 implements student analytics ownership isolation for controlled v2 rehearsal. Legacy remains the default; production v2 is not enabled. T-201 whole-schema FK/admin-removal, persistent rollout/recovery and production cutover gates, plus T-107 reporting/reviewer/policy gates, remain open. Dated entries below preserve their historical scope.

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

## Ownership approval and production gate (2026-09-28)

This update supersedes the earlier statements that D-012–D-015 await approval: the user approved all four decisions as proposed. Their target remains unimplemented; current schema, API, authentication and client behavior are unchanged. T-104 design/review is complete and T-201's design dependency is satisfied, with migration/integrity/recovery verification still required. Social networking is **not production-complete** until blocking/reporting is designed, implemented and tested under D-016 / T-107 and [OWNERSHIP_DESIGN section 8](OWNERSHIP_DESIGN.md#8-blocking-and-reporting-production-completion-gate). This includes server enforcement, private report handling, explicitly authorized audited moderation, web/WebView and released-native coverage, and security/race/rollback tests. No blanket admin private-message access or irreversible retention policy is approved.

T-107's [core safety design](SAFETY_DESIGN.md) was approved on 2026-09-28. The listed retention, reviewer provisioning, appeals/notices and other deferred policies still need separate decisions before the affected features or irreversible data handling. Implement and test the approved core under the T-201 migration and D-014 client gates; a design approval alone does not satisfy the production exit gate.
