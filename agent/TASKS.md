# Tasks

Status: prioritized, dependency-aware implementation backlog. Classification identifies scope governance, not urgency.

## P0

- [x] T-001 — Fail closed when `FORGE_SECRET_KEY` is missing/default; define production cookie security configuration and a test. Depends on: none. Classification: SAFE_INCREMENTAL. Completed 2026-09-17: production startup rejects absent, default, and short secrets; production session cookies are Secure, HttpOnly, and SameSite=Lax; isolated Flask test harness added.
- [x] T-002 — Bind Socket.IO room joins exclusively to authenticated session identity/role; restrict origins; add cross-user subscription regression tests. Depends on: T-001 test harness. Classification: SAFE_INCREMENTAL. Completed: authenticated session-derived user/role rooms; anonymous/suspended connections rejected; client identity claims ignored; default same-origin checking restored; frontend join payload removed; `tests/test_socket_security.py` added. Verified host suite: 15 passed in 1.86s, 17 non-blocking deprecation warnings.
- [x] T-003 — Add CSRF/origin protection for state-changing cookie routes and test valid/invalid requests. Depends on: T-001. Classification: SAFE_INCREMENTAL. Completed 2026-09-18: session-bound random token, constant-time comparison, same-origin Origin/Referer guard, authenticated token endpoint, frontend API/multipart integration, identity/logout cache reset, and regression coverage. Full suite: 56 passed, 179 non-blocking warnings in 10.49s; diff check passed. Anonymous auth flows preserved; no proxy trust or authentication architecture change.
- [x] T-004 — Implemented 2026-09-18: exact HTTPS build-time origins, recoverable settings, navigation/popup controls and native transport restrictions. Depends on: T-001. Classification: SAFE_INCREMENTAL. 33 mobile tests, lint, TypeScript, native config verification and 56 Forge tests pass. Manual release-device gates remain in MOBILE_PLAN.md.
- [x] T-005 — Completed 2026-09-24: debug and demo modes default off; both are restricted to explicit local development; unknown environment names and ambiguous booleans fail closed; staging/production require deployment-grade secrets and Secure cookies; demo login/seed/startup seeding require explicit demo mode. Focused suite: 73 passed; full Forge suite: 93 passed. Depends on: T-001. Classification: SAFE_INCREMENTAL.

## P1

- [x] T-101 — Completed 2026-09-24: added `tests/test_authz_regressions.py` covering self-registration/admin exclusion, student email-domain checks, duplicate usernames, login identity/suspension handling, student/business/admin role gates, notification ownership, hidden-profile access, profile-view recording, business approval, listing approval, and alumni verification. Dedicated suite: 25 passed; full Forge suite: 118 passed. Depends on: T-001. Classification: SAFE_INCREMENTAL.
- [x] T-102 — Completed 2026-09-24: added request-size preflight and bounded streaming, container-signature validation, fail-closed ffmpeg processing, authenticated/feed-authorized media serving, soft-removal access revocation with byte retention pending a separately approved deletion policy, isolated upload storage, and upload regressions. Dedicated suite: 10 passed; full Forge suite: 139 passed. Depends on: T-101. Classification: SAFE_INCREMENTAL.
- [x] T-103 — Completed 2026-09-24: reset tokens are SHA-256 digests at rest; only explicit local debug returns a development token; SMTP absence/failure logs no recipients, subjects, bodies, or tokens; dedicated reset-security regressions added. Depends on: T-101. Classification: SAFE_INCREMENTAL.
- [ ] T-104 — Define ownership and authorization rules for network, suggestions, endorsements, and conversations; introduce a migration plan before code changes. Depends on: T-101. Classification: MAJOR_REVIEW.
- [x] T-105 — Ensure only approved/live listings produce student-visible opportunities; cover lifecycle with tests. Depends on: T-101. Classification: SAFE_INCREMENTAL.
- [x] T-106 — Correct business/admin analytics scope and document metric semantics. Depends on: T-101. Classification: SAFE_INCREMENTAL.

## P2

- [ ] T-201 — Add reversible schema migration tooling and explicit indexes/constraints appropriate to verified access patterns. Depends on: T-104 data design. Classification: MAJOR_REVIEW.
- [x] T-202 — Add stable API contract documentation and request/response tests before route extraction. Depends on: T-101. Classification: SAFE_INCREMENTAL.
- [ ] T-203 — Incrementally extract Flask blueprints/services around identity, workflows, media, and analytics. Depends on: T-101, T-202. Classification: SAFE_INCREMENTAL. First increment (Issue #1, PR #2): notification/onboarding blueprints merged. Second increment (Issue #3, 2026-09-24): five profile workflow routes extracted into `forge_routes/profile.py` after 50 new baseline regressions; full suite 256 passed, pending PR review. Image/storage and public-profile routes remain in the entrypoint under D-010. Remaining identity, workflow, media, and analytics extraction stays open; do not combine it with T-104/T-201 ownership/schema changes.
- [ ] T-204 — Improve web accessibility, responsive behavior, error handling, CSP/security headers, and client tests without replacing the static frontend. Depends on: T-003, T-202. Classification: SAFE_INCREMENTAL.
- [ ] T-205 — Implement native Expo workflows in priority order while WebView stays available. Depends on: T-004, T-202. Classification: SAFE_INCREMENTAL.

## P3

- [ ] T-301 — Evaluate a proven incremental web migration path; do not replace the existing frontend until parity evidence exists. Depends on: T-202, T-204. Classification: MAJOR_REVIEW.
- [ ] T-302 — Evaluate PostgreSQL, backup/restore, migration/rollback, and operations. Depends on: T-201 and documented data ownership. Classification: HUMAN_APPROVAL_REQUIRED.
- [ ] T-303 — Consider backend replacement only with a human-approved architecture decision and migration plan. Depends on: Phase 2/3 evidence. Classification: HUMAN_APPROVAL_REQUIRED.
- [ ] T-304 — Consider a fundamental authentication change only with human approval, threat model, migration, and rollback. Depends on: P0 completion. Classification: HUMAN_APPROVAL_REQUIRED.
