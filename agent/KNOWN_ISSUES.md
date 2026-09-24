# Known issues

## Verified defects / limitations

- Remaining P0 security defects are tracked in `SECURITY.md`: unauthenticated Socket.IO rooms/wildcard CORS, permissive/insecure mobile WebView transport, and absent CSRF protection. The predictable secret fallback was resolved by T-001.
- Production operators must set `FORGE_ENV=production` and supply a unique `FORGE_SECRET_KEY` of at least 32 characters. Non-production processes receive an ephemeral random signing key, so their sessions do not survive a restart; this is intentional and unsuitable for multi-process production deployment.
- Network, suggestion, connection, and conversation tables are seeded/shared demo state rather than per-user relationships. Any logged-in user can view or mutate the same rows.
- `Conversation` and `Message` do not identify participants; message sender is stored only as `me`/`them`. This cannot support secure multi-user messaging.
- `Comment`, `Post`, and `Testimonial` persist display names rather than author foreign keys, limiting ownership enforcement, renames, deletion, and auditing.
- Posts have no timestamp, author user ID, or feed membership policy beyond the role string; content moderation is a boolean flag/soft removal only.
- CV upload accepts raw text and marks a CV as uploaded; it does not persist an original document or perform actual file upload/extraction.
- Opportunity visibility is not filtered to approved/live BusinessListings; `/api/opportunities` returns all `Opportunity` rows.
- The hard-delete admin user action attempts deletion without an explicit retention/cascade policy, then silently falls back to suspension on foreign-key failure.
- There is no discovered automated test suite, lint configuration, database migration system, or CI workflow for the application.
- The mobile README and unused Expo template components remain starter material; mobile parity is WebView-based rather than native.

## Recommendations (not verified behavior)

- Add ownership foreign keys and migration strategy before converting demo networking/messaging data into real user data.
- Replace CSV/pipe-delimited skills, tags, programme targeting, and pathway rows with normalized structures only after an approved migration plan.
- Add timestamps, actor identities, audit records, pagination, validation limits, and retention rules to user-generated and administrative operations.

## T-203 follow-up boundary (2026-09-24)

The first notification/onboarding extraction requires no migration or architectural decision. Further identity, profile, media, workflow, and analytics extraction remains unimplemented in this PR. Shared networking/conversation ownership and messaging models must not be repaired as part of extraction: any such change remains stopped at the T-104/T-201 design and migration boundary. Authentication/session replacement and irreversible retention/deletion policy likewise remain outside this work. Historical discovery findings above are not newly verified defects from T-203.
