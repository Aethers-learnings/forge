# API map

Status: verified from 61 Flask route decorators in `forge_backend.py`. All JSON routes return 401 through `require_login()` unless marked public/session-aware. No version prefix exists. State-changing cookie routes have no discovered CSRF protection.

## Auth and session

| Method / path | Access | Verified behavior |
| --- | --- | --- |
| POST `/api/auth/register` | Public | Creates `trade`, `grad`, or `business`; checks student-domain only when an email is supplied; creates a session. |
| POST `/api/admin/provision` | Secret header | Creates admin if `X-Provision-Secret` equals environment secret; otherwise 404. |
| POST `/api/auth/login` | Public | Username/password login; in-memory 5-attempt/300-second per-username throttle; creates session. |
| POST `/api/auth/forgot-password` | Public | Creates 30-minute reset token for matching username; sends SMTP email if configured; returns token in debug. |
| POST `/api/auth/reset-password` | Public token | Exchanges a valid stored token for a password of at least 8 characters. |
| POST `/api/auth/demo-login` | Debug only | Selects seeded `demo_<role>` user; 404 outside debug. |
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
| GET `/api/analytics/student` | Logged in | Returns caller views, shared network-derived connections, engagement, peer comparison, searched skills. |
| GET `/api/analytics/business` | Business or admin | Returns current user-owned opportunity/listing metrics. |
| GET `/api/analytics/admin` | Admin | Returns platform counts, queues, registration series, and content totals. |
| GET `/api/admin/users` | Admin | Returns administrative view of all users. |
| POST `/api/admin/users/:id/:action` | Admin | `approve-business`, `suspend`, `unsuspend`, or `remove` (fallback suspension on delete failure). |
| POST `/api/admin/announce` | Admin | Persists/sends an announcement to all or a role audience. |

## Static and realtime

- GET `/` serves `static/forge_demo.html`; GET `/manifest.webmanifest` and GET `/icons/:name` serve PWA assets.
- Socket.IO event `join` currently accepts client-supplied `userId` and `role` and joins both rooms; this is a P0 defect. Server emits `notification`, `new_comment`, `new_message`, `job_match`, and `new_applicant`.
