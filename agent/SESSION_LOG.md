# Session log

## 2026-10-09 — PR #26 review repair

The user requested repair and reverification of PR #26 after the two-PR review. Reused the existing review checkout and selected `manual/native-api-timeout` at `daf0e182b012e4cbdb99481c1c17084c116182b9`; preserved prior untracked review evidence. Fetched current master `e126d7de9277a20fc9f7d92a62125ab684ad7121`, which now includes merged analytics PR #31. No rebase, history rewrite or PR merge is part of this repair.

Added eight maintained cases; five reproduced the original early timer cleanup/false-success defect before the repair, including real fetch with stalled 200/503 response bodies. Moved JSON consumption into the deadline-protected try/finally, propagated aborted JSON reading to timeout classification and rejected late successful bodies after abort. Completed malformed JSON and HTTP error status/body/message remain compatible. Updated mobile behavior, state and testing records. Tests use a disposable localhost server; no application database is required or accessed.

The original PR head's full mobile suite, lint, TypeScript and syntax checks pass after repair; current-master integration is verified separately in TEST_RESULTS. Prepare the repaired existing PR for human review and leave it unmerged. Native device/session/lifecycle verification and the existing social release gates remain outstanding.

## 2026-09-29 — PR #21 review findings

- Read the review and reproduced the same-direction `expectedVersion:0` retry and desired endorsement retry conflicts with new regressions. Corrected no-op retry ordering while retaining missing/stale precondition checks; limited the normal endorsement read projection to the actor's direction.
- Updated stale T-201/Issue #18 status in TASKS, STATE and DATA_MODEL. Added focused, concurrent request, active/revoked endorsement and bilateral projection checks. Full-suite validation exposed a reused test-file/WAL isolation failure; the fixture now uses one migration-created path and engine per test. Migration history, the real instance database and existing routes/clients/sockets/analytics remain untouched. Validation evidence is in TEST_RESULTS; PR remains review-only.

## 2026-09-28 — repository cleanup

Inspected current `master` after the T-107 design approval and additive owned-social migration. Added a navigation index for engineering records, corrected repository and mobile setup documentation, removed the unused Expo reset-project command, replaced the starter Explore content with a Forge About screen at the same route, tightened generated-file ignores, and supplied CSS module declarations for TypeScript. Preserved backend runtime, schema, and mobile workflows. Backend and mobile checks are recorded in TEST_RESULTS.md; social ownership/safety implementation remains outstanding.

## 2026-09-18 — IMPLEMENTATION_1 T-003: authenticated API CSRF/origin protection

- Inspected current agent records, Flask signed-session authentication, unsafe API routes, central frontend helper/direct video upload, and isolated test harness in the existing host checkout. T-002 was already committed at `32b9790`; only the mobile and sandbox edits were pre-existing.
- Added session-bound `secrets.token_urlsafe(32)` CSRF tokens, constant-time comparison, and a before-request guard for authenticated unsafe `/api/` requests. Origin takes precedence over Referer; missing/foreign/malformed origins fail closed against direct scheme/Host. No ProxyFix or forwarded-header trust.
- Added authenticated `GET /api/auth/csrf-token` (`csrfToken`, no-store). Rotate on register/login/demo-login, clear on logout/invalid-session cleanup; preserve anonymous authentication/reset flows and existing authentication architecture.
- Updated central API and multipart video fetch token headers; retain browser multipart Content-Type. Centralized client identity changes, cleared token caches, deduplicated acquisition, rejected stale token responses, and made failed logout visible without pretending success.
- Added `tests/test_csrf_security.py`, `tests/test_csrf_frontend.py`, and `tests/csrf_frontend.cjs`. Corrected initial DELETE test setup to use an admin for the existing admin-only route; corrected added backend line endings without whole-file normalization.
- Full host-venv verification: **56 passed, 179 warnings in 10.49s**; warnings are existing datetime.utcnow()/SQLAlchemy Query.get() deprecations exercised by wider coverage. Node frontend regressions ran without skips; no live browser/mobile/proxy test claimed. `git diff --check` passed.
- Updated STATE, TASKS, SECURITY, TEST_RESULTS, and SESSION_LOG only after tests passed. T-003 complete; T-004 mobile HTTPS/navigation allowlisting is next P0. Security records also reconcile stale T-001 fallback-secret/cookie statements against passing implementation evidence.
- Modified this session: `forge_backend.py`, `static/forge_demo.html`, the three new test files, and the five named agent records. Baseline hashes confirm `mobile/src/app/index.tsx` and `sandbox/Dockerfile` remain byte-for-byte unchanged. No staging or commit performed.

## 2026-09-18 — T-002 completion record synchronization

- Updated only STATE, TASKS, SECURITY, TEST_RESULTS, and SESSION_LOG to reflect completed T-002, using the verified host terminal output and current implementation.
- Socket.IO rejects anonymous/suspended connections and derives user/role rooms exclusively from authenticated Flask session identity, ignoring client-supplied `userId`/`role` claims.
- Wildcard `cors_allowed_origins` removed for default same-origin checking; static frontend emits `join` without identity claims.
- `tests/test_socket_security.py` added; verified original host suite: 15 passed in 1.86s with 17 non-blocking deprecation warnings (`datetime.utcnow()` and SQLAlchemy `Query.get()`).
- Confirmed `.venv-host/` is ignored locally via `.gitignore`. T-003 CSRF/origin protection is next P0.
- Pre-existing mobile and sandbox changes must remain untouched; no commit made. Existing backend diff includes line-ending normalization from the earlier implementation, which this documentation task does not alter.

Verification: fresh `.venv-host/bin/python -m pytest -q` passed (15 passed, 17 warnings in 2.19s) after approved filesystem access for the temporary test database. `git diff --check` passed and the documentation diff was reviewed. Baseline hashes confirm only the five intended agent records changed, including byte-for-byte preservation of `mobile/src/app/index.tsx` and `sandbox/Dockerfile`. No commit created.

## 2026-09-17 — IMPLEMENTATION_1 T-001: session configuration and isolated test harness

Scope: completed the highest-priority approved safe-incremental task only; no commit created.

Changes and evidence:

- Replaced the predictable `dev-secret-change-me` fallback with `build_app_config()`. Production (`FORGE_ENV=production`) now fails startup when `FORGE_SECRET_KEY` is absent, one of the historical/default values, or shorter than 32 characters. Development/test falls back only to a process-local random secret.
- Added explicit Flask session cookie settings: `HttpOnly`, `SameSite=Lax`, and `Secure` in production.
- Added `FORGE_DATABASE_URI` configuration support and a `pytest` harness that uses temporary workspace-local SQLite files, creates/drops schema per test, and does not touch `instance/forge.db`.
- Added nine configuration/isolation regressions, including a subprocess startup failure check. Full suite result: 9 passed in 1.52s using a project-local virtual environment.
- Reviewed scope: no Flask, SQLite, frontend, mobile architecture, database technology, or authentication-model replacement. T-002 is next. Pre-existing `mobile/src/app/index.tsx` modification was preserved.

## 2026-09-17 — discovery record synchronization

Scope: documentation only. Inspected the Forge implementation, prototype web client, Expo/WebView wrapper, dependencies, Git status, durable records, route/model declarations, and security-relevant configuration. No application source, mobile source, database contents, or Git history was modified; no commit was created.

Findings recorded:

- Current system is Flask + Flask-SQLAlchemy/SQLite + Flask-SocketIO + static HTML/JS, with an Expo WebView wrapper.
- Role, approval, profile, content, notification, analytics, upload, and optional SMTP/Anthropic flows were mapped.
- P0 findings: default predictable session secret; unauthenticated Socket.IO room membership with wildcard CORS; arbitrary/insecure mobile WebView origin/transport; and no CSRF protection for cookie-authenticated mutations.
- Migration direction is incremental, test-first stabilization. Flask, current web frontend, and Expo/WebView wrapper remain current; PostgreSQL and fundamental authentication changes require human approval.
- Pre-existing dirty file observed: `mobile/src/app/index.tsx`; preserved unchanged.

Outcome: project state advanced from DISCOVERY to IMPLEMENTATION_1, with P0 containment and regression baseline as the next work.

## 2026-09-18 — T-004 SAFE_INCREMENTAL

Implemented in `/home/pablo/Documents/Programming/04-Projects/forge` at starting HEAD `ea8ffc3`; the stale mirror was not used. Exact HTTPS origins come from build-time configuration with no production default. Missing configuration permits no connection. Persisted URL, Connect/save, initial WebView source and navigation share the pure policy; invalid saved values remain visible in recoverable settings without loading or automatic replacement. Existing mobile error handling is preserved. Popups and subframe navigation are blocked, mixed content is never allowed, Android cleartext is disabled through an Expo manifest plugin, and iOS ATS has no arbitrary-load/local-network exceptions.

Verified: 33 mobile tests; mobile lint, TypeScript, native preview/production config introspection and diff check pass. Isolated Forge suite: 56 passed, 179 existing deprecation warnings in 6.60s. Signed release-device tests remain a release gate (see MOBILE_PLAN.md). No commit or push. T-005 is next P0.

Preservation: Dockerfile hash matches the starting baseline. The static frontend changed concurrently during this session; this task never wrote it and leaves its current contents intact. The pre-existing mobile error handling remains. No existing locked dependency versions changed or entries were removed.

Added missing lint tooling and repaired two small existing lint issues (apostrophe and web hydration). npm reported 14 moderate vulnerabilities, ESLint deprecation and a pending resolver script; no broad upgrades/script approvals. Updated all six requested agent records. Remaining release work is in MOBILE_PLAN.md; T-005 is next P0.

## 2026-09-24 — prepare V2/profile-image commit and push

Reviewed the real current master checkout and preserved all existing V2/profile-image source changes, including backend line-ending normalization. Intended source scope: forge_backend.py, requirements.txt, static/forge_demo.html, tests/conftest.py, tests/test_profile_images.py. Updated state and test evidence. All 69 tests and frontend/backend syntax, CSRF/logout, and whitespace checks passed. User authorized a normal push to origin/master without history rewriting. sandbox/Dockerfile excluded and preserved byte-for-byte (SHA-256 c05ebde6159325507f89fa05b66c620cb6afccf76ada0af5c017d53b6b401f75). Frontend upload/remove controls are absent and remain future work; this checkpoint does not claim they exist. Commit/push outcome is reported in the task response.

## 2026-09-24 — IMPLEMENTATION_1 T-005: debug/demo deployment containment

- Started from pushed master `872eb2ba9bba6816946c8039a77e0dcd1f79171f`; `sandbox/Dockerfile` was the only pre-existing dirty file and remained outside task scope.
- Changed runtime configuration so `FORGE_DEBUG` and `FORGE_DEMO_MODE` default off and may only be enabled in explicit `FORGE_ENV=development`.
- Added strict boolean parsing and validated environment names. Unknown/misspelled environments fail startup. Staging and production/prod use deployment secret requirements and Secure cookies.
- Added the `.env.example` placeholder secret to the rejected deployment-secret set.
- Decoupled `/api/auth/demo-login` from Flask debug. Debug alone now returns 404 from demo login. `seed-demo` and automatic startup demo seeding require explicit demo mode.
- Added configuration/import/CLI/demo-login regressions, including fail-closed environment and placeholder-secret cases.
- Verification after final hardening: focused configuration/CSRF suite **73 passed, 288 warnings in 9.65s**; full isolated Forge suite **93 passed, 377 warnings in 10.60s**; Python compilation, Node frontend CSRF/logout regressions, and `git diff --check` passed.
- Existing datetime/SQLAlchemy deprecation warnings remain out of scope. No architecture, authentication model, schema, frontend framework, or deployment platform replacement was introduced.
- T-005 completes roadmap P0 T-001 through T-005. T-101 regression coverage is next. `sandbox/Dockerfile` remains unrelated, modified, uncommitted, and excluded.

## 2026-09-24 — IMPLEMENTATION_1 T-101: authentication/authorization regression baseline

- Began from pushed T-005 master `2321515decc63ece7bd71ae2805dbcf3b7263a18`; unrelated `sandbox/Dockerfile` remained outside task scope.
- Added `tests/test_authz_regressions.py` only; no production application behavior changed.
- Covered registration/login, role gates, notification ownership, profile visibility, business/admin approval, listing approval, and alumni-verification approval behavior.
- First run: 22 passed / 3 failed because the new notification fixtures guessed `kind`; model inspection confirmed `Notification.type`. Corrected the tests only.
- Final dedicated suite: **25 passed, 133 warnings in 5.94s**.
- Full isolated Forge suite: **118 passed, 510 warnings in 15.04s**. Frontend CSRF/logout regressions, Python compilation, and `git diff --check` passed.
- T-101 complete; T-102 upload-boundary hardening is next.
- `sandbox/Dockerfile` remains modified, unrelated, uncommitted, and excluded.
# 2026-09-24 — Autonomous runtime MVP

- Added deterministic local `scripts/forge-auto` orchestration tooling, focused unit tests, governance/model-routing documentation, and decision D-008. It preserves pre-existing dirty product-task paths and does not run autonomous product work.

## 2026-09-24 — IMPLEMENTATION_1 T-102: upload boundary hardening

- Added configurable isolated upload storage, global request-size protection, route-level Content-Length preflight, and bounded streamed video writes capped at 50 MiB.
- Added supported-container signature-family validation for ISO-BMFF, EBML, and AVI instead of relying only on filename extensions.
- Changed ffmpeg handling to fail closed when processing is available but fails. When ffmpeg is absent, signature-validated originals are retained with placeholder thumbnails.
- `/uploads/<path:name>` now requires authentication, serves only media referenced by active non-removed posts, applies role-feed authorization to non-admin users, and retains admin moderation access.
- Soft removal immediately revokes media access. Physical bytes are deliberately retained because an irreversible deletion/retention lifecycle requires separate approval.
- Added isolated upload storage to the test fixture and 10 focused upload-security regressions.
- Final verification: dedicated suite **10 passed, 58 warnings in 3.93s**; full Forge suite **139 passed, 568 warnings in 17.05s**; Python compilation and `git diff --check` passed.
- Container-signature checking is not malware/deep media scanning; that limitation remains documented.
- T-102 complete; T-103 is next. `sandbox/Dockerfile` remains separate autonomous-agent infrastructure work and is excluded from this task.

## 2026-09-24 — IMPLEMENTATION_1 T-103: password-reset token hardening

- Stored password-reset tokens as SHA-256 digests; reset redemption hashes the supplied token before lookup and continues to clear the digest after use.
- Kept the plaintext development token limited to explicit Flask debug behavior, which existing T-005 configuration prohibits outside local development.
- Removed email fallback/failure logging of recipients, subjects, bodies, exception details, and therefore reset URLs/tokens. Non-debug without SMTP intentionally cannot deliver reset email but returns the existing generic anti-enumeration response.
- Added reset-token digest, redemption, non-debug response, and sensitive-log regressions; updated the existing anonymous CSRF reset test to retrieve the debug token from its intended response rather than the database.
- Verification: focused suite **44 passed, 56 warnings in 7.83s**; full suite **144 passed, 162 warnings in 22.39s**; backend compilation and `git diff --check` passed.

- 2026-09-24 11:07 UTC: autonomous T-105 completed after reviewer PASS; artifacts `.forge-agent/runs/20260924T110515Z-T-105`; checks: git diff --check => 0; /home/pablo/Documents/Programming/04-Projects/forge/.venv-host/bin/python -m py_compile forge_backend.py tests/test_authz_regressions.py => 0; /home/pablo/Documents/Programming/04-Projects/forge/.venv-host/bin/python -m pytest -q => 0.

- 2026-09-24 14:11 UTC: autonomous T-106 completed after reviewer PASS; artifacts `.forge-agent/runs/20260924T140842Z-T-106`; checks: git diff --check => 0; /home/pablo/Documents/Programming/04-Projects/forge/.venv-host/bin/python -m py_compile forge_backend.py tests/test_authz_regressions.py => 0; /home/pablo/Documents/Programming/04-Projects/forge/.venv-host/bin/python -m pytest -q => 0.

- 2026-09-24 14:44 UTC: autonomous T-202 completed after reviewer PASS; artifacts `.forge-agent/runs/20260924T141111Z-T-202`; checks: git diff --check => 0; /home/pablo/Documents/Programming/04-Projects/forge/.venv-host/bin/python -m py_compile tests/test_api_contract.py => 0; /home/pablo/Documents/Programming/04-Projects/forge/.venv-host/bin/python -m pytest -q => 0.

## 2026-09-24 — T-203 / GitHub Issue #1

- Read Issue #1, AGENTS.md, and all eight issue-required records before source edits. Checked out the existing branch `codex/t-203-backend-extraction` at `e03c0a3` into the initially empty working environment; it matched master.
- Selected notifications/onboarding because their operations are cohesive and need only the existing login guard, database, model, and step mapping. Added and verified 30 behavior cases against the monolith before extraction; preserved all existing tests.
- Extracted six handlers into two blueprint factories without changing their operations. Reviewed original-vs-extracted ASTs: all 129 original class/function definitions are preserved after normalizing only the six moved handlers' blueprint/dependency identifiers.
- Documented factory wiring, internal endpoint namespaces, security invariants, and remaining extraction boundaries. No schema migration, authentication/CSRF redesign, ownership repair, or retention change was attempted.
- Full-suite and diff-check evidence is in TEST_RESULTS.md. Changes are prepared for a review PR to master; do not merge automatically.

## 2026-09-24 — T-203 / GitHub Issue #3

- Read the issue, comments (none), AGENTS.md, required records, existing handlers, and relevant tests. Retrieved Forge into the supplied empty workspace and checked out the existing `codex/t-203-profile-extraction` branch at `5dafe2a` (merged PR #2).
- Committed 50 new profile cases plus expanded direct-script registration coverage before production edits. Original handlers passed the full 256-test suite.
- Moved only the five required profile handlers into an explicitly injected blueprint. Kept image routes and shared helpers in place; documented D-010 and remaining T-203 boundaries.
- Reviewed source diff and compared all original top-level definitions, URL rules, and schema metadata. Full suite after extraction: 256 passed; evidence and limitations are in TEST_RESULTS.md.
- Preparing a PR to `master` for human review. No merge, auto-merge, schema/ownership/retention change, or client work is included.

## 2026-09-24 — GitHub Issue #6

- Inspected required web/API/security records and reused the existing export location instead of adding duplicate actions. Kept implementation within the static client and its tests.
- Added all-role rendering and behavioral export regressions using the existing Node/pytest style; a focused test caught and corrected an expired-session message being overwritten by the account-change guard.
- Full suite and focused web/security checks pass; details and verification limits are in TEST_RESULTS.md. Prepared a review PR to `master`; no merge or auto-merge.

## 2026-09-26 — Issue #5 analytics extraction

- Read Issue #5, required architecture/API/security/decision/task/test records, and existing T-106 coverage. Started from clean `master` at `2193553`; created the requested `codex/t-203-analytics-extraction` branch.
- Committed the regression baseline separately before moving production code: 28 new analytics cases plus expanded direct-script startup coverage; full suite 285 passed.
- Extracted only the three analytics handlers into an explicitly injected blueprint. Preserved all metrics, response shapes/order, role/owner scope, and activity-update transaction behavior. Shared helpers and all unrelated routes/models/clients remain unchanged.
- Full post-extraction suite 285 passed; 66 URL rules/23 table definitions and indexes match the base; normalized AST comparison preserves all 118 original definitions; diff check passes.
- Updated durable records and prepared a second reviewable extraction/documentation commit for a PR to `master`. No merge. Identity, remaining workflows, image/media, and public-profile extraction keep T-203 open.

## 2026-09-26 — T-104 / GitHub Issue #9 ownership design

- Read Issue #9, AGENTS.md and all required architecture/roadmap/task/decision/security/API/data/mobile/web/issue/test/state/session records. Checked out the existing clean `codex/t-104-ownership-design` branch at `d4a0516`, the current master baseline.
- Traced all seven social handlers, five legacy models, seed data, Socket.IO rooms/events, notification commit ordering, shared analytics, current web/native/WebView consumers and existing test coverage. Reconciled relevant stale discovery descriptions without changing runtime.
- Prepared `OWNERSHIP_DESIGN.md` and proposed D-012–D-015 covering ownership, authorization, compatibility, data preservation and migration gates. Documented concrete alternatives and human decisions; no unprovable legacy ownership, automatic deletion, admin private-data bypass or authentication change approved.
- T-104 remains open pending architecture review; implementation, T-201 migrations and native messaging remain gated. Only `agent/*.md` changes are intended. Full-suite and diff verification are recorded in TEST_RESULTS.md. Preparing a PR to master for review only; no merge.

## 2026-09-28 — ownership approval and safety requirement

- Recorded the user's explicit approval of D-012–D-015 as proposed, plus the requirement for blocking/reporting before social networking is production-complete.
- Verified PR #10 was already merged and started a documentation follow-up from clean master `7327929` on `codex/t-104-approval-safety-gate`.
- Marked T-104 design/review complete without claiming runtime completion; retained migration/retention gates and added D-016 / open T-107 with enforcement, reporting privacy, moderation, client and test acceptance requirements. Reconciled historical pending-approval statements in canonical records.
- No production code, schema, database, API or client changes. Validation recorded in TEST_RESULTS.md. Follow-up PR targets master; do not merge.

## 2026-09-28 — T-201 migration foundation

Started T-201 after approval of D-012–D-015. Added a conservative SQLite migration foundation: frozen current-schema manifest, explicit migration ledger/baseline command, status/verification commands, and consistent backup support. No ownership schema, FK enforcement, automatic migrations, or persistent database mutation was performed. Validation: 5 focused migration tests and 290 full-suite tests passed; diff check clean.

## 2026-09-28 — T-201 owned-social migration revision

Built and reviewed the second T-201 increment:
`20260928_02_owned_social_schema`. Added ordered revision handling,
checksum-protected manifests, explicit atomic SQLite DDL transactions,
guarded upgrade/downgrade commands, six approved owned-social tables,
constraints/indexes/triggers, and regression coverage.

A manual staged-diff review identified Python sqlite3 legacy DDL transaction
behavior as a rollback risk; the migration engine was corrected to use explicit
`BEGIN IMMEDIATE`, with injected failure tests for baseline, upgrade and
downgrade atomicity.

Validation finished at 13 focused migration tests and 298 full-suite tests.
Copy-only rehearsal proved reversible empty migration, refusal to discard owned
data and exact source-database non-mutation. No real database baseline/upgrade
was performed. Next prerequisite before ORM ownership models is removing or
guarding historical `db.create_all()` bootstrap behavior so migrations remain
the sole owner of revision-02 schema creation.

## 2026-09-28 — Issue #16 migration-managed bootstrap

- Read Issue #16, required agent records, AGENTS, migration engine/manifests/revision, startup/configuration/fixture tests and root/mobile startup guidance. Started the dedicated branch from master `dac4ef86e0736dd56013822ce68f118791c6c757`.
- Replaced ORM bootstrap with frozen-baseline/ordered-revision initialization and read-only persistent startup verification. Added explicit new-file CLI initialization; preserved confirmation, recovery-command access, demo gates and engine-local application pragmas without global FK changes.
- Added fresh-schema/constraint, refusal/non-mutation, checksum/physical-tamper, server-entrypoint, CLI/demo and interruption regressions. Updated fixtures to migration HEAD; removed their metadata-only baseline dependency.
- Validation is in TEST_RESULTS. All tests use isolated databases; no real instance/forge.db access, migration, baseline or seed occurred. No social ORM/API/client work or historical migration changes. T-201 remains open; PR is for review only, no merge.
## 2026-09-28 — Issue #19 browser quality coverage

- Started a dedicated branch from current master. Added optional Playwright/Chromium regression tests for the existing static web client, a disposable migrated local server, ignored failure screenshots, and usage guidance.
- Browser checks cover login, roles, focus/keyboard cards, form labels, loading/retry, offline recovery, pending mutation dedup, user text escaping, responsive widths, reduced motion and served CSP/security headers. Existing production code and migration history are untouched.
- Focused/full validation and database isolation evidence are recorded in TEST_RESULTS. Review PR only; no merge.

## 2026-09-29 — Issue #22 route/contract increment

Started a dedicated branch from master `88b80641b3d35d21af295ff15818c384996691b2` after reading the referenced design, API, security, state, model and test records. Implemented fail-closed process-wide legacy/maintenance/v2 selection, a focused owned-social HTTP dispatcher, signed user/conversation-scoped cursors, bounded projections, retry status metadata and the wrong-endpoint 403 service distinction. No legacy row import, dual write or delivery. Focused owned-social/migration/bootstrap validation: 77 passed, 92 warnings. Browser-enabled full suite, final diff check and PR status are recorded with the final verification. Web/WebView, socket/notification delivery, shared student analytics, persistent rollout/FK/admin-removal review and T-107 remain outstanding.

Final validation: full browser-enabled pytest **370 passed, 1486 warnings**, no skips; `git diff --check` passed. Prepared as a review PR, not merged.

## 2026-09-29 — T-201 ownership-v2 web/WebView client

Started from clean current master `dcea0d9a4dc1570f40c2a0f903411c547e62274c` (merged PR #23), on dedicated `codex/ownership-v2-web-client`. Read required agent records, the shared static product, legacy handlers, owned HTTP/service modules and existing Node/Chromium/pytest harnesses. Added a public no-store projection of the already-captured process mode because legacy toggle/read/send semantics are not safely interchangeable with v2. No new configuration subsystem or authorization semantics.

Implemented owned networking, per-section/list/history paging, real-peer create/reuse, version/desired-state mutations, stable message retries, visible-message reads, generic read-only/errors and account-generation protection in the existing static document. Added executable Node cases, real Chromium owned flows and subprocess configuration checks. Existing tests are preserved. Validation commands/counts are recorded in TEST_RESULTS; initial browser test waits were corrected to observe completed rows/history instead of transient busy-label changes.

All test databases were disposable and migration-managed. The real `instance/forge.db` was never opened, copied, upgraded or modified, and migration history was unchanged. Production remains legacy by default; no v2 enablement, native social work, delivery, analytics, T-107 or persistent rollout/FK/admin-removal work occurred. Preparing a review PR to master; no merge.


## 2026-09-29 — PR #24 contiguous read-cursor review fix

Started from PR head `8006aa01f65d307a068555eed16009eb7087440f` on the existing `codex/ownership-v2-web-client` branch and read its posted merge-blocker. Reproduced five failures in the expanded Node suite before the fix. Replaced maximum-visible advancement with a per-thread observed-sequence set and a contiguous scan from the confirmed cursor; loaded own messages are non-blocking, unknown/unobserved incoming gaps block, and submitted cursors are deduplicated while one read is in flight. History refresh/pagination preserve observations, and stale-account/hidden-tab checks remain enforced. No backend contract, default legacy mode, migration, native source or real database access changed.

Chromium now exercises only sequence 3 initially visible, then sequence 1, then sequence 2, asserting POST cursors `[1, 3]`; the existing real-server test requires loading earlier history before read advancement. The new browser fixture initially exposed a few pixels of message 2 due to thread padding; removing padding from the test-only controlled viewport corrected the fixture without relaxing assertions or product CSS. Exact final validation is in TEST_RESULTS. Update the existing PR only; do not merge.

## 2026-10-09 — T-201 delivery / Issue #28

Fetched/pulled clean master `876819abd0505b1964c21aa2a68e12ccf676ab27`, verified merged blocking PR #27 and read unrelated open PR #26 without applying it. Created Issue #28 and `codex/t201-social-delivery` in the current checkout; no stash/worktree/rebase/merge. Read the required records, current service/HTTP/socket/notification/client and regression harnesses. Implemented approved delivery increment in the existing service with transaction-local intents, same-transaction Notification inserts, post-commit reauthorization/enqueue, generic wording, user-room isolation, permanent unread hint suppression and shared list/count/export projection. Added narrow moderation retirement through the existing Socket.IO room manager; no new session registry or cookie revocation.

Tests cover A/B/C/admin/device isolation and forged claims, durable request/accept/message semantics, same-key/concurrent retries, notification/commit rollback, post-commit emission failure/log minimization, block-before and commit-before-block ordering on independent connections, suspension/deletion/membership ineligibility, reservation serialization, rollback of suppression, retained history/read, and client HTTP refresh/late-generation rejection. Updated the obsolete deferred-notification assertion to three required generic rows while keeping legacy helpers forbidden. Historical documents remain; current summaries now identify merged blocking and separate reporting gates.

The server restarted during dependency setup; verified branch/files before resuming. Existing venvs lacked pytest/pip, so installed unchanged requirements in ignored project-local `.venv-delivery`; Chromium lives in ignored `.playwright-delivery`. Playwright 1.55 uses its supported Ubuntu 24.04 fallback on this newer host. Git metadata writes, network package/browser downloads, mobile Expo subprocesses and localhost/Chromium required explicit sandbox escalations. Failed sandbox attempts are recorded in TEST_RESULTS; no test was weakened or skipped to avoid them.

Only disposable migration-managed databases were used. The real `instance/forge.db` was never opened, enumerated, copied, hashed, migrated, seeded or modified. No migration/schema/native source/default mode/production v2/PR #26 changes. Preparing coherent commits and an unmerged review PR to master; broader T-201 and T-107 remain open. Final validation is in TEST_RESULTS.

## 2026-10-09 — PR #29 review repair

The user requested fixes for four review findings on head `0e9f1a865373ca5119cdde0aa2ff49f71d9a0cd8`. Reused the existing isolated review checkout because the original local checkout contains unrelated changes; fetched and selected `codex/t201-social-delivery`, with master still `876819abd0505b1964c21aa2a68e12ccf676ab27`. No new checkout, stash, merge, rebase or framework change was needed.

Preserved same-thread composer input/focus/selection immediately before automatic repaint, including edits made during the HTTP refresh. CSRF generation resets now retire sockets; an actual current CSRF rejection attempts a replacement while preserving the failed action's error and no-replay behavior. The notification handler can consume maintenance configuration while social operations remain gated. Owned message notification links select their intended thread and reauthorize over HTTP; malformed hints and late account-switch navigation are rejected. No backend, schema, native source or social-default changes were necessary.

Promoted the review reproductions into maintained Node and Chromium regressions, adding mobile-width/in-flight typing, thread scoping, fresh socket versus retired-handler behavior, maintenance notifications, prior-thread navigation and unavailable-history checks. The original assertions were preserved. All execution uses disposable migration-managed databases; the real `instance/forge.db` remains untouched. Validation commands/results are recorded in TEST_RESULTS. Update existing PR #29 and leave it unmerged; T-201/T-107 release gates and PR #26 stay separate.

## 2026-10-09 — PR #29 multipart recovery repair

The user requested a fix for the re-review's remaining P2 finding at verified PR head `d73b6938a0ab12c8105026da8c36d8b57f07d47e`. Reused `review-t201` on `codex/t201-social-delivery`; remote master remains `876819abd0505b1964c21aa2a68e12ccf676ab27`. No new checkout or architectural change was needed.

Extracted the existing JSON-request security invalidation into a shared generation-checked helper and applied it to video uploads. Same-account CSRF failures replace realtime without replay; current 401s expire the session; stale token, HTTP and error-body completions cannot mutate another account or repaint its view. Maintained multipart tests cover legacy/v2 recovery, retired handlers, one upload attempt, token/upload 401s, stale success/error/body parsing and switching during token acquisition. Chromium invokes the actual upload and realtime handlers with real authorized HTTP and the established offline transport stub. Temporary review reproducers were promoted into maintained coverage and removed; existing assertions remain intact.

Validation evidence is recorded in TEST_RESULTS. Only disposable migration-managed fixtures were used. No real `instance/forge.db`, original checkout changes, PR #26, native source, backend delivery semantics, schema/migration, default mode or production enablement changes. Prepare and push a coherent repair to existing PR #29, leaving it unmerged; broader T-201/T-107 and signed-device release work remains open.

## 2026-10-09 — T-201 student analytics isolation / Issue #30

Fetched origin, pulled clean master at `3686256c561c36cbc2b7d07864d29d33b7b6999e`, verified merged PR #29 and inspected open PRs/issues. Only unrelated PR #26 was open; no dedicated analytics issue existed. Created Issue #30 and `codex/t201-student-analytics-isolation` in the current checkout, without stash, worktree, old branch, rebase or merge. Read required canonical records and current analytics/owned/mode/auth/client/test evidence.

Reproduced the global legacy connection metric and missing maintenance boundary with focused regressions before the production fix. Added a pure owned-service acceptance-date projection plus explicit fixed-mode/provider injection into the existing analytics blueprint. Preserved legacy counts/series and all unrelated T-106 metrics, business/admin handlers and active-role access. V2 uses only own currently accepted endpoint edges and acceptance dates; maintenance stops after auth. Missing acceptance time fails closed. No migration/schema or client production edit was needed.

Added A/B/C/admin, all states, block/unblock, acceptance-window, empty graph/no fallback, spoofing, SQL tracing, unknown-mode startup, optional web analytics, account-generation and real Chromium mobile/keyboard regressions. Existing expectations remain intact. Full suite **442 passed, no skips**; mobile **53**, lint/TypeScript, Node **5 + 82**, compile/diff and AST preservation passed. TEST_RESULTS records exact commands, subprocess counts, inspected SQL and sandbox permission reruns.

Updated current records and appended evidence while preserving dated PR #29 review history. T-201 remains open for whole-schema FK/admin-removal, persistent rollout/recovery and production cutover; T-107 remains open for reporting/reviewers/deferred policy. No production v2, default legacy, native source, PR #26 or real `instance/forge.db` access/change. Implementation/tests committed as `81fdfe3`; documentation follows for a PR to master for human review, without merge.

## 2026-10-09 — T-201 whole-schema FK/admin review / Issue #32

Fetched origin, selected/pulled clean master `825e7e5d8392506f1496dd5db3cd8a54ccf24042`; inspected open PRs/issues (no exact issue/no open PR), created Issue #32 and `codex/t201-fk-admin-removal-review` in this checkout. No stash/worktree/history rewrite. Read required project decisions/records, physical migration authority, models/hooks, admin/socket/storage paths and regression harnesses. All experiments used new workspace-local migrated disposable databases; the real instance/forge.db was never accessed/enumerated/copied/hashed/migrated/modified.

Reproduced old admin deletion orphaning identity references and the stale-writer race after a BEGIN IMMEDIATE hard delete. Implemented the authorized fail-closed suspension for referenced and clean users, physical schema introspection, under-lock admin reauthorization, explicit physical rollback after failed SQLAlchemy commit, generic failures and all-mode target socket retirement. No child writes, nullable clearing, guessed owners, report/reviewer work, frozen migrations or global FK enablement. Preserved legacy default and disabled production v2.

Generated FK_ADMIN_REVIEW from actual migrated schema and matched every FK to its revision manifest. Added all-42 OFF/ON parent behavior, exact 28 user-binding removal/preservation, orphan checks/startup refusal, per-connection/transaction pragma, ORM SQL/final-state, seed, upgrade/downgrade/restore, both removal race orders, failure/reauthorization/auth/CSRF/device/unsuspend regressions. Initial fixtures exposed a missing required alumni document field and incomplete block event sequence; corrected fixture data without weakening production checks. Commit-failure injection found logical rollback insufficient and led to physical DBAPI cleanup. Socket tests exposed prior v2-only retirement and led to the bounded all-mode fix. Tests/results and sandbox reruns are recorded in TEST_RESULTS. Preparing coherent commits and an unmerged PR to master; T-201/T-107 remaining gates stay open.

Final release verification: 142 new cases, 427 broad focused cases, 584 full cases including all 25 Chromium, 5 + 82 Node, 64 mobile, lint/TypeScript, 56-file compile, AST/generated-evidence/diff checks pass; no automated skips. Sandbox Chromium/mobile denials were rerun with required permission. The complete checklist and device/operator limitations are in TEST_RESULTS.
