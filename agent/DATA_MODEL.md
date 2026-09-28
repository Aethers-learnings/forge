# Data model

Status: verified SQLAlchemy schema in `forge_backend.py`. SQLite database path: `instance/forge.db`. Schema creation is inline via `db.create_all()`; no migration history was found.

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
