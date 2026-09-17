# Architecture

Status: verified discovery baseline; future-state items are explicitly labelled.

## Current implementation

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
