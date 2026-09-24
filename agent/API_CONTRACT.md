# API contract baseline

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
