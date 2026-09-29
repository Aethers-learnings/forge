# T-107 implementation record

Date: 2026-09-29

Status: **directed blocking core implemented for review; reporting/reviewer work remains outstanding.**

This record describes the implementation on `manual/t107-blocking-core`, starting from `master` `0fb2c68261e63a126925165e080f0d684afade07`. It does not authorize production ownership-v2 enablement or merge.

## Implemented scope

- Additive migration `20260929_03_blocking_core` adds `user_block` and `block_event` on top of the existing migration ledger. The migration preserves legacy social tables, does not import ownerless legacy rows, does not globally enable SQLite foreign keys, and uses RESTRICT identity references.
- Blocking is directed for storage/control but pair-wide for social eligibility. Either active direction denies request/re-request, acceptance, conversation creation, new sends, and endorsement activation inside the same serialized `BEGIN IMMEDIATE` write transaction as the mutation.
- Blocking a pending edge cancels it. Blocking an accepted edge disconnects it. Active endorsements in both directions are revoked atomically with the block and ownership/block audit events.
- Existing direct conversation membership, messages, history and per-member read cursor remain intact. Existing members keep read-only history and may explicitly advance their own read cursor. A retry of a message that committed before a block still returns the historical row without creating a new message.
- Unblocking changes only the caller-owned directed block row. It does not restore a request, accepted edge, endorsement, unread state, notification, conversation write permission, or cooldown exception.
- Suggestions remove either-direction blocked pairs before HTTP pagination. Blocked-pair endorsement/reputation projection is suppressed.
- `GET /api/network/blocks` lists only the caller's active outgoing blocks with a caller-scoped signed cursor and minimal `targetUserId`, `name`, `version` projection.
- `PUT /api/network/blocks/:targetUserId` accepts exactly `{blocked, expectedVersion}`. It returns 201 for first creation and 200 for existing-state/update behavior; missing version is 428 and stale change is 409. Self, unavailable, hidden and nonexistent targets are concealed except an existing caller-owned block remains manageable for unblock.
- Authorized network/suggestion rows expose only the caller's own retained `blockVersion`, including inactive retained rows, so block -> unblock -> reload -> re-block can recover a current version without exposing whether the peer blocked the caller.
- Web/WebView ownership-v2 UI includes Block controls on existing peer contexts, confirmation when blocking ends an accepted connection, an own active Blocked accounts list with Unblock, bounded pagination, generic errors, stale-version refresh without intent replay, account-generation isolation and late-result dropping.
- Default/production social mode remains `legacy`. No production v2 cutover is included.

## Verification completed locally before publication

The implementation commit was `464957a0682d4b68918c5817cda0315bfa5f65dc` before documentation/helper cleanup.

Focused backend/web verification:

- Python blocking/owned-social/migration/bootstrap suite: **92 passed, 144 warnings**.
- Ownership-v2 frontend Node suite: **52 passed, 0 failed**.
- Python compile checks passed for changed backend/migration/test modules.
- `git diff --check` passed.
- Tests use isolated/disposable migration-managed databases. The helper explicitly refused to open or mutate the real `instance/forge.db`; no test or migration command was run against that database.

Coverage includes pending cancellation, accepted disconnection, two-direction endorsement revocation, independent opposite blocks, pair-wide denial, unblock restoration rules, pre-pagination suggestion exclusion, retained history/read cursor, stranger history denial, create/send/request/accept/endorse denial, desired-state idempotency, stale versions, re-block recovery after reload, suspended actor/peer behavior, block-vs-request/accept/create/send/endorse/read serialized races, rollback atomicity, HTTP identity/privacy/gate ordering, ordinary-admin isolation, Web/WebView stale refresh and account-switch cleanup.

## Final local gate run before review

After helper cleanup and documentation commits, the user ran the release-gate commands on `manual/t107-blocking-core`:

- full Forge pytest suite: **378 passed, 2 skipped, 1538 warnings in 136.49s**;
- dedicated Chromium owned-social command: **1 skipped** because `playwright.sync_api` is not installed in the active venv; the test module deliberately uses `pytest.importorskip("playwright.sync_api")`;
- mobile Node suite: **53 passed, 0 failed**;
- `npm --prefix mobile run lint`: PASS;
- mobile TypeScript `tsc --noEmit`: PASS;
- final `git diff --check`: PASS.

The Chromium result is an environment limitation, not a failing browser assertion. Install `requirements-browser.txt` and Chromium, then rerun `tests/test_browser_owned_social.py` before marking the PR ready for review. The PR remains draft until that browser gate is exercised or the gate is explicitly waived by a human reviewer.

## Review findings incorporated before PR

- Removed unnecessary `color` from the block-list projection to keep it at the minimum caller-management surface.
- Added caller-owned `blockVersion` projection to authorized network/suggestion rows. Without this, an inactive retained block row could not be reactivated after a reload because `GET /api/network/blocks` intentionally lists only active rows.
- Expanded race evidence beyond accept to request, conversation creation, send, endorsement and read; added injected rollback coverage.
- Temporary local apply/verification helpers were removed from the final branch diff before PR creation.

## Explicitly not implemented

The following approved/future T-107 work remains separate and must not be inferred from the blocking implementation:

- safety-report persistence or submission API;
- report receipts/status;
- reviewer queue, reviewer grants, evidence access, reviewer audit, transitions or appeals;
- reviewer provisioning/separation of duties;
- retention, erasure/anonymization, legal hold or emergency access policy;
- anonymous reporting;
- evidence-window/rate-limit/category policy decisions;
- socket/notification block invalidation/suppression policy beyond existing no-delivery ownership-v2 behavior;
- native Expo networking/messaging/block UI;
- global SQLite FK enablement or whole-schema admin-removal policy;
- persistent production ownership-v2 rollout/recovery.

T-107 as a whole therefore remains open. The blocking core is implemented and tested; reporting/reviewer/policy work is still a mandatory production-completion gate under `SAFETY_DESIGN.md` and D-016.
