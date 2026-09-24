# Tasks

Status: prioritized, dependency-aware implementation backlog. Classification identifies scope governance, not urgency.

## P0

- [x] T-001 — Fail closed when `FORGE_SECRET_KEY` is missing/default; define production cookie security configuration and a test. Depends on: none. Classification: SAFE_INCREMENTAL. Completed 2026-09-17: production startup rejects absent, default, and short secrets; production session cookies are Secure, HttpOnly, and SameSite=Lax; isolated Flask test harness added.
- [x] T-002 — Bind Socket.IO room joins exclusively to authenticated session identity/role; restrict origins; add cross-user subscription regression tests. Depends on: T-001 test harness. Classification: SAFE_INCREMENTAL. Completed: authenticated session-derived user/role rooms; anonymous/suspended connections rejected; client identity claims ignored; default same-origin checking restored; frontend join payload removed; `tests/test_socket_security.py` added. Verified host suite: 15 passed in 1.86s, 17 non-blocking deprecation warnings.
- [x] T-003 — Add CSRF/origin protection for state-changing cookie routes and test valid/invalid requests. Depends on: T-001. Classification: SAFE_INCREMENTAL. Completed 2026-09-18: session-bound random token, constant-time comparison, same-origin Origin/Referer guard, authenticated token endpoint, frontend API/multipart integration, identity/logout cache reset, and regression coverage. Full suite: 56 passed, 179 non-blocking warnings in 10.49s; diff check passed. Anonymous auth flows preserved; no proxy trust or authentication architecture change.
- [x] T-004 — Implemented 2026-09-18: exact HTTPS build-time origins, recoverable settings, navigation/popup controls and native transport restrictions. Depends on: T-001. Classification: SAFE_INCREMENTAL. 33 mobile tests, lint, TypeScript, native config verification and 56 Forge tests pass. Manual release-device gates remain in MOBILE_PLAN.md.
- [x] T-005 — Completed 2026-09-24: debug and demo modes default off; both are restricted to explicit local development; unknown environment names and ambiguous booleans fail closed; staging/production require deployment-grade secrets and Secure cookies; demo login/seed/startup seeding require explicit demo mode. Focused suite: 73 passed; full Forge suite: 93 passed. Depends on: T-001. Classification: SAFE_INCREMENTAL.

## P1

- [ ] T-101 — **Next task.** Create a Flask regression suite for registration/login, role gates, notification ownership, profile visibility, and approval actions. Depends on: T-001. Classification: SAFE_INCREMENTAL.
- [ ] T-102 — Add request-size preflight, media content validation, upload authorization/retention policy, and upload tests. Depends on: T-101. Classification: SAFE_INCREMENTAL.
- [ ] T-103 — Hash password-reset tokens; establish non-debug reset delivery behavior and avoid sensitive logging. Depends on: T-101. Classification: SAFE_INCREMENTAL.
- [ ] T-104 — Define ownership and authorization rules for network, suggestions, endorsements, and conversations; introduce a migration plan before code changes. Depends on: T-101. Classification: MAJOR_REVIEW.
- [ ] T-105 — Ensure only approved/live listings produce student-visible opportunities; cover lifecycle with tests. Depends on: T-101. Classification: SAFE_INCREMENTAL.
- [ ] T-106 — Correct business/admin analytics scope and document metric semantics. Depends on: T-101. Classification: SAFE_INCREMENTAL.

## P2

- [ ] T-201 — Add reversible schema migration tooling and explicit indexes/constraints appropriate to verified access patterns. Depends on: T-104 data design. Classification: MAJOR_REVIEW.
- [ ] T-202 — Add stable API contract documentation and request/response tests before route extraction. Depends on: T-101. Classification: SAFE_INCREMENTAL.
- [ ] T-203 — Incrementally extract Flask blueprints/services around identity, workflows, media, and analytics. Depends on: T-101, T-202. Classification: SAFE_INCREMENTAL.
- [ ] T-204 — Improve web accessibility, responsive behavior, error handling, CSP/security headers, and client tests without replacing the static frontend. Depends on: T-003, T-202. Classification: SAFE_INCREMENTAL.
- [ ] T-205 — Implement native Expo workflows in priority order while WebView stays available. Depends on: T-004, T-202. Classification: SAFE_INCREMENTAL.

## P3

- [ ] T-301 — Evaluate a proven incremental web migration path; do not replace the existing frontend until parity evidence exists. Depends on: T-202, T-204. Classification: MAJOR_REVIEW.
- [ ] T-302 — Evaluate PostgreSQL, backup/restore, migration/rollback, and operations. Depends on: T-201 and documented data ownership. Classification: HUMAN_APPROVAL_REQUIRED.
- [ ] T-303 — Consider backend replacement only with a human-approved architecture decision and migration plan. Depends on: Phase 2/3 evidence. Classification: HUMAN_APPROVAL_REQUIRED.
- [ ] T-304 — Consider a fundamental authentication change only with human approval, threat model, migration, and rollback. Depends on: P0 completion. Classification: HUMAN_APPROVAL_REQUIRED.
