# Architecture

Current implementation (2026-10-09): PR #27 merged blocking, PR #29 merged participant-safe delivery, and PR #31 merged student analytics isolation. Issue #32 completes the disposable whole-schema FK audit and hardens admin removal with physical preflight and fail-closed suspension, including unreferenced accounts while FK-off writers remain unsafe. Legacy remains the default; production v2 is not enabled. T-201 remains open for reviewed global-FK enablement, persistent rollout/recovery and production cutover; T-107 reporting/reviewer/policy gates remain open. Dated entries below preserve historical scope.

Status: historical discovery baseline followed by dated implementation updates; future-state items are explicitly labelled. For the approved ownership target and current increment evidence, see OWNERSHIP_DESIGN and the implementation updates below.

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

## Ownership approval and production gate (2026-09-28)

This update supersedes the earlier statements that D-012–D-015 await approval: the user approved all four decisions as proposed. Their target remains unimplemented; current schema, API, authentication and client behavior are unchanged. T-104 design/review is complete and T-201's design dependency is satisfied, with migration/integrity/recovery verification still required. Social networking is **not production-complete** until blocking/reporting is designed, implemented and tested under D-016 / T-107 and [OWNERSHIP_DESIGN section 8](OWNERSHIP_DESIGN.md#8-blocking-and-reporting-production-completion-gate). This includes server enforcement, private report handling, explicitly authorized audited moderation, web/WebView and released-native coverage, and security/race/rollback tests. No blanket admin private-message access or irreversible retention policy is approved.

## 2026-09-28 — T-201 ordered SQLite migration layer

Forge now has an explicit ordered SQLite migration layer alongside the existing
Flask/SQLAlchemy application. The pre-migration 23-table schema remains frozen
as revision `20260928_01_pre_migrations`; revision
`20260928_02_owned_social_schema` is layered on top rather than rewriting that
baseline.

Schema-changing operations use an explicit SQLite `BEGIN IMMEDIATE`
transaction so DDL, verification and migration-ledger writes commit or roll
back together. Each revision has checksum-protected code/schema state, upgrade
and guarded downgrade behavior, integrity/FK verification, and explicit
operator CLI commands. Nothing auto-upgrades during normal Flask startup.

Revision 02 adds only the six approved owned-social persistence tables and
supporting constraints/indexes/triggers. It does not cut over routes, clients,
sockets, notifications or analytics; it does not migrate legacy social rows;
and it does not globally enable SQLite FK enforcement.

A copy-only rehearsal against the current real database proved reversible empty
upgrade/downgrade behavior and refusal to discard owned data. The real database
was deliberately not baselined or upgraded.

Important next architectural boundary: `forge_backend.py` still has historical
`db.create_all()` bootstrap behavior. Before owned-social SQLAlchemy models are
declared, startup and test database initialization must become
migration-aware/fail-closed so ORM metadata cannot bypass the ordered migration
ledger.

## Issue #16: migration-owned initialization (2026-09-28)

`forge_migrations.py` plus committed manifests/revisions are the schema authority. The fresh initializer materializes the frozen baseline without importing application metadata, applies the ordered revisions and ledger in one explicit transaction, and verifies before commit. `db-init` requires confirmation and refuses every existing file. Test resets replace only fixture-owned files using this initializer; there is no application/test `create_all()` path.

Normal app import (including WSGI), direct execution and Flask run verify persistent HEAD before serving. A separate SQLite read-only connection avoids application WAL/NORMAL hooks during refusal; those hooks now attach only to the app engine. Checksum/order, reflected schema, physical revision SQL/trigger bodies, ledger columns and integrity must pass. CLI command discovery is exempt so operators can recover an unready database; seed-demo explicitly checks readiness. Fresh memory databases auto-initialize only in development/test. This is a bootstrap seam, not an app-factory or framework rewrite; routes, models, authentication and FK policy are unchanged. See README's environment/state policy and interruption limits.

## Issue #18 — internal owned-social service (2026-09-29)

Six ORM classes map the tables created by revision 02; migrations remain the schema authority. The unwired `forge_routes/owned_social.py` service receives the existing engine and model module, without creating another Flask app or database. Each mutation reserves SQLite's write lock with `BEGIN IMMEDIATE` before reading actor, account, pair or membership state. State changes and ownership audit commit together; detached results return only after commit. Read helpers scope edges and conversation history to the actor. Existing HTTP handlers, clients, Socket.IO, notifications and analytics do not call this service yet. Coordinated ownership-v2 cutover, whole-schema foreign-key review and persistent rollout remain T-201 work.

## Issue #22 — HTTP social gate (2026-09-29)

Startup config selects exactly one social graph mode. The existing legacy handlers remain registered for default behavior, while a process-fixed request dispatcher intercepts affected paths for maintenance or v2 after the global CSRF guard. V2 performs login and capability negotiation before invoking `OwnedSocialService`; the HTTP translator owns body parsing, signed cursor encoding and viewer-relative serialization, while pair/membership/write authorization remains in the transactional service. No route-level legacy fallback, socket/notification emission, analytics change, client update, or migration was introduced. Production cutover still requires the coordinated gates recorded in TASKS and OWNERSHIP_DESIGN.

## 2026-10-09 — narrow owned analytics read boundary / Issue #30

The existing analytics blueprint now receives the fixed startup mode and, only in v2, a callable projecting `OwnedSocialService.accepted_connection_dates(user)`. The entrypoint supplies its existing engine/model module; the blueprint never imports `forge_backend`, creates a database or receives the whole owned graph. The helper re-resolves the active trusted actor and selects only `network_edge.accepted_at` for accepted rows with that caller as an endpoint. It performs no writes, audit, notification or socket work, and has no admin override. Missing acceptance time fails closed through generic analytics 503.

Legacy alone reads the historical shared request/NPC inputs. Maintenance stops after login, before any graph/metric reads. Mode capture also fixes private no-store response policy for v2/maintenance; request claims and later mutable config cannot switch the provider. Unrelated analytics handlers are unchanged; no migration or architecture replacement.

## 2026-10-09 — bounded removal/integrity seam / Issue #32

`forge_integrity.py` reflects physical SQLite constraints (ordered composite FKs included) and exposes content-free violation identifiers. It creates no schema/app/endpoint. The existing admin route delegates only removal: release the prior ORM read transaction, reserve BEGIN IMMEDIATE on an independent existing-engine connection, recheck actor/target authority, preflight real user references, commit suspension. Failed commits explicitly roll back the underlying DBAPI handle because SQLAlchemy can lose its logical transaction marker before SQLite ends the transaction.

A reserved write lock cannot prevent a stale FK-off child insert after hard-delete commit. Removal therefore retains even currently unreferenced identities pending the separately verified global writer boundary. This is a bounded safety fallback under the user's fail-closed instruction, not an architecture/retention redesign. Existing room-manager moderation retirement now applies to every mode. WAL/NORMAL initialization, migration authority, default legacy and disabled production v2 remain unchanged. See FK_ADMIN_REVIEW for physical matrices and rollout gates.
