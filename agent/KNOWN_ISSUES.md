# Known issues

## Verified defects / limitations

- P0 security defects are tracked in `SECURITY.md`: predictable secret fallback, unauthenticated Socket.IO rooms/wildcard CORS, permissive/insecure mobile WebView transport, and absent CSRF protection.
- Network, suggestion, connection, and conversation tables are seeded/shared demo state rather than per-user relationships. Any logged-in user can view or mutate the same rows.
- `Conversation` and `Message` do not identify participants; message sender is stored only as `me`/`them`. This cannot support secure multi-user messaging.
- `Comment`, `Post`, and `Testimonial` persist display names rather than author foreign keys, limiting ownership enforcement, renames, deletion, and auditing.
- Posts have no timestamp, author user ID, or feed membership policy beyond the role string; content moderation is a boolean flag/soft removal only.
- CV upload accepts raw text and marks a CV as uploaded; it does not persist an original document or perform actual file upload/extraction.
- Opportunity visibility is not filtered to approved/live BusinessListings; `/api/opportunities` returns all `Opportunity` rows.
- Business analytics accepts admin access but queries opportunities/listings owned by the current admin account, producing empty/non-platform-wide data for admins.
- The hard-delete admin user action attempts deletion without an explicit retention/cascade policy, then silently falls back to suspension on foreign-key failure.
- There is no discovered automated test suite, lint configuration, database migration system, or CI workflow for the application.
- The mobile README and unused Expo template components remain starter material; mobile parity is WebView-based rather than native.

## Recommendations (not verified behavior)

- Add ownership foreign keys and migration strategy before converting demo networking/messaging data into real user data.
- Replace CSV/pipe-delimited skills, tags, programme targeting, and pathway rows with normalized structures only after an approved migration plan.
- Add timestamps, actor identities, audit records, pagination, validation limits, and retention rules to user-generated and administrative operations.
