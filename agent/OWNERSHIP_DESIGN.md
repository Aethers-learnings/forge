# T-104: networking and conversation ownership

Status: **PROPOSED / REQUIRES HUMAN APPROVAL** — Issue #9 architecture-review package, 2026-09-26. This document does not authorize implementation or declare the ownership defect fixed. T-104 remains open pending review; T-201 remains blocked on an approved design.

Evidence base: commit `d4a0516c3d053010a4a9c1a21208ff4f0021c5ee`. Read with [ARCHITECTURE](ARCHITECTURE.md), [API_CONTRACT](API_CONTRACT.md), [API_MAP](API_MAP.md), [SECURITY](SECURITY.md), [DATA_MODEL](DATA_MODEL.md), and proposed D-012–D-015 in [DECISIONS](DECISIONS.md). Names below identify source symbols, not new implemented classes. All target tables, constraints, endpoints, statuses, client changes, and migration commands below are proposals only.

## 1. Current behavior and evidence

Authentication is already signed Flask-session authentication. `require_login` resolves the session's user, rejects missing/deleted users with 401 and suspended users with 403, and commits `last_seen` before the handler. Authenticated unsafe API requests also pass the existing session-token and same-origin CSRF checks. These checks establish the actor; they do not establish ownership of social rows. No authentication, token, CSRF, framework, or database replacement is proposed.

The following handlers and models are in [forge_backend.py](../forge_backend.py). Every route listed requires login but has no social ownership predicate.

| Entry point / symbols | Current reads, writes, response | Concrete isolation failure |
| --- | --- | --- |
| `GET /api/network`, `get_network` route group | Returns every `NetworkRequest`, `Suggested`, and `ConnectionNPC`, ordered by ID. Root keys: `requests`, `suggested`, `connections`. | Any active user gets the same names, statuses, counters, and endorsement flag. |
| `POST /api/network/requests/<req_id>/<action>` | `accept`/`ignore` overwrite a globally located row; unknown action 400, missing row 404. Accept creates a notification for the caller, then commits; 200 `{ok:true}`. | A third user can accept/ignore somebody else's apparent request; repeated accepts repeat notifications. Accept does not create a connection row. |
| `POST /api/network/suggested/<sug_id>/connect` | Globally locates suggestion, sets `pending`, commits, 200 `{ok:true}`. | One caller changes everybody's suggestion; no recipient or actual request is recorded. |
| `POST /api/network/connections/<conn_id>/endorse` | Toggles shared `endorsed_by_me`, increments/decrements shared count, commits; returns `id`, `endorsements`, `endorsedByMe`. | A caller can undo another caller's endorsement; no sender, recipient, or enforceable uniqueness exists. Concurrent toggles can lose updates. |
| `GET /api/conversations` | Returns all conversations, each serialized with its entire message history. | Any account can read every thread without knowing a slug. |
| `GET /api/conversations/<slug>` | Global slug lookup, clears global `unread`, commits, returns full conversation. | Guessing a slug reads a stranger's history and clears their unread state. A GET mutates shared state outside unsafe-method CSRF enforcement. |
| `POST /api/conversations/<slug>/messages` | Trims `text`; blank 400. Global slug lookup; writes `who='me'`, then synthetic `who='them'` from `AUTO_REPLIES`, commits, emits to caller only, returns full conversation with 200. | Any active user can write to any thread; `who` cannot identify an author. No real recipient receives delivery; unread is not set by this handler. |

`NetworkRequest` stores display name, role, color, status and creation time, but no endpoint user IDs. `Suggested` has display fields/status only. `ConnectionNPC` has display fields, skill, aggregate count and a global boolean. `Conversation` has unique `slug`, name, color and a global unread boolean. `Message` has a conversation FK, `who`, text and time. `Conversation.to_dict()` returns `{id: slug, name, color, unread, messages}`; `Message.to_dict()` returns only `{who, text}`. These five legacy tables cannot prove an owner or author.

### Delivery, seed, and less obvious consumers

- `_join_authenticated_socket_rooms`, `on_connect`, and `on_join` derive `user:<id>` and `role:<role>` from the session, ignore supplied identity claims, and reject anonymous/suspended users on connect/join. There are no conversation membership rooms. A subsequent suspension does not itself disconnect an already connected socket. `notify_user` sends `new_message` only to the caller's user room, with `{conversationId, conversation: full_history}`. Correct room identity does not repair the HTTP leaks.
- `push_notification` adds/flushes a user-owned `Notification` and emits to its user room **before its caller commits**. A later rollback can therefore leave a client-visible notification that was never committed. Social request acceptance notifies the caller, not a verified requester. Message sending does not insert a persistent notification. [Notification routes](../forge_routes/notifications.py) separately scope reads to the caller and reject another user's notification mutation.
- `seed_demo_data` creates five request rows (two pending, three accepted), three suggestions, three NPC connections, and two conversations (`ayesha`, `apex`) with five messages. Normal seed entrypoints are development/demo gated. The rows have no provenance or owner FK, and can subsequently contain real typed messages. Matching display names or a greeting to Thabo is **not** evidence of ownership. Neither seed origin nor disposability may be assumed in a deployed database.
- [Static client](../static/forge_demo.html): `renderNetworkView`, `reqAction`, `connectSuggested`, and `endorse` consume those exact fields and send bodyless mutations. `renderMessagesView` uses the last element of each full `messages` array as its preview; `threadHtml` relies on GET clearing unread and `who` determining bubble direction. `sendMessage` sends only `{text}` and reloads the thread. `initSocket` joins without identity claims; it toasts/reloads on `new_message`. Notification bell unread is separate from conversation unread. All four roles see network/messages navigation. There is no create-thread UI or pagination.
- [Native API client](../mobile/src/api/client.js) and [Expo screen](../mobile/src/app/index.tsx) implement native authentication, profile/onboarding, feed, opportunities, and notifications, alongside a WebView fallback. They currently implement **no native networking, conversations, or Socket.IO messaging**. The WebView runs the same static client; its cookie session and the native session are separate. Do not describe current mobile as only a wrapper or bridge their credentials for this work.
- [Student analytics](../forge_routes/analytics.py), `student_analytics`, counts all accepted legacy requests plus all NPC connections, using request creation dates for its series. A secure social cutover must replace that input with the caller's accepted edges and acceptance dates, retaining the analytics response shape. Otherwise shared graph information survives outside the seven routes. This is future ownership work, not part of this documentation PR.
- Current profile export includes profile, notifications, coach messages, and applications, but does not export networking or conversations. Adding social export/erasure is a separate reviewed requirement; this proposal does not silently change the export contract.

This is source tracing, not a production exploit or production-data inspection. Existing socket/auth/CSRF tests cover their respective boundaries; they do not prove social isolation. Existing analytics regressions deliberately pin the current shared counts until an approved change replaces them.

## 2. Target model and invariants

**Recommendation:** user-to-user ownership, accepted-connection-only direct messaging, derived suggestions, and separate immutable-authored messages/per-member read cursors. This is not organizational tenancy: there is no verified organization-membership model. If school/company isolation is required, stop for a separate tenant model instead of treating a profile's campus/company text as an authorization boundary.

| Proposed entity | Fields and database constraints | Service rules in the same transaction |
| --- | --- | --- |
| `network_edge` | Integer ID; `user_low_id`, `user_high_id` FKs; `CHECK(low < high)`; unique pair. Explicit `requester_id`, `recipient_id` FKs with CHECK that they are exactly the two endpoints. State enum `pending/accepted/ignored/cancelled/disconnected`; integer `version >= 1`; `created_at`, `requested_at`, `updated_at`, nullable `accepted_at`, `ended_at`; `changed_by_user_id` FK. | One row represents both a request and its resulting relationship. Actor and changed-by come from session. Terminal-state re-request reuses this pair row with a higher version; audit preserves prior cycles. Creation time never changes. Accepted time is populated only for accepted state; terminal time for terminal state. |
| `endorsement` | Integer ID, `network_edge_id` FK, `endorser_id`, `recipient_id` FKs, non-null `skill_key` (empty string means general), optional display label, `version`, `created_at`, `updated_at`, nullable `revoked_at`. Unique `(endorser_id, recipient_id, skill_key)` and CHECK sender differs from recipient. | Endpoints must match the edge. Only the endorser can activate/revoke; activation requires an accepted edge and both active accounts. No stored aggregate or shared `endorsed_by_me`. Derive the viewer's flag from active rows. Initially expose only the caller-to-peer general endorsement count (0 or 1), not endorsements from unrelated edges; a public reputation aggregate needs a separate visibility decision. Disconnect revokes active endorsements in both directions atomically, incrementing their versions and recording each revocation event. |
| `direct_conversation` | Integer ID; opaque randomly generated unique `public_id`; canonical low/high user FKs, unique pair, CHECK low < high; `created_by_user_id` FK constrained to endpoint; timestamps; `last_seq >= 0`. | Only the session actor and one selected peer can form a pair. Accepted edge and active accounts required to create. Concurrent creation converges to one row. Reconnection reuses the same conversation; no group-chat membership changes. |
| `conversation_member` | Composite PK `(conversation_id, user_id)`, FKs, `joined_at`, `last_read_seq >= 0`, nullable `read_at`. | Exactly two members, equal to the conversation endpoints, inserted atomically with creation. No client-controlled join/leave/invite. Endpoint-check triggers plus restricted membership writes prevent outsiders; a simple CHECK cannot enforce the two-row count, so transaction logic and validation must enforce it too. |
| `direct_message` | Composite PK `(conversation_id, seq)`; `sender_id`; composite FK `(conversation_id, sender_id)` to member; required `client_message_id`; unique `(conversation_id, sender_id, client_message_id)`; text and `created_at`. | Nonblank trimmed text, proposed maximum 4,000 characters. Allocate next sequence and insert in one serialized write transaction. Immutable sender/text; `who` is computed relative to the authenticated viewer. No synthetic reply in real conversations. |
| `ownership_event` | Integer ID; exactly one of `network_edge_id`, `endorsement_id`, `conversation_id` (FKs); actor user FK; entity version, event type, previous/next state, UTC timestamp. Separate unique indexes per entity/version/event type; CHECK exactly one entity FK. | Append transition/create/revoke audit in the same commit, without message bodies or credentials. Message author/time/key already provide message provenance. Audit is not a delivery queue or permission to expose activity publicly. |

New references use `ON DELETE RESTRICT`, not cascade/SET NULL. Index both endpoint lookup directions/state, recipient/state request lookup, active endorsement recipient/context, member user/conversation, and message conversation/sequence; uniqueness supplies pair and retry indexes. Social integer IDs must not be reused; public conversation identifiers are opaque, but secrecy is never authorization. All times are server-generated UTC. SQLite constraints, triggers, and `PRAGMA foreign_keys=ON` need migration review; current `_set_sqlite_pragma` configures WAL/synchronous but does not explicitly enable foreign keys.

Suggestions are a query over active users with `profile_visible=true`, using the ordinary public-profile field visibility rules without the admin inspection bypass: exclude self, accepted/pending pairs, and ineligible targets. Return only already-discoverable profile fields; never reveal hidden profiles through suggestion counts, sorting, or errors. No new suggestion table or copied NPCs. Selection is revalidated at request time. Terminal pairs may reappear only after a proposed 24-hour cooldown; do not disclose whether the peer ignored a request. Product approval is required for cooldown and discovery policy.

Initially use general endorsements (`skill_key=''`) in the existing button. Future explicit skill context normalizes a submitted skill using NFKC, trim, and case-fold, validates it against the recipient's current skills, and stores a stable key/label. Removing a profile skill does not rewrite historical endorsement context. Enabling skill-specific endorsement UI is a separate compatibility step; arbitrary recipient/sender claims are never accepted.

### State transitions and retries

| Existing state | Actor / operation | Result |
| --- | --- | --- |
| No edge | Active discoverable A requests B | Pending, requester A/recipient B, version 1. Self-request rejected. |
| Pending | Recipient accepts / ignores | Accepted / ignored; increment version, set relevant timestamp, append audit. |
| Pending | Requester cancels | Cancelled; increment version and audit. |
| Pending | Either side tries to create an opposite request | Do not auto-accept or insert a second edge. Same-direction repeat returns existing pending edge; opposite-direction create conflicts without changing it. |
| Accepted | Either endpoint disconnects | Disconnected; increment version; revoke endorsements; history stays readable to members, new sends stop. |
| Terminal | Eligible endpoint explicitly re-requests after cooldown | Pending with new requester/recipient direction, higher version and request time; clear current acceptance/end time, preserve audit. |

Transitions require `expectedVersion`. Missing version yields 428; stale version yields 409 and no writes/notifications. Repeating an already committed accept with its old version yields 409, not another notification. Request creation uses `expectedVersion:0` for an absent pair; terminal retries require the visible terminal version. Same-direction pending repeat can return the existing pending result without mutation. A stale create must never resurrect a cancelled/ignored request. Disconnect/revoke remain available to an active endpoint even when the peer is suspended.

Endorsement mutation sets a desired boolean, never toggles implicitly. Use `expectedVersion:0` for a never-existing endorsement; otherwise require its current version. A repeat already in the desired state may return the current result without side effects; changing state with a stale version conflicts. The server selects the counterpart of the supplied edge as recipient.

### Reading, suspension, deletion, and concurrency

Unread is the count of messages from the other member with `seq > last_read_seq`. Pure GETs never advance it. Explicit read advances monotonically to an observed sequence in that same conversation, bounded by its current last sequence. Sending does not advance read state and cannot clear earlier unseen incoming messages. Another participant's cursor is not returned by default; public read receipts need product approval.

An active member may read retained history after disconnection or peer suspension, with minimal/generic peer presentation when necessary. Creating a thread, sending, and activating an endorsement require an accepted edge and active peer; known members receive a generic 409 `operation unavailable` when that condition fails. Do not disclose a moderation reason. A suspended actor gets 403, including existing sessions. Missing/deleted actor gets 401. No admin bypass permits private conversation inspection, forced joining, or endorsement impersonation; an admin who is a legitimate participant has ordinary participant rights. Existing account moderation remains separate.

Retain referenced user identity and history pending an approved retention/erasure design. The current admin `remove` handler attempts hard delete then falls back to suspension on failure. New RESTRICT constraints can change that behavior, so enabling them requires explicit review of admin-removal outcomes and user messaging; this package does not implement a new deletion policy. Dangling or inconsistent membership fails closed and raises an operational integrity alert, never grants fallback access.

Later mutation services must serialize their authorization read and writes inside one SQLite write transaction (for example `BEGIN IMMEDIATE`, integrated correctly after the existing login guard's last-seen commit). Check actor, peer, edge state/version and membership again inside that transaction. Pair unique constraints settle opposite requests and duplicate thread creation. Sequence allocation and message insertion are atomic. After checking current actor and membership, the same `(conversation, sender, client_message_id)` with identical normalized text returns the original message, even if the edge has since disconnected (it performs no new send); different text yields 409. Read uses a monotonic maximum in its write transaction. Suspension/disconnect racing a send serializes: a committed earlier send is retained; a send authorized after revocation is denied. Database rollback produces no success event. Do not promise recall of an already committed/delivered message.

## 3. Authorization matrix

The existing authentication/CSRF checks remain in front of these proposed handlers. The matrix assumes an unsafe authenticated request has valid CSRF and origin; otherwise existing CSRF rejection can precede route authorization. Resolve membership before returning object content or detailed object-dependent validation. Malformed syntax can return 400 without disclosing whether an object exists.

| Operation | Anonymous / missing user | Authorized active caller | Other active caller | Suspended actor | Admin |
| --- | --- | --- | --- | --- | --- |
| List network/suggestions | 401 | Only own incoming/outgoing edges, own connections, eligible suggestions | Gets own projection, never others' graph | 403 | Same ordinary scope |
| Create/re-request via suggestion | 401 | Session actor to eligible target, rules above | Hidden/missing/self-ineligible target: generic 404; cannot nominate another requester | 403 | Same rules |
| Accept/ignore request | 401 | Recipient only | Requester sees 403; outside pair gets concealed 404 | 403 | No override |
| Cancel request | 401 | Requester only | Recipient 403; outside pair 404 | 403 | No override |
| Disconnect edge | 401 | Either endpoint | Outside pair 404 | 403 | No override |
| Activate endorsement | 401 | Session endorser on accepted edge to active peer | Outside edge 404; cannot supply another sender/recipient | 403 | No override |
| Revoke endorsement | 401 | Its endorser, including after disconnect | Known recipient 403; outsider 404 if directly addressed; existing edge button always targets caller's own endorsement | 403 | No override |
| List conversations | 401 | Only caller's membership projection | Returns own list, no foreign counts/previews | 403 | Same ordinary scope |
| Create direct conversation | 401 | Session actor + accepted active peer | Ineligible/non-discoverable target 404; known but unavailable relationship 409 | 403 | No override |
| Read detail/history | 401 | Member, including read-only disconnected history | Nonmember and nonexistent slug both 404 | 403 | Member only |
| Send message | 401 | Member plus accepted edge/active peer | Nonmember 404; known read-only member 409 | 403 | Same rules |
| Advance read cursor | 401 | Member, own cursor only | Nonmember 404; cannot update peer cursor | 403 | Same rules |
| Socket connect/join | Reject | Session-derived own rooms only | Forged user/role/conversation claims ignored/rejected | Reject | Own rooms only |
| Social socket/notification delivery | None | Only active intended participants/recipient | No payload, count, or existence hint | No live delivery | No monitoring bypass |

Never accept `actorId`, `senderId`, `requesterId`, `who`, ownership, role, or room claims as authority. A target-user selector is not an actor selector. Reject unsupported identity fields with 400 under the new contract. Use identical concealed-404 body/status for nonexistent and unauthorized objects; do not distinguish via message counts, pagination totals, notification previews, or cursor validation. Filter before ordering/limiting/counting. Private responses use `Cache-Control: no-store`. Opaque cursors must be scoped to the authenticated user and, for history, the conversation; foreign cursors give a generic 400 without querying/disclosing their target. Rate limits against guessing/request spam require a separately verified deployment plan and are not a substitute for authorization.

## 4. API and client transition — proposed contract boundary

Ownership filtering alone changes what users see; several safe semantics also require explicit contract changes. **Do not silently deploy these under the current contract.** Recommend a coordinated ownership-v2 capability header `X-Forge-Ownership-Version: 2` on the affected paths, preserving route paths. After cutover, missing/unsupported capability gets 426 `{error:"ownership client update required"}` after existing auth/CSRF checks and before object lookup. The header is compatibility negotiation, not permission. An old NPC numeric ID must never be interpreted as a real user ID from a cached bodyless request. A versioned URL alternative requires a different approved decision before implementation; do not support two writable social graphs.

| Current endpoint | Proposed v2 mapping | Compatibility classification |
| --- | --- | --- |
| `GET /api/network` | Retain root `requests/suggested/connections`; requests are incoming only; add `outgoingRequests`. Retain eligible display fields and lifecycle presentation (with concealed terminal outcomes); add `counterpartUserId`, `direction`, `version`. Connection ID identifies the edge; derived `endorsements/endorsedByMe` refer only to caller-to-counterpart/general context (count 0 or 1); add `endorsementVersion` (0 if absent). Suggestions use real target user IDs and include `edgeVersion` (0 if absent). | Additive fields, but filtered contents and ID meanings require the v2 boundary. Terminal request outcomes use a generic ended presentation for the requester rather than disclosing ignore/moderation reason. |
| `POST /api/network/requests/<id>/<action>` | Existing accept/ignore plus proposed cancel/disconnect actions; `{expectedVersion}`; 200 `{ok:true, version}`. Session/pair role controls action. | Required body, state checks and 403/409/428 are deliberate changes. |
| `POST /api/network/suggested/<id>/connect` | ID is eligible target user; `{expectedVersion}`; create/re-request or return own pending edge, 200 `{ok:true, requestId, version}`. | ID namespace and required precondition change; no legacy fallback. |
| `POST /api/network/connections/<id>/endorse` | `{endorsed: true/false, expectedVersion}`; general context only initially. Return existing three fields plus endorsement `version`. | Explicit desired state replaces unsafe toggle; skill context needs a later explicit field/UI agreement. |
| `GET /api/conversations` | Retain array root and `id/name/color/unread/messages`; only caller's threads. `messages` contains at most the latest preview. Add `unreadCount`, `lastSequence`, `readOnly`. Default/max 50 rows, stable ordering by conversation ID, scoped `cursor` query and `X-Next-Cursor` response header. | Bounded history and pagination change assumptions; web must page. No foreign threads/totals. |
| `GET /api/conversations/<slug>` | Same object root; latest 50 messages in ascending sequence, optional scoped `before` cursor for older pages. Add `hasMore`, `nextCursor`, `lastSequence`, `lastReadSequence`, `readOnly`. Each message retains viewer-relative `who/text`, adds `sequence`, `createdAt`. | GET becomes pure; full-history assumption removed; names/colors derive from authorized counterpart profile, not NPC snapshots. |
| `POST /api/conversations/<slug>/messages` | `{text, clientMessageId}` (UUID generated once per user submission and retained across retries). First commit 201, duplicate 200; `{conversationId, message:{sequence,who,text,createdAt}, lastSequence}`. | Deliberate status/shape/input changes; no automatic reply or returned full history. |
| New `POST /api/conversations` | `{targetUserId}`; derive own pair. 201 for creation, 200 for existing authorized pair; returns detail projection. | New endpoint/UI workflow; no group membership API. |
| New `POST /api/conversations/<slug>/read` | `{upToSequence}`; authenticated CSRF-protected; 200 `{lastReadSequence, unreadCount}` for caller. Zero permitted for an empty thread; otherwise sequence must exist in this thread. | Replaces GET side effect; concurrent advancement cannot move backward or consume later messages. |

All proposed list limits reject invalid/out-of-range values with 400; no unbounded full-history fallback. Network lists likewise need bounded sections with per-section scoped cursors (add `nextCursors` under the retained root, limit 50 per section); existing web must support loading each section. Exact opaque cursor encoding is an implementation choice, but its user/conversation scope is a security invariant.

Web work later: send capability/precondition bodies; represent incoming vs outgoing requests; handle stale-version reload without replaying intent; use explicit desired endorsements; add real-peer conversation creation; page history/previews; only mark rendered/observed messages read; preserve one message UUID across transient retries; avoid rendering a late response after account switches; clear account-scoped state/cursors on logout. Retain CSRF/session helper behavior and same-origin requests. Handle 426 with a refresh/update explanation, not repeated writes; handle read-only peers without revealing moderation state. Remove synthetic-reply expectations only at approved cutover.

The WebView receives the same web changes and needs cold/cached-page tests. Native messaging is still blocked: future native adapters must implement this contract, cookie/CSRF behavior and caller-scoped cache, with native/WebView session separation intact. Existing native notifications retain their `{id,type,text,link,read,createdAt}` shape. No native messaging feature is implemented by this design.

### Participant-safe events and notification flow

For a committed real message, use `new_message` as a minimal invalidation `{conversationId, lastSequence}`; no full conversation/text, actor-provided room, or role broadcast. Reuse session-bound user rooms, resolving only actual active members at emission time. The sending user's other devices may receive the invalidation; only the other member receives a persistent generic new-message notification. Request notifications go to the actual recipient on request creation and requester on acceptance, once per successful transition. Text must not expose private message content; links are authenticated destinations, never bearer credentials.

Insert notification rows in the business transaction, commit, then emit. Do **not** reuse the current pre-commit-emitting `push_notification` unchanged for these writes. A narrowly scoped future helper can separate persistence from emission without refactoring unrelated notification behavior here. Socket delivery is best effort: a crash after commit may lose the event, while HTTP refresh recovers persisted messages/notifications. Retry keys prevent duplicate durable effects, not exactly-once transport. No new queue/service is required.

Recheck active account and membership before delivery; on suspension/deletion disconnect that user's known sockets and prevent rejoin under invalid identity. Client logout must close its socket. Global revocation of copied signed cookies is not provided by the current session model and is outside T-104; stronger logout/session revocation requires separate D-006 review, not an invented session registry in this design. Role rooms must never carry private social events. A socket already queued before revocation cannot be recalled; minimal invalidations contain no message text, and subsequent HTTP reads reauthorize. Current single-process delivery assumptions must be revisited before multi-worker deployment. A conversation slug in a generic notification still requires membership on navigation; no notification endpoint becomes an alternate history reader.

## 5. Staged SQLite migration and rollback plan (not executable here)

T-201 must supply reviewed migration tooling/version tracking and a rehearsed restore procedure. `db.create_all()` is not a migration strategy. No SQL below has been run on an application database for this task. No legacy owner is inferred from name, role, color, unread, `who`, message contents, or seed templates.

| Stage / approval gate | Proposed work and validation | Safe rollback |
| --- | --- | --- |
| 0 — approve D-012–D-015 | Decide user-vs-organization scope, discovery/cooldown, connected-only messaging, retention/admin removal, contract boundary and maintenance window. Inventory row counts, FK orphans, indexes and SQLite version on a controlled copy. Take a consistent SQLite backup using its backup mechanism with WAL handled correctly; rehearse restore and verify checksums/counts. | No deployment change. Retain original and tested backup. Stop on unexplained corruption/ownership evidence. |
| 1 — containment-ready release | Prepare a reviewed feature/maintenance gate and compatible client; disabling social routes returns authenticated 503, never falls back to shared rows. Production rollback artifact must contain the gate. Old-client capability rejection prepared. | Keep social routes unavailable if a safe compatible release cannot serve them; do not restore insecure shared access merely for availability. |
| 2 — additive schema, T-201 approval | Add the six tables, indexes, checks, triggers and migration ledger under migration tooling. Enable FK enforcement on every connection only after whole-schema orphan/deletion-impact review. Rehearse transactional DDL behavior for supported SQLite. No legacy drop, rename, or destructive alteration. | Leave additive tables inert and gated. Before any new writes an independently tested down migration may remove only empty new objects; leaving them is safer. Never disable integrity silently to pass deployment. |
| 3 — quarantine / optional verified import | Keep all five legacy social tables intact, unavailable through user APIs. New graph starts empty. No dual-read, union, or dual-write. An exceptional import needs independently verified endpoint identity and authorship for every imported record, an approved mapping manifest, provenance, dry-run reconciliation and rejection report. Ambiguous conversations remain quarantined in full. Create synthetic fixtures only in isolated dev/test DBs. | Discard only unexposed dry-run output; retain legacy and manifest. If an import has been exposed/written onward, treat it as new live data and preserve it. No guessed reverse transform. |
| 4 — implementation rehearsal | Future tests below pass on migrated copies. Update all seven routes, new endpoints, web/WebView, socket/notification consumers and shared student-analytics input together behind gate. Native social adapters remain blocked until ready. Verify no legacy reads/writes in new social/analytics paths. | Gate off; preserve new rows, cursor state, notifications and audit. No stale-client access to old graph. |
| 5 — approved cutover | Quiesce legacy writes, snapshot/count/checksum again, run invariants, enable v2-only social operations. Monitor concealed denials, conflicts, FK errors and delivery failures without bodies/tokens. No mixed legacy/v2 writable cohorts. | Before new writes: gated prior compatible artifact. After new writes: compatible secure rollback artifact or maintenance 503, preserving all new data. Never restore a pre-cutover snapshot over newer messages or export back into ownerless tables. Restore to an isolated recovery copy first and reconcile approved recovery. |
| 6 — later retention review | Legacy cleanup, identity anonymization, permanent erasure, audit retention and old-table removal require a **separate human-approved policy**, verified backups and recovery testing. Not part of T-104/T-201's additive cutover permission. | Do not start irreversible cleanup without its own recovery/retention approval. A backup is not justification to discard new writes. |

Foreign-key enforcement affects all 23 existing tables, not just new ones. If existing data fails `foreign_key_check`, stop and document affected references; do not auto-delete or assign owners. Review the existing admin-remove fallback before rollout. A migration requiring repairs to unrelated tables or a different authentication/organization model is a new architecture decision, not an implementation detail.

### Planned validation queries and invariants

These are review examples against the **proposed** names, not migration scripts. T-201 must make them repeatable, include fixture failures, and fail the rollout if any invalid-row query returns rows.

```sql
PRAGMA foreign_keys;       -- must be 1 on every application/migration connection
PRAGMA foreign_key_check; -- must return no violations, including legacy references

SELECT user_low_id, user_high_id, COUNT(*)
FROM network_edge GROUP BY user_low_id, user_high_id HAVING COUNT(*) > 1;
SELECT id FROM network_edge
WHERE user_low_id >= user_high_id
   OR NOT ((requester_id = user_low_id AND recipient_id = user_high_id)
        OR (requester_id = user_high_id AND recipient_id = user_low_id));

SELECT user_low_id, user_high_id, COUNT(*)
FROM direct_conversation GROUP BY user_low_id, user_high_id HAVING COUNT(*) > 1;
SELECT c.id FROM direct_conversation c
LEFT JOIN conversation_member m ON m.conversation_id = c.id
GROUP BY c.id HAVING COUNT(m.user_id) != 2
 OR SUM(CASE WHEN m.user_id IN (c.user_low_id, c.user_high_id) THEN 1 ELSE 0 END) != 2;

SELECT d.conversation_id, d.seq FROM direct_message d
LEFT JOIN conversation_member m
 ON m.conversation_id = d.conversation_id AND m.user_id = d.sender_id
WHERE m.user_id IS NULL;
SELECT c.id FROM direct_conversation c
LEFT JOIN direct_message d ON d.conversation_id = c.id
GROUP BY c.id HAVING c.last_seq != COALESCE(MAX(d.seq), 0)
 OR COUNT(d.seq) != c.last_seq;
SELECT m.conversation_id, m.user_id FROM conversation_member m
JOIN direct_conversation c ON c.id = m.conversation_id
WHERE m.last_read_seq < 0 OR m.last_read_seq > c.last_seq
 OR (m.last_read_seq > 0 AND NOT EXISTS (
   SELECT 1 FROM direct_message d
   WHERE d.conversation_id = m.conversation_id AND d.seq = m.last_read_seq));

SELECT e.id FROM endorsement e JOIN network_edge n ON n.id = e.network_edge_id
WHERE NOT ((e.endorser_id = n.user_low_id AND e.recipient_id = n.user_high_id)
        OR (e.endorser_id = n.user_high_id AND e.recipient_id = n.user_low_id))
 OR (e.revoked_at IS NULL AND n.state != 'accepted');
```

Also verify allowed state/timestamp combinations, monotonically increasing versions, one matching audit event per committed transition, retry-key uniqueness, nonempty/length-limited text, and notification recipients tied to committed events. Active endorsements may be retained during peer suspension but must be hidden from public projections and cannot be activated while suspended; disconnection revokes them. Validate every legacy table's count and deterministic content digest before/after additive migration. Assert no target FK references a legacy social table and exercise query traces proving no legacy data is returned. Compare current unrelated route contracts/schema objects with the approved baseline; do not assert the new social contract is byte-compatible. No missing-data default may return legacy histories or shared counts.

## 6. Threat model and required future tests

Use independent active users **A, B, C**, plus admin D, with distinct cookies/CSRF tokens and deliberately overlapping display names. Establish only A–B; C guesses every ID/slug and changes every actor-like field. Add suspended and removed-user sessions. Use isolated SQLite databases and existing Flask/Socket.IO/Node harnesses; no production testing with private messages.

| Threat / invariant | Required regression or integration evidence before implementation approval/cutover |
| --- | --- |
| ID/slug guessing; cross-user history and graph enumeration | Exercise every matrix row for anonymous, A/B/C, suspended actor, nonparticipant D and participant D. Lists, detail, page cursors, previews, counts, errors and cache headers must reveal only authorized data. Missing and C-accessed resources have equal concealed-404 shape; denied writes leave all rows/cursors/audit/notifications unchanged. |
| Forged requester/author/endorser/room | Send A's request with C's claimed IDs, `who`, role and rooms; reject unsupported fields and never store claims. Assert message author is A, endorsement recipient is edge counterpart, and no socket joins C/admin rooms. Keep all existing CSRF/origin tests and add each new unsafe endpoint. |
| Requester accepts own request; third party accepts another's | A cannot accept A→B; C cannot act; B accepts only pending/current version. Ignore/cancel/disconnect role/state matrix, terminal cooldown and stale resurrection denied. Repeated accept never duplicates audit/notification. |
| Opposite-direction connection and duplicate direct pair races | Independent SQLite connections synchronize simultaneous A→B/B→A and A/B thread creates. Assert one pair, no implicit acceptance, exactly two correct members, deterministic conflict/existing result, and no orphan notifications. Unique violations roll back cleanly. |
| Sending without membership or after revocation | C cannot send/read even with a valid slug; disconnected/suspended peer denies new send but permits A's retained history. Interleave suspend/disconnect and send transactions; no send authorized after committed revocation. Missing/corrupt membership fails closed. |
| Lost/forged unread state | B receives multiple A messages; A cannot clear B's cursor. GETs are side-effect-free. Older read racing new message leaves new message unread; reversed read completions never decrease cursor; send does not consume incoming unread; foreign/future sequences denied. |
| Endorsement impersonation, toggle races and count drift | A and C's endorsements cannot overwrite one another; unique sender/recipient/context, repeated desired state and stale opposite-state writes behave as specified. Disconnect versus activation serialized; no active endorsement survives disconnect. Derived count matches rows and viewer flag; skill normalization tested before enabling that context. |
| Retry duplicates and partial failure | Concurrent same message UUID/text commits one message and one recipient notification; different text conflicts. Two different sends get distinct ordered sequences. Inject failures before commit: no message/notification/audit/event. Inject emission failure after commit: HTTP reconciliation succeeds, retry adds no duplicate. |
| Stale sessions/sockets, role-room leakage | Reject suspended/missing user on HTTP/connect/rejoin. Connect first then suspend/delete; disconnect affected sockets and prevent unauthorized delivery/rejoin. Verify client logout closes its socket; do not claim global signed-cookie revocation. A/B receive only intended invalidations, C/admin role rooms none. Notification contents and links cannot leak history; all subsequent fetches reauthorize. Test limits of already queued events explicitly. |
| Destructive deletion / ambiguous seed import | Referenced identity cannot cascade-delete history; verify approved admin-remove outcome. Seed-like names and `me/them` alone never backfill owners. Mixed demo/real legacy contents remain unchanged/quarantined. Invalid mapping manifest stops import; no partial promotion. |
| Migration and rollback | Test clean and populated legacy DBs, orphans, duplicate pair attempts, bad member/author FK, all SQL invariants, repeated migration execution/version guard, interrupted DDL, backup restore and rollback before/after new writes. Gate must never fall back to legacy data. New writes survive rollback drills; unrelated schemas/contracts stay intact. |
| Web/WebView/native compatibility | Actual web functions send capability/preconditions/CSRF, page previews/history, mark only observed messages read, retain send UUID, handle 401/403/404/409/426/428/503, and clear account caches/late responses. Cached old web/WebView mutations cannot target new ID namespace. Test narrow screen/keyboard paths. Native current workflows/notification shape remain passing; signed-device WebView/native-session checks required before release. |
| Hidden analytics leakage | A/B/C student dashboard uses only own accepted edges and acceptance dates. Replace shared-count expectations intentionally under approved ownership work; retain unrelated T-106 metrics and response shapes. No legacy count fallback on an empty new graph. |

Existing suite execution on this docs-only branch protects the current baseline; it does **not** prove this future model, migration or race plan implemented. Add executable security tests before later runtime edits, then make each migration/service/client increment reviewable. Independent-connection race tests are required: a single rolled-back fixture transaction cannot establish concurrency correctness.

## 7. Review decisions and implementation gates

The recommendations below intentionally expose choices that current source cannot settle. Approval must name the selected alternative; developers must not infer a policy from a sample schema.

| Human choice | Recommendation and cost | Alternative and tradeoff |
| --- | --- | --- |
| Relationship representation | One unique pair edge plus audit; few tables and straightforward opposite-request exclusion. | Separate request/connection entities preserve request attempts directly, but need cross-table uniqueness and reconciliation. |
| Who may message | Accepted peers only; predictable consent boundary but requires a connection workflow. | Discoverable strangers may initiate; needs approved inbox/spam/blocking policy before launch. |
| Discovery/reputation | Public-profile suggestions, 24-hour terminal cooldown, general private pair endorsement count; avoids a new public graph leak. | Persist curated suggestions or expose public skill reputation; requires ownership, freshness, consent and visibility rules. |
| Legacy data | Quarantine, preserve, start owned graph empty; old history disappears from ordinary UI. | Evidence-based per-record import costs manual verification; automatic name-based import is unsafe. Discard requires a separate retention decision. |
| API boundary | Capability header preserves paths but requires explicit client negotiation and coordinated cache handling. | `/api/v2` paths make version separation obvious but duplicate routing/client surface during transition. Neither permits legacy shared writes. |
| Deletion/admin access | Restrict referenced identity deletion, no private-data admin bypass; erasure/support requests may need a later workflow. | Anonymization or audited support access needs explicit policy, actor retention rules and new authorization tests; it cannot be inferred here. |
| Availability during rollback | Maintenance response preserves confidentiality/data while recovery runs. | Continuous availability requires a compatible secure rollback release validated in advance; ownerless fallback is not acceptable. |

Reviewers should explicitly accept or amend each of the following before any production work:

1. **D-012 / ownership:** user pair model, accepted-only direct messaging, immutable authors, per-member read state, no admin private-data override; whether organizational isolation is actually required.
2. **D-013 / data safety:** retain and quarantine all unprovable legacy rows; no guessed import, dual-read or dual-write; RESTRICT identity references and separate retention/erasure review.
3. **D-014 / compatibility:** coordinated v2 capability boundary, exact deliberate semantic/status/body changes, explicit reads, idempotent sends, bounded results and generic socket invalidations; maintenance rather than unsafe fallback.
4. **D-015 / sequencing:** T-201 migration tooling and whole-schema FK review first, then regression-protected model/service/API/client increments; backup/restore and revocation/delivery tests before enablement. Approve discovery/cooldown, text limit and general endorsement launch policy.

This PR submits the design for architecture review only. It neither approves those decisions nor completes their implementation. Stop and record any request to change production schema/runtime, decide permanent retention, broaden to tenant/auth architecture, or infer ownership without evidence. No merge is authorized by this task.
