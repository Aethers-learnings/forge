# Known issues

Current implementation (2026-10-09): PR #27 merged directed blocking and PR #29 merged participant-safe delivery. Issue #30 implements student analytics ownership isolation for controlled v2 rehearsal. Legacy remains the default; production v2 is not enabled. T-201 whole-schema FK/admin-removal, persistent rollout/recovery and production cutover gates, plus T-107 reporting/reviewer/policy gates, remain open. Dated entries below preserve their historical scope.

## Verified defects / limitations

- Historical P0 findings (secret configuration, Socket.IO room identity/CORS, mobile transport, and CSRF) have implementation resolutions recorded in `SECURITY.md`; release-device checks remain separate. They must not be confused with the still-open social row-ownership defects below.
- Production operators must set `FORGE_ENV=production` and supply a unique `FORGE_SECRET_KEY` of at least 32 characters. Non-production processes receive an ephemeral random signing key, so their sessions do not survive a restart; this is intentional and unsuitable for multi-process production deployment.
- Default legacy network, suggestion, connection and conversation tables are shared demo state. Controlled v2 uses its separate authorized owned graph; legacy remains unsuitable for real private social data.
- `Conversation` and `Message` do not identify participants; message sender is stored only as `me`/`them`. This cannot support secure multi-user messaging.
- `Comment`, `Post`, and `Testimonial` persist display names rather than author foreign keys, limiting ownership enforcement, renames, deletion, and auditing.
- Posts have no timestamp, author user ID, or feed membership policy beyond the role string; content moderation is a boolean flag/soft removal only.
- CV upload accepts raw text and marks a CV as uploaded; it does not persist an original document or perform actual file upload/extraction.
- Opportunity visibility is not filtered to approved/live BusinessListings; `/api/opportunities` returns all `Opportunity` rows.
- The hard-delete admin user action attempts deletion without an explicit retention/cascade policy, then silently falls back to suspension on foreign-key failure.
- An automated Flask/Node/Chromium regression suite and reversible migration tooling exist; see `TEST_RESULTS.md`. Whole-schema FK/admin-removal review, persistent rollout/recovery rehearsal and production cutover remain outstanding under T-201.
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

## Issue #22 route boundary status (2026-09-29)

The historical shared social-route findings above apply in default `legacy` mode. Configured `v2` serves an isolated owned graph behind capability negotiation; `maintenance` returns authenticated 503. The static web/WebView client still speaks legacy, social socket/notification delivery and student analytics have not cut over, and T-107 remains mandatory. V2 is controlled API rehearsal, not a production social release. No ownerless legacy data was reassigned or erased.

## 2026-09-29 — web/WebView client limitation resolved for rehearsal

The earlier statement that the shared static client cannot speak ownership-v2 is superseded: explicit configuration/capability, versions, paging, real conversation creation, retry-key sends, explicit observed reads and account isolation are implemented and regression-tested. Production remains default legacy and is not enabled for v2 by this task. An unconfirmed send's in-memory retry key does not survive a page reload; reconcile history before resubmitting after reload. If IntersectionObserver is unavailable, the client conservatively does not advance read state.

Social socket/notification delivery, student analytics cutover, persistent rollout/recovery, whole-schema FK/admin-removal review, mandatory T-107 blocking/reporting, native social networking/messaging and signed-device WebView verification remain outstanding. This is controlled client rehearsal, not social production completion.

## 2026-10-09 — delivery boundary resolved for controlled rehearsal

PR #27's directed blocking core is merged; it is not outstanding implementation. Issue #28 adds atomic generic persistent notifications, reauthorized post-commit user-room delivery, minimal invalidation HTTP refresh, unread contact suppression and narrow moderation socket retirement. No schema blocker remains for suppression: reserved type/link references plus permanent empty unread hints implement the approved boundary without deleting Notification rows.

Limitations: Socket.IO delivery is best effort with no durable packet queue/replay; HTTP state is recovery. SQLite's brief reservation spans each enqueue in the current single-process architecture. Notification projection scans the caller's rows to authorize before count/limit; larger-volume optimization remains future profiling work. An unread notification is conservatively suppressed even if its packet was previously seen; no delivered/undelivered tracking field exists. Already queued/delivered packets cannot be recalled; cookie copies are not globally revoked. Native notifications retain their public shape, but native social and signed-device WebView/session verification remain separate.

T-201 remains open for student analytics isolation, whole-schema FK/admin-removal review, persistent rollout/recovery and production cutover. T-107 remains open for reporting/receipts, reviewer grants/queue/evidence/audit/transitions, and separately approved retention/erasure/legal hold/appeals/notices/emergency/anonymous/category/rate/evidence-window policies. No production v2 enablement, PR #26 change or real-database access occurred.

## 2026-10-09 — PR #29 review defects resolved

The review reproduced unsent draft loss during message refresh, permanently stale sockets after CSRF rejection, dropped non-social maintenance notifications and ignored conversation IDs in owned message links. These are fixed with focused Node and Chromium regressions, including typing during a delayed refresh, desktop/mobile selection preservation, old-handler rejection after automatic socket replacement, and authorized notification navigation from a previous selection. Draft preservation applies to automatic refresh of the current thread; it does not add persistent drafts across navigation, logout or reload. PR #29 is still awaiting human merge review.

## 2026-10-09 — multipart realtime recovery resolved

Re-review of `d73b693` reproduced a remaining gap: a video-upload CSRF rejection retired realtime without replacing its socket. The multipart path now shares JSON-request security invalidation and automatic same-account socket recovery, without retrying the upload. Current upload/token 401s expire the session; late responses or token work from an obsolete account generation have no effect on the current account. Nine Node cases and one Chromium case extend the maintained regression coverage. Signed-device WebView verification and the existing production release gates remain separate; PR #29 remains unmerged.

## 2026-10-09 — student analytics ownership boundary resolved / Issue #30

PR #29 is merged in starting master `3686256`; preceding unmerged statements are dated history. V2 student connection totals and series now use only the caller's currently accepted owned edges and accepted_at dates. Legacy's shared metric intentionally remains unchanged. Maintenance returns authenticated generic 503 without either graph read. SQL and A/B/C/admin tests prove no fallback/union/foreign graph. Missing acceptance time fails closed with generic analytics 503; remediation of corrupt persistent state is operator/recovery work, never an automatic repair or substitute date.

Other student metrics retain T-106 behavior, including display-name post attribution; those separate limitations are not resolved here. No client changes or schema blocker was needed for this gate. T-201 remains open for whole-schema FK/admin-removal review, persistent rollout/recovery and production cutover. T-107 remains open for reporting/receipts, reviewer grants/queues/evidence/audit/transitions and deferred category/rate/evidence-window, provisioning, retention/erasure/legal hold, appeals/notices, emergency and anonymous-report policy. Native social and signed-device WebView checks remain separate. Production remains default legacy; no v2 enablement or PR #26 work.
