# API contract baseline

Current implementation (2026-10-09): PR #27 merged blocking, PR #29 merged participant-safe delivery, and PR #31 merged student analytics isolation. Issue #32 completes the disposable whole-schema FK audit and hardens admin removal with physical preflight and fail-closed suspension, including unreferenced accounts while FK-off writers remain unsafe. Legacy remains the default; production v2 is not enabled. T-201 remains open for reviewed global-FK enablement, persistent rollout/recovery and production cutover; T-107 reporting/reviewer/policy gates remain open. Dated entries below preserve historical scope.

Status: stable baseline for the current unversioned Flask API. This document fixes the request and response shapes relied upon by the existing web client and planned incremental clients. It does not introduce API versioning, change route ownership, or resolve the data-model limitations recorded in `KNOWN_ISSUES.md`.

## Common transport rules

- JSON request bodies use `Content-Type: application/json`. Required and optional fields are defined per route below. Routes that use Flask's forced JSON parsing may return Flask's standard `400` response for a missing or malformed JSON body before Forge validation runs.
- Successful application JSON responses use `application/json`. Forge-generated error responses are JSON objects with an `error` string unless Flask's standard `400`/`404`/`405` handling applies.
- `GET`, `HEAD`, `OPTIONS`, and `TRACE` are safe for CSRF purposes. For every other `/api/` method made in an authenticated session, send same-origin `Origin` (or `Referer`) plus `X-CSRF-Token`. Anonymous unsafe requests are not intercepted by the CSRF middleware; public authentication/reset routes therefore retain their own anonymous behavior. Obtain the token from `GET /api/auth/csrf-token`; an authenticated CSRF failure returns `403 {"error": "...", "code": "csrf_failed"}`.
- `401` means no usable authenticated session; `403` means an authenticated caller lacks the required role/ownership or failed CSRF validation. Routes may return `404` to conceal an unavailable or unauthorized resource.
- Arrays are JSON arrays; optional URL values are `null` when absent unless a route documents an empty string.

## Stable resources

### User

`User` responses from registration, login, `GET /api/auth/me`, and profile update routes contain these fields:

```json
{
  "id": 12,
  "username": "sam",
  "role": "trade",
  "name": "Sam",
  "color": "#2c6e62",
  "avatarUrl": "",
  "completion": 72,
  "cvUploaded": false,
  "skills": ["Python"],
  "alumniVerified": false,
  "bio": "",
  "headline": "",
  "programme": "",
  "year": "",
  "campus": "",
  "businessApproved": false,
  "company": {"industry": "", "description": "", "location": "", "talentSought": ""},
  "portfolio": {"github": "", "linkedin": "", "credly": "", "website": ""},
  "visibility": {"profileVisible": true, "showEmail": false, "showSkills": true},
  "onboarding": {"complete": false, "step": 0}
}
```

### Post

`Post` responses from feed, create, like, comment, flag, and video creation contain:

```json
{"id": 4, "name": "Sam", "role": "trade", "color": "#2c6e62", "body": "Hello", "media": false, "videoUrl": null, "thumbUrl": null, "pick": false, "flagged": false, "likeCount": 0, "likedByMe": false, "comments": [{"who": "Sam", "text": "Nice"}]}
```

### Opportunity

`Opportunity` responses from list and apply contain:

```json
{"id": 8, "title": "Junior developer", "co": "Forge", "match": 80, "matchIsFallback": true, "tags": ["Python"], "applied": false}
```

## Contracted routes

| Method / path | Request | Success response |
| --- | --- | --- |
| `POST /api/auth/register` | `{username, password, role, name?, email?}`; role is `trade`, `grad`, or `business` | `201 User`; `400` invalid fields, `409` duplicate username |
| `POST /api/auth/login` | `{username, password}` | `200 User`; `401` invalid credentials, `403` suspended, `429` throttled |
| `POST /api/auth/logout` | no body; authenticated calls require CSRF | `200 {"ok": true}` |
| `GET /api/auth/me` | none | `200 User` or `200 null` |
| `GET /api/auth/csrf-token` | authenticated session | `200 {"csrfToken": "..."}` and `Cache-Control: no-store`; `401` otherwise |
| `GET /api/feed` | authenticated session | `200 Post[]` |
| `POST /api/posts` | `{body}` | `201 Post`; `400` when body is blank |
| `POST /api/posts/:id/like` | no body | `200 Post` with `likedByMe` toggled |
| `POST /api/posts/:id/comments` | `{text}` | `200 Post`; `400` when text is blank |
| `GET /api/opportunities` | authenticated session | `200 Opportunity[]` |
| `POST /api/opportunities/:id/apply` | no body | `200 Opportunity` with `applied` toggled |
| `PATCH /api/profile/skills` | `{action: "add"|"remove", skill}`; trade/grad only | `200 User`; `400` for invalid request or role |
| `GET /api/notifications` | authenticated session | `200 {"notifications": Notification[], "unreadCount": number}` |
| `POST /api/notifications/:id/read` | no body | `200 {"ok": true}`; `403` for another user's notification |
| `POST /api/notifications/read-all` | no body | `200 {"ok": true}` |

`Notification` has `{id, type, text, link, read, createdAt}`. `createdAt` values are ISO-8601 datetime strings.

## Compatibility policy

Existing documented fields and status codes are contractually stable for incremental route extraction. Additive response fields are permitted. Removing or renaming a documented field, changing its JSON type, or changing a documented success/error status requires an explicit compatibility decision and accompanying migration plan.

## Pending social ownership contract review (2026-09-26)

[OWNERSHIP_DESIGN](OWNERSHIP_DESIGN.md#4-api-and-client-transition--proposed-contract-boundary) is a proposed future mapping, not an amendment to this implemented contract. It explicitly lists changes that cannot be treated as harmless additive fields: real-user ID namespaces, required transition versions, desired-state endorsements, bounded message histories, pure reads, message retry keys and response/status changes. Existing paths, authentication, CSRF and client behavior are unchanged by Issue #9. D-014 and coordinated web/WebView migration require human approval; future native messaging remains blocked.

## Ownership approval and production gate (2026-09-28)

This update supersedes the earlier statements that D-012–D-015 await approval: the user approved all four decisions as proposed. Their target remains unimplemented; current schema, API, authentication and client behavior are unchanged. T-104 design/review is complete and T-201's design dependency is satisfied, with migration/integrity/recovery verification still required. Social networking is **not production-complete** until blocking/reporting is designed, implemented and tested under D-016 / T-107 and [OWNERSHIP_DESIGN section 8](OWNERSHIP_DESIGN.md#8-blocking-and-reporting-production-completion-gate). This includes server enforcement, private report handling, explicitly authorized audited moderation, web/WebView and released-native coverage, and security/race/rollback tests. No blanket admin private-message access or irreversible retention policy is approved.

## Issue #22 — configured ownership-v2 HTTP contract (2026-09-29)

`FORGE_SOCIAL_MODE` is parsed exactly at startup: `legacy` (default, existing seven handlers), `maintenance` (authenticated 503 after CSRF), or `v2` (owned graph only). Unknown values fail startup. In v2, active-session auth and the existing unsafe-method origin/CSRF guard precede `X-Forge-Ownership-Version: 2`; absent/unsupported capability returns `426 {"error":"ownership client update required"}` before object lookup. Private v2 responses use `Cache-Control: no-store`. This is an internal rehearsal contract; the current web/WebView client cannot use it yet.

| V2 path | Body / success | Relevant failures |
| --- | --- | --- |
| `GET /api/network` | `{requests,outgoingRequests,suggested,connections,nextCursors}`; optional `limit`, section `*Limit` (1–50), section `*Cursor` | Invalid cursor/limit 400; only own pending/accepted graph and eligible discoverable users. |
| `POST /api/network/suggested/:targetUserId/connect` | `{expectedVersion}`; 200 `{ok,requestId,version}` | Missing version 428; stale/opposite 409; missing/hidden/ineligible target 404 or generic unavailable per pair state. |
| `POST /api/network/requests/:edgeId/:action` | `{expectedVersion}`; accept/ignore/cancel/disconnect; 200 `{ok,version}` | Wrong endpoint 403; outside pair 404; stale 409. |
| `POST /api/network/connections/:edgeId/endorse` | `{endorsed,expectedVersion}`; 200 `{id,endorsements,endorsedByMe,version}` | Desired-state retries are no-ops; caller→peer general context only. |
| `GET /api/conversations` | Caller-member array; optional `limit` (1–50), `cursor`; next via `X-Next-Cursor`; latest one-message preview | Foreign cursor 400; no read mutation. |
| `GET /api/conversations/:slug` | Latest 50 ascending messages; optional scoped `before`; `hasMore`, `nextCursor`, `lastSequence`, `lastReadSequence`, `readOnly`, `unreadCount` | Nonmember and nonexistent both 404; no read mutation. |
| `POST /api/conversations` | `{targetUserId}`; detail projection, 201 created / 200 reused | Accepted active pair required. |
| `POST /api/conversations/:slug/messages` | `{text,clientMessageId}`; `{conversationId,message,lastSequence}`, 201 first / 200 identical retry | Changed same-key text 409; no synthetic reply. |
| `POST /api/conversations/:slug/read` | `{upToSequence}`; 200 `{lastReadSequence,unreadCount}` | Own monotonic bounded cursor only. |

Unknown body fields, including identity and role claims, fail 400. Cursors are signed, caller scoped, and conversation scoped for history; they never authorize access. No socket, notification, analytics, web/WebView, or T-107 cutover accompanies this contract.

## 2026-09-29 — static-client mode discovery and consumption

Public `GET /api/social-config` returns `200 {"mode":"legacy"|"maintenance"|"v2"}` with `Cache-Control: no-store`. The value is captured from the same startup mode as the social dispatcher; this endpoint reads neither social graph and grants no authorization. It introduces no new flag or configuration service. Default mode remains legacy. The static web/WebView client explicitly selects and pins this contract per account generation, clearing selection and all private cursors/state on session changes. Failed configuration does not assume legacy, and failed social operations never switch contracts.

The v2 client sends `X-Forge-Ownership-Version: 2` and existing CSRF tokens, consumes bounded network/list/history pages, uses real counterpart IDs for create/reuse, and submits only the documented exact version/desired-state/message/read bodies. It retains send retry keys only in account-scoped memory. Rendering a list or fetching history does not mark read; visible message observations trigger the explicit read endpoint. Runtime social authorization and all pre-existing v2 status/body contracts are unchanged. Production v2, delivery, analytics and T-107 are not enabled/completed by this client increment.

## 2026-10-09 — Issue #28 ownership-v2 delivery contract

After a real message commit, `new_message` carries **only** `{conversationId,lastSequence}` to each participant's `user:<id>` room, including the sender's other active devices. No body, history, author/room claims, block metadata or role broadcast. The client re-fetches authorized HTTP state; socket content never supplies message text. Only the other member receives one generic persistent `owned_message` Notification (`You have a new message.`). Identical normalized same-key sends return historical results, including after block/disconnect, without another notification or packet; changed text conflicts.

A real request creates one `owned_request` Notification (`You have a connection request.`) for the derived recipient. Successful acceptance creates one `owned_accepted` Notification (`Your connection request was accepted.`) for the original requester. Request no-ops, stale accept, denied operations, ignore/cancel/disconnect, endorsement, conversation creation/reuse and read cursor writes create no new notification. Relationship updates use the generic `notification` packet only; no additional role/social-state event is introduced.

The public Notification remains `{id,type,text,link,read,createdAt}`. Owned links are authenticated navigation hints: `network:<edgeId>:<edgeVersion>` or `messages:<opaqueConversationId>:<sequence>`. They grant no access and contain no message text or client identity claims. V2 lists/counts and existing profile-export notifications apply the service's eligibility projection; filtering precedes the newest-50 limit and unread count. Private notification responses and v2 profile export are no-store. Mark-read ownership/CSRF rules are unchanged.

Notification persistence shares the business transaction; emit is strictly post-commit and best effort. Each enqueue rechecks both accounts, pair state/block and membership or edge version/recipient. Block/terminal transition clears unread owned links in its transaction; empty owned links remain permanently suppressed, while generic rows remain stored. No notification-delivery flag/schema or historical-deletion policy was added. Already delivered packets cannot be recalled. HTTP/history refresh reauthorizes, and no client mutation intent is replayed by a socket refresh/error. Legacy remains the default; no production v2 rollout.

PR #29 review clarification: the web/WebView consumer selects the conversation in an `owned_message` hint before invoking authorized history loading, even when another conversation was previously selected. It rejects malformed owned hints and stale account callbacks. Ordinary notification delivery remains available while the social mode is maintenance; social operations still return their existing unavailable behavior. Automatic thread invalidations preserve in-progress composer text and selection. CSRF rejection replaces obsolete socket handlers without retrying a mutation. No public response or request shape changes accompany these fixes.

## 2026-10-09 — mode-aware student analytics / Issue #30

`GET /api/analytics/student` retains any active authenticated-role access and successful keys `{profileViews,connections,engagement,peerComparison,topSearchedSkills}`. Only the connection source depends on the process-fixed startup mode; query/header claims and ownership capability cannot choose a graph or redirect the session caller. No new capability requirement.

- **legacy (default):** total = all accepted legacy NetworkRequest rows + all ConnectionNPC rows. Series = existing 14-day cumulative accepted-request creation dates; NPCs contribute only to total. Owned rows are ignored.
- **v2:** total = all currently accepted network_edge rows where the caller is low/high endpoint. Series = existing cumulative daily buckets over accepted_at, including today and the preceding 13 days. Outside-window accepted edges contribute to total but not the bounded series. Pending/ignored/cancelled/disconnected rows do not contribute; normal blocking terminalizes the edge and unblock restores nothing. Empty owned graph returns total zero and 14 zero buckets, with no legacy access/fallback.
- **maintenance:** normal authentication (401 missing/deleted, 403 suspended) precedes generic `503 {"error":"social maintenance"}`; neither social graph is read. Business/admin analytics remain available under their existing role rules.

V2 and maintenance student responses are `Cache-Control: no-store`, including errors. Missing accepted_at on a counted owned edge fails closed with `503 {"error":"analytics unavailable"}`; never substitute creation/request time. The service's active-actor recheck can deny with generic 403 after initial auth. Unrelated T-106 metrics and response types remain unchanged.

## 2026-10-09 — clarified admin remove safety / Issue #32

`POST /api/admin/users/:id/remove` requires an active admin session and ordinary unsafe-method CSRF/origin headers, with no body required. Under BEGIN IMMEDIATE it rechecks active-admin authority and protects admin targets. A real FK reference returns `200 {"ok":true,"note":"<name> has linked activity — suspended instead."}`; the user is suspended and all referenced rows remain unchanged. An unreferenced account returns `200 {"ok":true,"note":"<name> suspended instead."}` for now: FK-off competing writers prevent a safe hard-delete guarantee. This is the authorized non-destructive failure mode, not a new erasure/retention policy. No successful hard deletion is claimed.

Missing target returns JSON 404; an admin target returns 400; wrong/inactive actor fails authentication/403. Reservation/preflight/update/commit errors return `503 {"error":"operation unavailable"}` after rollback, without linked-table details. Effective committed suspension retires only target sockets in all modes. Removal is repeatable and `unsuspend` retains its existing restore contract. No capability header is required for moderation. Safe clean-user hard deletion remains gated on a separately verified writer boundary; global FKs were not enabled. See FK_ADMIN_REVIEW.
