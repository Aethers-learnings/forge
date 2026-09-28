# Known issues

## Verified defects / limitations

- Historical P0 findings (secret configuration, Socket.IO room identity/CORS, mobile transport, and CSRF) have implementation resolutions recorded in `SECURITY.md`; release-device checks remain separate. They must not be confused with the still-open social row-ownership defects below.
- Production operators must set `FORGE_ENV=production` and supply a unique `FORGE_SECRET_KEY` of at least 32 characters. Non-production processes receive an ephemeral random signing key, so their sessions do not survive a restart; this is intentional and unsuitable for multi-process production deployment.
- Network, suggestion, connection, and conversation tables are seeded/shared demo state rather than per-user relationships. Any logged-in user can view or mutate the same rows.
- `Conversation` and `Message` do not identify participants; message sender is stored only as `me`/`them`. This cannot support secure multi-user messaging.
- `Comment`, `Post`, and `Testimonial` persist display names rather than author foreign keys, limiting ownership enforcement, renames, deletion, and auditing.
- Posts have no timestamp, author user ID, or feed membership policy beyond the role string; content moderation is a boolean flag/soft removal only.
- CV upload accepts raw text and marks a CV as uploaded; it does not persist an original document or perform actual file upload/extraction.
- Opportunity visibility is not filtered to approved/live BusinessListings; `/api/opportunities` returns all `Opportunity` rows.
- The hard-delete admin user action attempts deletion without an explicit retention/cascade policy, then silently falls back to suspension on foreign-key failure.
- An automated Flask/Node regression suite now exists; see `TEST_RESULTS.md`. Reversible schema migration tooling remains outstanding under T-201.
- Mobile has native authentication/profile/feed/opportunity/notification workflows plus WebView fallback; native networking/messaging is not implemented and remains blocked on approved ownership/migration work.

## Recommendations (not verified behavior)

- Add ownership foreign keys and migration strategy before converting demo networking/messaging data into real user data.
- Replace CSV/pipe-delimited skills, tags, programme targeting, and pathway rows with normalized structures only after an approved migration plan.
- Add timestamps, actor identities, audit records, pagination, validation limits, and retention rules to user-generated and administrative operations.

## T-203 follow-up boundary (2026-09-24)

The first notification/onboarding extraction requires no migration or architectural decision. Further identity, profile, media, workflow, and analytics extraction remains unimplemented in this PR. Shared networking/conversation ownership and messaging models must not be repaired as part of extraction: any such change remains stopped at the T-104/T-201 design and migration boundary. Authentication/session replacement and irreversible retention/deletion policy likewise remain outside this work. Historical discovery findings above are not newly verified defects from T-203.

## Issue #3 follow-up boundary (2026-09-24)

The five profile workflow routes are extracted with regression evidence; the earlier first-increment note is historical. Image upload/delete/serving and public-profile reads remain in the entrypoint under D-010. Identity, remaining workflows, media, and analytics extraction keep T-203 open. CV upload still accepts text only; substring matching, permissive JSON handling, and visibility truthiness are preserved baseline behavior, not redesigned here. T-104/T-201 ownership/schema and irreversible-retention boundaries remain unchanged.

## Issue #5 follow-up boundary (2026-09-26)

The three analytics handlers are now extracted under D-011 with T-106 semantics preserved. Earlier notes listing analytics extraction as unimplemented are historical. T-203 remains open for identity, remaining workflows, image/media, and public-profile routes. Shared networking counts and display-name post attribution remain existing data-model limitations; no T-104/T-201 ownership/schema or retention work is included.

## Issue #9 ownership design boundary (2026-09-26)

[OWNERSHIP_DESIGN](OWNERSHIP_DESIGN.md) documents shared histories/unread/endorsements, unproven legacy authors, related shared analytics, suspension-after-connect and pre-commit notification limitations. No defect is repaired by this design-only PR. Proposed D-012–D-015 require human review before schema/runtime/client changes; legacy reassignment, destructive cleanup, admin private-message access and organizational tenancy are not silently authorized.

## Ownership approval and production gate (2026-09-28)

This update supersedes the earlier statements that D-012–D-015 await approval: the user approved all four decisions as proposed. Their target remains unimplemented; current schema, API, authentication and client behavior are unchanged. T-104 design/review is complete and T-201's design dependency is satisfied, with migration/integrity/recovery verification still required. Social networking is **not production-complete** until blocking/reporting is designed, implemented and tested under D-016 / T-107 and [OWNERSHIP_DESIGN section 8](OWNERSHIP_DESIGN.md#8-blocking-and-reporting-production-completion-gate). This includes server enforcement, private report handling, explicitly authorized audited moderation, web/WebView and released-native coverage, and security/race/rollback tests. No blanket admin private-message access or irreversible retention policy is approved.

## T-201 bootstrap boundary before owned-social ORM models

The ordered owned-social schema revision exists, but application startup still
uses the historical `db.create_all()` path. Adding the six owned-social tables
to SQLAlchemy metadata before changing that bootstrap would allow a new or
partially managed database to receive those tables outside
`forge_schema_migrations`.

Therefore the next ownership implementation increment must first make
application/test schema initialization migration-aware or otherwise fail closed
on unmanaged/out-of-date persistent databases. Do not add owned-social ORM
models or rely on `db.create_all()` to create revision-02 tables until this is
resolved and regression-tested.

## Issue #16 bootstrap boundary resolved; remaining limits (2026-09-28)

The earlier `db.create_all()` bootstrap warning is resolved by migration-only fresh initialization, migrated test fixtures and read-only startup verification. An existing unmanaged/behind-head database now intentionally prevents startup until an operator explicitly verifies, backs up and adopts/upgrades it; no persistent rollout is performed here. Failed fresh initialization may leave an empty file/recovery journal and requires inspection/new disposable path, never forced adoption.

Owned-social ORM/service integration, D-014 cutover, global FK review and T-107 implementation remain open. Verification occurs at startup, not continuously; schema-changing operator commands require stopped application writers. SQLite read-only WAL access may maintain shared-memory read locks but does not mutate source schema/data. The new readiness check does not fix legacy social authorization.
