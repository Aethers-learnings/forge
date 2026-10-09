# Data model

Current implementation (2026-10-09): PR #27 merged directed blocking and PR #29 merged participant-safe delivery. Issue #30 implements student analytics ownership isolation for controlled v2 rehearsal. Legacy remains the default; production v2 is not enabled. T-201 whole-schema FK/admin-removal, persistent rollout/recovery and production cutover gates, plus T-107 reporting/reviewer/policy gates, remain open. Dated entries below preserve their historical scope.

Status: the discovery tables below are historical. Current ORM mappings are in `forge_backend.py`; frozen baseline and ordered migrations own schema creation, with fail-closed startup verification. Default persistent path is `instance/forge.db`; this increment never accessed it.

## Identity and profile

| Entity | Fields | Constraints / relations |
| --- | --- | --- |
| `User` | `id`, `username`, `password_hash`, `role`, `name`, `email`, `color`, `completion`, `cv_uploaded`, `skills`, `alumni_verified`, `created_at`, `headline`, `programme`, `year`, `campus`, `industry`, `company_desc`, `location`, `talent_sought`, `bio`, `github_url`, `linkedin_url`, `credly_url`, `portfolio_url`, `profile_visible`, `show_email`, `show_skills`, `business_approved`, `suspended`, `last_seen`, `onboarding_complete`, `onboarding_step`, `reset_token`, `reset_token_expires` | PK `id`; unique/non-null `username`; non-null password/role/name. CSV `skills`; `reset_token` stores a SHA-256 digest. |
| `AlumniVerification` | `id`, `user_id`, `document_ref`, `note`, `status`, `submitted_at` | PK; FK `user.id`; status pending/approved/rejected. |
| `ProfileView` | `id`, `viewed_user_id`, `viewer_user_id`, `source`, `created_at` | PK; FKs to `user.id`; viewer nullable. |
| `Testimonial` | `id`, `user_id`, `author_name`, `author_role`, `text`, `approved`, `created_at` | PK; FK target `user.id`; author is denormalized. |
| `Notification` | `id`, `user_id`, `type`, `text`, `link`, `read`, `created_at` | PK; FK `user.id`. |
| `CoachMessage` | `id`, `user_id`, `who`, `text`, `created_at` | PK; FK `user.id`; `who` is ai/user. |

## Content, engagement, and discovery

| Entity | Fields | Constraints / relations |
| --- | --- | --- |
| `Post` | `id`, `feed`, `author_name`, `author_role`, `color`, `body`, `media`, `video_url`, `thumb_url`, `pick`, `flagged`, `base_likes`, `removed` | PK; no author FK or timestamp. |
| `Like` | `id`, `post_id`, `user_id` | PK; FKs post/user; unique `(post_id,user_id)`. |
| `Comment` | `id`, `post_id`, `author_name`, `text`, `created_at` | PK; FK post; no author FK. |
| `Opportunity` | `id`, `title`, `co`, `match`, `tags`, `owner_user_id`, `listing_id`, `created_at` | PK; optional FKs `user.id` and `business_listing.id`; CSV tags. |
| `Application` | `id`, `opportunity_id`, `user_id`, `created_at` | PK; FKs opportunity/user; unique `(opportunity_id,user_id)`. |
| `Event` | `id`, `title`, `place`, `day`, `mon`, `programmes` | PK; day/month and CSV programmes are strings. |
| `Interest` | `id`, `event_id`, `user_id` | PK; FKs event/user; unique `(event_id,user_id)`. |
| `Pathway` | `id`, `prog`, `rows` | PK; pipe-delimited rows. |
| `SkillSearch` | `id`, `skill`, `searcher_id`, `created_at` | PK; nullable FK `user.id`. |

## Business approval and analytics

| Entity | Fields | Constraints / relations |
| --- | --- | --- |
| `ApprovalQueueItem` | `id`, `title`, `co`, `tags`, `status`, `submitted_at`, `decided_at` | PK; status pending/approved/rejected; CSV tags. |
| `BusinessListing` | `id`, `owner_user_id`, `queue_item_id`, `title`, `co`, `tags`, `status`, `impressions` | PK; nullable FKs user/approval item; status pending/live/rejected; CSV tags. |

## Demo/shared networking and messaging (not tenant-safe)

| Entity | Fields | Constraints / relations |
| --- | --- | --- |
| `NetworkRequest` | `id`, `name`, `role`, `color`, `status`, `created_at` | PK; no user ownership; pending/accepted/ignored. |
| `Suggested` | `id`, `name`, `role`, `color`, `status` | PK; no user ownership; none/pending. |
| `ConnectionNPC` | `id`, `name`, `role`, `color`, `skill`, `endorsements`, `endorsed_by_me` | PK; no user ownership. |
| `Conversation` | `id`, `slug`, `name`, `color`, `unread` | PK; unique/non-null slug; no participant relation. |
| `Message` | `id`, `conversation_id`, `who`, `text`, `created_at` | PK; FK conversation; `who` is me/them, not actor identity. |

## Relationship map and caveats

`User` is referenced by likes, applications, interests, alumni verification, profile views, notifications, coach messages, testimonials (target only), search logs, opportunities/listings (optional owner), and reset/session fields. `Post` is referenced by likes/comments; `Opportunity` by applications; `Event` by interests; `ApprovalQueueItem` by listing; `BusinessListing` by opportunity; `Conversation` by message.

The SQLAlchemy model declarations contain foreign keys but no explicit ORM relationships, cascade policy, indexes beyond primary/unique constraints, tenancy constraints, or audit/deletion policy. Normalization, PostgreSQL, and migrations are recommendations—not current implementation—and PostgreSQL requires human approval.

## T-104 ownership proposal — not current schema (2026-09-26)

[OWNERSHIP_DESIGN](OWNERSHIP_DESIGN.md) records source-verified limitations of `NetworkRequest`, `Suggested`, `ConnectionNPC`, `Conversation`, and `Message`, then proposes six separate owned entities with pair uniqueness, author/membership FKs, endorsement provenance, per-member read cursors and audit events. No model, database, index or migration has been changed. Legacy rows remain unassigned: names, seed templates and `me/them` cannot prove ownership. D-012–D-015 require human approval; T-201 must review FK enforcement across the existing schema and admin-removal behavior before implementing additive migration tooling.

## Ownership approval and production gate (2026-09-28)

This update supersedes the earlier statements that D-012–D-015 await approval: the user approved all four decisions as proposed. Their target remains unimplemented; current schema, API, authentication and client behavior are unchanged. T-104 design/review is complete and T-201's design dependency is satisfied, with migration/integrity/recovery verification still required. Social networking is **not production-complete** until blocking/reporting is designed, implemented and tested under D-016 / T-107 and [OWNERSHIP_DESIGN section 8](OWNERSHIP_DESIGN.md#8-blocking-and-reporting-production-completion-gate). This includes server enforcement, private report handling, explicitly authorized audited moderation, web/WebView and released-native coverage, and security/race/rollback tests. No blanket admin private-message access or irreversible retention policy is approved.

## T-201 migration tooling foundation — 2026-09-28

The first approved T-201 implementation increment adds explicit SQLite migration tracking without changing the application schema. `forge_migrations.py` provides a frozen 23-table baseline manifest, migration-ledger baselining, schema-drift verification, SQLite integrity/FK diagnostics, and consistent backup support using SQLite's backup API.

No ownership tables, indexes, constraints, foreign-key enforcement changes, automatic startup migrations, or production database mutations are included in this increment. Existing `db.create_all()` startup behavior remains temporarily unchanged. Applying the baseline to an existing persistent database is an explicit operator action and must refuse schema drift.

## T-201 owned-social schema revision — 2026-09-28

Ordered migration revision `20260928_02_owned_social_schema` now defines the
approved D-012 owned-social persistence layer: `network_edge`, `endorsement`,
`direct_conversation`, `conversation_member`, `direct_message`, and
`ownership_event`. The revision is additive. It leaves the five ownerless
legacy social tables physically intact and performs no legacy ownership import.

The revision includes canonical user-pair constraints, directed
requester/recipient identity, state/version checks, `ON DELETE RESTRICT`
identity references, endorsement provenance, opaque direct-conversation IDs,
two endpoint-only conversation-member triggers, per-member read cursors,
member-authored message foreign keys, `(conversation, sender,
client_message_id)` retry uniqueness, 4,000-character message limits, and
single-target ownership audit events.

The migration layer now supports ordered checksum-validated revisions,
explicit upgrade/downgrade commands, committed revision-schema manifests and
real SQLite DDL atomicity using `BEGIN IMMEDIATE`. Downgrade of revision 02 is
permitted only while all six owned-social tables are empty.

Copy-only rehearsal against a consistent backup of `instance/forge.db`
successfully baselined, upgraded from 23 to 29 application tables, verified
integrity and FK consistency, downgraded exactly back to the 23-table frozen
baseline, re-upgraded, refused downgrade after inserting controlled owned data,
then repeated the empty downgrade/upgrade successfully. The real
`instance/forge.db` remained byte/stat-identical, has no migration ledger and
has none of the six owned tables.

Global `PRAGMA foreign_keys=ON` is still intentionally not enabled. Application
startup is also not migration-managed yet: the existing ORM/bootstrap still
uses the historical `db.create_all()` path. Do not add owned-social ORM models
until that bootstrap boundary is changed, otherwise startup could create
migration-owned tables outside the ledger.

## Issue #16 bootstrap authority (2026-09-28)

Supersedes the historical create-all startup notes: fresh schema now comes solely from the unchanged frozen baseline and ordered revisions, including all six owned tables, physical constraints/indexes/triggers and checksum ledger. No new ORM models or revision changes are included. Persistent startup only verifies; explicit new-file initialization and existing-file adoption/upgrade are separate operator actions. Global FK enforcement remains unchanged.

## Issue #18 ORM and service mapping (2026-09-29)

Six `forge_backend.py` ORM mappings represent the already-migrated `network_edge`, `endorsement`, `direct_conversation`, `conversation_member`, `direct_message` and `ownership_event` tables. The focused internal service uses these mappings without creating schema, importing legacy social rows, adding cascade deletion or storing endorsement aggregates. Its normal general-endorsement read projection is caller-to-peer only; disconnect still revokes active endorsements in both directions. Migration history and global FK policy are unchanged. The earlier migration-only status above is historical.
