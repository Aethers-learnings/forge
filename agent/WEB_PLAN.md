# Web plan

Status: proposed incremental migration and quality plan.

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
