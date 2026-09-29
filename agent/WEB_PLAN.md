# Web plan

Status: proposed incremental migration and quality plan.

## Browser regression harness (Issue #19)

Install `pip install -r requirements-browser.txt` and `python -m playwright install chromium`, then run `pytest tests/test_browser_web_quality.py`. Tests start a local Flask server with a freshly migrated, seeded database in a temporary test directory. Chromium exercises auth, roles, keyboard and label semantics, delayed/retry/offline behavior, mutation deduplication, escaping, desktop/mobile widths, reduced motion and real response CSP/security headers. Third-party font and socket CDN requests are blocked in the browser context to avoid external network dependence; production CSP is unchanged. Screenshots are written to ignored `test-results/` only on failure. The browser dependency is optional for the ordinary Python suite (browser tests skip if Playwright is absent); install it to run browser coverage.

## Verified baseline

`static/forge_demo.html` is a single static document served by Flask. It contains the application UI, styles, client state, rendering functions, `fetch` API client, Socket.IO client, auth forms, role-specific navigation, dashboards, and direct DOM updates. It uses an `esc()` helper for rendered values, but relies on `innerHTML` composition. PWA assets are served through Flask. No separate frontend build/test tooling was found.

## Plan

1. P0: integrate CSRF/origin policy, harden Socket.IO origin/identity behavior, and establish security-header/CSP compatibility tests. Classification: SAFE_INCREMENTAL.
2. Add browser-level regression tests for auth, role navigation, escaping, forms, uploads, and permission/error states. Classification: SAFE_INCREMENTAL.
3. Improve the existing static client incrementally: accessible semantics and focus management, responsive/touch layouts, loading/offline/retry states, and reduced-motion/keyboard support. Classification: SAFE_INCREMENTAL.
4. Extract API client/state/rendering seams only once tests lock behavior; publish a stable API contract. Classification: SAFE_INCREMENTAL.
5. Prove a route-by-route migration path before changing frontend framework or removing the current client. Classification: MAJOR_REVIEW.

The current web frontend remains until an incremental migration path is proven. It must not be replaced simply because it is monolithic.

## T-104 contract dependency (2026-09-26)

[OWNERSHIP_DESIGN](OWNERSHIP_DESIGN.md) traces the existing network/message renderers and proposes required capability/precondition handling, desired-state endorsements, real-peer thread creation, pagination, explicit read cursors and send retry keys. These are deliberate future contract changes requiring D-014 approval and coordinated cutover; no static-client behavior changes in Issue #9. WebView runs the same client and must be tested with cached old pages; do not replay legacy numeric IDs into the new graph.

## Ownership approval and production gate (2026-09-28)

This update supersedes the earlier statements that D-012–D-015 await approval: the user approved all four decisions as proposed. Their target remains unimplemented; current schema, API, authentication and client behavior are unchanged. T-104 design/review is complete and T-201's design dependency is satisfied, with migration/integrity/recovery verification still required. Social networking is **not production-complete** until blocking/reporting is designed, implemented and tested under D-016 / T-107 and [OWNERSHIP_DESIGN section 8](OWNERSHIP_DESIGN.md#8-blocking-and-reporting-production-completion-gate). This includes server enforcement, private report handling, explicitly authorized audited moderation, web/WebView and released-native coverage, and security/race/rollback tests. No blanket admin private-message access or irreversible retention policy is approved.

## 2026-09-29 — ownership-v2 client compatibility

The existing static document now supports both explicitly selected contracts. Before social loading, it reads `/api/social-config` once per account generation. That endpoint reports the dispatcher's captured process mode with no graph access, user data or secrets. Legacy cannot safely consume v2 desired-state endorsements, pure-read semantics and real-user creation, so an explicit signal is necessary; neither resource shapes nor error responses select a contract. Unknown configuration fails with update guidance, maintenance denies social loading, and errors never trigger downgrade or write replay.

V2 uses 20-row network sections and conversation pages, independent signed cursors, ID deduplication, server counterpart/edge identifiers and versions. Histories use the server's latest-50 window and `before` cursor; sequences merge ascending without duplication. Connections offer real conversation creation/reuse. Messages retain an in-memory retry key and unchanged text across user-triggered transient retries; one in-flight logical send is allowed per thread. A definitive conflict refreshes the thread and requires a new action. No synthetic reply is expected.

IntersectionObserver advances explicit read state only to an actually visible rendered sequence while the page is visible; GET alone never marks read. Read-only histories use generic language and disable sending. Controls retain keyboard, labels, busy/disabled and narrow-screen behavior. No framework replacement or social realtime delivery was added.

CSRF generation also owns social caches/cursors/retries and late-response guards. Logout, login identity/session changes and invalid sessions reset those values; obsolete sockets are disconnected and their queued callbacks ignored. Existing non-social behavior and CSRF/origin policy remain tested. Client state/retry keys are memory-only; page reload discards an unconfirmed submission.

Production remains default legacy and v2 requires separate rollout approval. Socket/notification delivery, student analytics, persistent rollout/FK/admin-removal review, mandatory T-107, native social features and signed-device checks remain deferred.
