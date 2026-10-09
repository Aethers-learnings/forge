# API map

Current implementation (2026-10-09): PR #27 merged directed blocking and PR #29 merged participant-safe delivery. Issue #30 implements student analytics ownership isolation for controlled v2 rehearsal. Legacy remains the default; production v2 is not enabled. T-201 whole-schema FK/admin-removal, persistent rollout/recovery and production cutover gates, plus T-107 reporting/reviewer/policy gates, remain open. Dated entries below preserve their historical scope.

Status: route inventory for the current Flask prototype. All JSON routes return 401 through `require_login()` unless marked public/session-aware. No version prefix exists. Authenticated unsafe `/api/` requests are protected by the session-bound CSRF token plus same-origin Origin/Referer validation added in T-003.

## Auth and session

| Method / path | Access | Verified behavior |
| --- | --- | --- |
| POST `/api/auth/register` | Public | Creates `trade`, `grad`, or `business`; checks student-domain only when an email is supplied; creates a session. |
| POST `/api/admin/provision` | Secret header | Creates admin if `X-Provision-Secret` equals environment secret; otherwise 404. |
| POST `/api/auth/login` | Public | Username/password login; in-memory 5-attempt/300-second per-username throttle; creates session. |
| POST `/api/auth/forgot-password` | Public | Creates a 30-minute SHA-256-digested reset token for a matching username; sends SMTP email if configured; returns plaintext only in explicit local debug mode. |
| POST `/api/auth/reset-password` | Public token | Exchanges a valid token whose digest matches stored state for a password of at least 8 characters. |
| POST `/api/auth/demo-login` | Explicit local demo mode | Selects seeded `demo_<role>` user only when `FORGE_DEMO_MODE=1` with `FORGE_ENV=development`; otherwise 404. Flask debug alone does not enable it. |
| POST `/api/auth/logout` | Session-aware | Removes `user_id` from session. |
| GET `/api/auth/me` | Session-aware | Returns current public user object or `null`; does not call `require_login()`. |

## Feed and media

| Method / path | Access | Verified behavior |
| --- | --- | --- |
| GET `/api/feed` | Logged in | Returns non-removed posts where `feed == current role`, relevance sorted. |
| POST `/api/posts` | Logged in | Creates text post in author’s role feed. |
| POST `/api/posts/:id/like` | Logged in | Toggles caller’s `Like`. |
| POST `/api/posts/:id/comments` | Logged in | Adds comment using caller’s current display name; emits to role room. |
| DELETE `/api/posts/:id` | Admin | Soft-removes the post. |
| POST `/api/posts/:id/flag` | Logged in | Marks post flagged. |
| POST `/api/posts/video` | Trade or grad | Accepts multipart `video` and optional `caption`; extension allowlist, 50 MB post-save check, optional ffmpeg processing. |
| GET `/uploads/:name` | Public | Serves stored upload by path. |

## Discovery, opportunity, event, and pathway

| Method / path | Access | Verified behavior |
| --- | --- | --- |
| GET `/api/opportunities` | Logged in | Returns all opportunities; student reads increment linked listing impressions. |
| POST `/api/opportunities/:id/apply` | Logged in | Toggles caller’s application; notifies opportunity owner when applying. |
| GET `/api/events` | Logged in | Returns all events with caller interest state. |
| POST `/api/admin/events` | Admin | Creates event and notifies matching student programmes. |
| POST `/api/events/:id/interest` | Logged in | Toggles caller interest. |
| GET `/api/pathways` | Logged in | Returns all programme pathways. |

## Business, approval, and alumni workflows

| Method / path | Access | Verified behavior |
| --- | --- | --- |
| GET `/api/business/listings` | Business or admin | Business receives its own listings; admin receives all. |
| POST `/api/business/listings` | Approved business | Creates pending approval queue item and listing. |
| GET `/api/admin/queue` | Admin | Lists every approval item. |
| POST `/api/admin/queue/:id/:action` | Admin | `approve` or `reject`; synchronizes linked listing and creates opportunity on approval. |
| POST `/api/alumni/verify` | Grad | Creates a verification record from `documentRef` and `note`. |
| GET `/api/admin/alumni-verifications` | Admin | Lists every alumni verification. |
| POST `/api/admin/alumni-verifications/:id/:action` | Admin | `approve` sets target user’s `alumni_verified`; `reject` records status. |

## Networking and messaging

| Method / path | Access | Verified behavior |
| --- | --- | --- |
| GET `/api/network` | Logged in | Returns all shared seeded network requests, suggestions, and connections. |
| POST `/api/network/requests/:id/:action` | Logged in | Changes shared request to `accepted` or `ignored`. |
| POST `/api/network/suggested/:id/connect` | Logged in | Changes shared suggestion to pending. |
| POST `/api/network/connections/:id/endorse` | Logged in | Toggles shared endorsement state/count. |
| GET `/api/conversations` | Logged in | Returns every shared conversation and messages. |
| GET `/api/conversations/:slug` | Logged in | Returns shared conversation and marks it read. |
| POST `/api/conversations/:slug/messages` | Logged in | Adds `me` message plus deterministic seeded auto-reply; notifies caller only. |

## Coach, profile, onboarding, notifications

| Method / path | Access | Verified behavior |
| --- | --- | --- |
| GET/POST `/api/coach/chat` | Logged in | Reads caller history / appends caller text and optional Anthropic or fallback reply. |
| POST `/api/profile/cv-upload` | Logged in | Accepts JSON `cvText`, keyword-extracts skills, marks CV uploaded. |
| PATCH `/api/profile/skills` | Trade or grad | Adds/removes a caller skill. |
| PATCH `/api/profile/portfolio` | Logged in | Updates a role-specific allowlist of profile/company fields. |
| PATCH `/api/profile/visibility` | Logged in | Updates caller visibility booleans. |
| GET `/api/profile/export` | Logged in | Downloads caller profile, notifications, coach history, and applications as JSON. |
| GET `/api/onboarding` | Logged in | Returns role walkthrough state. |
| POST `/api/onboarding/advance` | Logged in | Advances current role walkthrough. |
| POST `/api/onboarding/skip` | Logged in | Marks caller walkthrough complete. |
| GET `/api/notifications` | Logged in | Returns caller’s newest 50 notifications and unread count. |
| POST `/api/notifications/:id/read` | Logged in/owner | Marks only caller-owned notification read. |
| POST `/api/notifications/read-all` | Logged in | Marks caller’s unread notifications read. |

## Profiles, search, analytics, administration

| Method / path | Access | Verified behavior |
| --- | --- | --- |
| GET `/api/users/:id` | Logged in | Returns visible profile (or owner/admin); creates profile view/notification for another viewer. |
| POST `/api/users/:id/testimonials` | Logged in | Adds testimonial for another user; no connection requirement. |
| GET `/api/search/candidates?skills=csv` | Business or admin | Searches visible unsuspended students by skill and logs terms. |
| GET `/api/analytics/student` | Any active logged-in role | Returns views, connections, engagement, peer comparison, searched skills. Fixed `legacy`: shared accepted requests + NPCs, request creation series. Fixed `v2`: caller-endpoint accepted owned edges, acceptance-date series only. `maintenance`: authenticated generic 503 before any social graph read. No client-selected mode/identity or legacy fallback. |
| GET `/api/analytics/business` | Business or admin | For a business, returns metrics for opportunities and listings it owns. For an admin, returns the same hiring-funnel metrics platform-wide. `applications` is application-row count; `impressions` is the cumulative count of student opportunity-board reads against linked listings; `rate` is rounded applications ÷ impressions, or `—` when impressions are zero. `profileViews` is views of the business profile for businesses and all recorded profile views for admins. Applicant skills and demographics count application rows (so one applicant applying to multiple opportunities contributes once per application). |
| GET `/api/analytics/admin` | Admin | Returns platform counts, queues, registration series, and content totals. `mau` is users whose `last_seen` is within the trailing 30 days; `pendingApprovals` is pending listing approvals + alumni verifications + unapproved business accounts; registration and content figures are all-time rows, with soft-removed posts excluded from posts/videos and flagged content limited to active posts. |
| GET `/api/admin/users` | Admin | Returns administrative view of all users. |
| POST `/api/admin/users/:id/:action` | Admin | `approve-business`, `suspend`, `unsuspend`, or `remove` (fallback suspension on delete failure). |
| POST `/api/admin/announce` | Admin | Persists/sends an announcement to all or a role audience. |

## Static and realtime

- GET `/` serves `static/forge_demo.html`; GET `/manifest.webmanifest` and GET `/icons/:name` serve PWA assets.
- Socket.IO connections require an active authenticated Flask session. User/role rooms are derived server-side from session identity; client-supplied identity claims are ignored. Server emits `notification`, `new_comment`, `new_message`, `job_match`, and `new_applicant`.

## T-203 implementation locations (2026-09-24)

The three `/api/onboarding*` handlers are now in `forge_routes/onboarding.py`; the three `/api/notifications*` handlers are in `forge_routes/notifications.py`. Their paths/methods and externally visible behavior are unchanged. `require_login` and the application-wide CSRF/origin hook remain in `forge_backend.py`. Notification creation, Socket.IO pushes, account models, and all other routes remain in the entrypoint. The T-202 API contract remains unchanged.

## T-203 profile implementation locations (Issue #3, 2026-09-24)

`POST /api/profile/cv-upload`, `PATCH /api/profile/skills`, `PATCH /api/profile/portfolio`, `PATCH /api/profile/visibility`, and `GET /api/profile/export` now live in `forge_routes/profile.py`. Their existing API contract, status codes, response bodies, and authentication/role rules are unchanged. The earlier location note predates this second increment. Profile image routes and public-profile reads remain in the entrypoint; no upload or serving policy changed.

## 2026-09-26 — Analytics implementation location

`GET /api/analytics/student`, `/api/analytics/business`, and `/api/analytics/admin` are implemented in `forge_routes/analytics.py`, registered by the entrypoint with existing dependencies. The T-106 metric definitions and access rules above remain unchanged, including the student endpoint's existing logged-in-only gate (not a student-role restriction). Public paths, methods, response bodies, status codes, ordering, and empty states are preserved.

## T-104 future ownership mapping (2026-09-26)

The implemented network/conversation paths and response shapes above remain unchanged. [OWNERSHIP_DESIGN sections 1 and 4](OWNERSHIP_DESIGN.md) trace all seven current handlers, web/WebView/native consumers, notifications, Socket.IO and shared analytics, and map them to a proposed secure contract. That mapping includes deliberate precondition/body/status/pagination/read-semantics changes, two new conversation operations, and a proposed capability boundary; it is **not** the current API. D-014 needs human approval before any route/client edits.

## Ownership approval and production gate (2026-09-28)

This update supersedes the earlier statements that D-012–D-015 await approval: the user approved all four decisions as proposed. Their target remains unimplemented; current schema, API, authentication and client behavior are unchanged. T-104 design/review is complete and T-201's design dependency is satisfied, with migration/integrity/recovery verification still required. Social networking is **not production-complete** until blocking/reporting is designed, implemented and tested under D-016 / T-107 and [OWNERSHIP_DESIGN section 8](OWNERSHIP_DESIGN.md#8-blocking-and-reporting-production-completion-gate). This includes server enforcement, private report handling, explicitly authorized audited moderation, web/WebView and released-native coverage, and security/race/rollback tests. No blanket admin private-message access or irreversible retention policy is approved.

## Issue #22 — exclusive social route modes (2026-09-29)

The seven networking/conversation paths above retain their historical behavior only in default `legacy` mode. `maintenance` authenticates (and applies existing CSRF to unsafe methods) before a generic social 503 without graph access. `v2` intercepts the same paths plus `POST /api/conversations` and `POST /api/conversations/:slug/read`, requires ownership capability 2 after auth/CSRF, and delegates to `forge_routes/owned_social_http.py` and `OwnedSocialService`. No legacy social table is a fallback. The exact v2 bodies, projections, limits, cursors, and status codes are in API_CONTRACT. Student analytics remains on shared legacy connection counts pending coordinated cutover; v2 is API rehearsal only, not a deployable user-facing mode.

## 2026-10-09 — owned-social durable/realtime flow (Issue #28)

`owned_social_http.py` injects the existing Socket.IO emitter into `OwnedSocialService` only on the owned path. Service mutation -> transactional Notification insert plus connection-local intent -> successful commit/connection close -> best-effort delivery. Service authorization stays central: a brief post-commit `BEGIN IMMEDIATE` reservation spans final eligibility check and enqueue so block/suspension cannot commit between them. Emission reads message sequence/sender identity only, never message text; user rooms only.

The notification blueprint receives a v2-only service projection for list/unread count. Profile export uses that same projection, preventing an alternate suppressed-contact link surface. Legacy route behavior/dependencies remain intact. Account moderation calls the existing room manager to disconnect only the suspended/deleted target after commit; invalid v2 rejoins disconnect their client. No global session registry or auth replacement.

## 2026-10-09 — student analytics graph coordination / Issue #30

Entrypoint -> analytics blueprint with captured startup mode and v2-only accepted-date callable -> pure owned-service actor/endpoint query -> existing `daily_series`/`cumulative` -> unchanged student JSON. No owned graph is exposed to the route, no entrypoint import cycle and no fallback. Maintenance returns `503 {"error":"social maintenance"}` immediately after normal login. Business/admin analytics are outside this gate. Analytics keeps its any-active-authenticated-role access; its stable shape needs no capability negotiation or browser graph-selection logic.
