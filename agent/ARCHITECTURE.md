# Architecture

Status: historical discovery baseline followed by dated implementation updates; future-state items are explicitly labelled. For current social ownership evidence and the unapproved target, see the T-104 note below.

## Original discovery snapshot (historical)

```text
Browser / installed PWA                 Expo mobile wrapper
static/forge_demo.html                 mobile/src/app/index.tsx
  fetch + DOM + Socket.IO                  WebView to editable HTTP(S) URL
             |                                      |
             +------------- Flask ------------------+
                           forge_backend.py
                 routes, models, auth, moderation,
                 analytics, uploads, coach integration
                         |                 |
                 SQLite / instance/forge.db  instance/uploads/
                         |
                 optional SMTP and Anthropic HTTP API
```

Flask serves `/`, the manifest, and icons from `static/`; it exposes `/api/*` JSON routes and `/uploads/*`. Session authentication stores `user_id` in Flask’s signed cookie. SQLAlchemy defines the schema inline and `db.create_all()` is invoked when the module is run directly. SQLite WAL/NORMAL pragmas are set for each connection. There is no migration framework, background worker, repository/service layer, formal API schema, test suite, or deployment configuration in the discovered project files.

The current client is same-origin. It renders API data via `innerHTML` with an `esc()` helper for most dynamic display values and establishes a Socket.IO connection after login. The mobile app persists the selected server URL in AsyncStorage and loads it in a WebView; Android cleartext traffic is enabled.

## Verified boundaries and responsibilities

- Authentication, role checks, session mutation, database queries, HTML serving, upload/transcode, realtime fan-out, external email, and optional LLM calls all live in `forge_backend.py`.
- `User`, content, opportunities, approvals, analytics, notifications, and several seeded/demo-only social entities share one SQLite schema; some network/conversation entities lack user ownership.
- ffmpeg is discovered from PATH and is invoked with an argument list and timeout. If unavailable/transcoding fails, the original video is retained with an SVG thumbnail.
- SMTP only sends when environment variables are configured; otherwise email bodies are written to application output. The career coach calls Anthropic only when `ANTHROPIC_API_KEY` is configured and otherwise returns rule-based text.

## Architectural principles and change classification

| Principle | Classification |
| --- | --- |
| Do not perform a large rewrite merely because the current implementation is monolithic. | SAFE_INCREMENTAL |
| Prefer incremental extraction and regression testing. | SAFE_INCREMENTAL |
| Flask remains the current backend unless a future replacement receives human approval. | HUMAN_APPROVAL_REQUIRED |
| The current web frontend remains until an incremental migration path is proven. | MAJOR_REVIEW |
| The current Expo/WebView mobile application remains during native-mobile parity work. | SAFE_INCREMENTAL |
| PostgreSQL is a future migration requiring human approval. | HUMAN_APPROVAL_REQUIRED |
| Fundamental authentication changes require human approval. | HUMAN_APPROVAL_REQUIRED |

## Proposed future architecture (not implemented)

Extract route-local services behind tests first: identity/session policy, socket authorization, content/upload policy, and workflow/approval services. Preserve Flask routes while introducing route blueprints and a versioned API contract only after regression coverage exists. A native mobile client can consume those stable contracts feature by feature while the WebView remains supported. Assess PostgreSQL and a schema migration tool only after data ownership, backups, and a migration/rollback plan have been approved.

## 2026-09-24 — T-203 first extraction (Issue #1)

The discovery descriptions above are historical. The current entrypoint still creates the Flask app, SQLAlchemy instance, models, Socket.IO instance, configuration, security hooks, and the remaining routes. Six account routes now live in two modules:

| Module | Responsibility | Existing dependencies supplied by the entrypoint |
| --- | --- | --- |
| `forge_routes/onboarding.py` | Read, advance, and skip onboarding | `db`, `require_login`, `ONBOARDING_STEPS` |
| `forge_routes/notifications.py` | List notifications, mark one read, mark all read | `db`, `require_login`, `Notification` |

Each module exports a blueprint factory. `forge_backend.py` registers each blueprint once, at the former route group's location. The factories do not import the entrypoint or instantiate an app/database; both module imports and direct-script startup keep a single app. Paths, methods, query order/limits, JSON serialization, status codes, transaction points, and authentication/CSRF policy are preserved. Flask's internal endpoint identifiers for the moved views acquire the `onboarding.` or `notifications.` namespace; no existing code uses their former identifiers via `url_for` or `request.endpoint`.

These small handlers retain their route-local queries and mutations; a separate service layer would add indirection without separating another responsibility. Further identity, workflow, profile, media, and analytics extraction remains incremental follow-up work. No schema, data ownership, framework, or authentication decision is required for this increment.

## 2026-09-24 — T-203 profile extraction (Issue #3)

The five profile workflow handlers (CV text, skills, portfolio, visibility, export) now live in `forge_routes/profile.py`. `create_profile_blueprint` receives the existing `db`, `require_login`, `STUDENT_ROLES`, `extract_skills`, `recalc_completion`, `Notification`, `CoachMessage`, and `Application` dependencies. It is registered once at the former handler location and creates no app/database or alternate service stack. Small queries/mutations remain route-local; shared completion and keyword helpers remain in the entrypoint.

Internal endpoint identifiers acquire the `profile.` namespace; repository inspection found no references to their old names via `url_for` or `request.endpoint`. Public paths/methods, serialization, query ordering, transactions, and the global security hook are preserved. Image upload/delete/serving, filesystem cleanup/rollback, public-profile reads, and all remaining workflows stay in `forge_backend.py` (D-010). T-203 remains open.

## 2026-09-26 — T-203 analytics extraction (Issue #5)

The three analytics GET handlers now live in `forge_routes/analytics.py`. Its blueprint factory receives the existing login guard, models, and `daily_series`/`cumulative` helpers explicitly; `forge_backend.py` registers it once at the former route-group location. No second app/database or service/repository layer is introduced. Queries, aggregation, ordering, serialization, and the login guard's activity-update commit are unchanged. Shared helpers remain in the entrypoint.

Internal endpoint identifiers acquire the `analytics.` prefix; no repository code references the old identifiers through `url_for` or `request.endpoint`. All public URL rules and schema metadata match the branch base. Identity, remaining workflows, image/media, and public-profile extraction remain follow-up work.

## T-104 current evidence and proposed boundary (2026-09-26)

At `d4a0516`, Flask/SQLite and signed-session/CSRF security remain the baseline. Notifications/onboarding/profile/analytics have incremental blueprint extractions; an automated regression suite exists. Mobile now includes native workflows and an HTTPS-restricted WebView fallback, superseding the original discovery snapshot's wrapper/cleartext description. Networking/conversation handlers and five ownerless social tables remain in `forge_backend.py`.

[OWNERSHIP_DESIGN](OWNERSHIP_DESIGN.md) traces these handlers and their consumers and proposes a minimal user-pair/membership model, explicit API transition and additive-first migration. D-012–D-015 are **PROPOSED / REQUIRES HUMAN APPROVAL**. This is not an app-factory rewrite, authentication replacement, schema change, or native messaging implementation. Keep T-203 behavior-preserving extraction separate from later approved ownership work.
