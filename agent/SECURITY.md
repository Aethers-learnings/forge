# Security

Status: discovery findings with T-001 through T-005 roadmap P0 resolutions verified as of 2026-09-24. Open findings and implementation evidence are distinguished below.

## P0 — verified findings

1. **Resolved — T-001: predictable fallback Flask secret.** Production startup rejects absent, historical/default, and short secrets; development uses a process-local random key. Production session cookies are Secure, HttpOnly, and SameSite=Lax. Configuration regressions remain passing in the full suite. Classification: SAFE_INCREMENTAL.

2. **Resolved — T-002: Socket.IO room selection and permissive CORS.** Connections reject anonymous and suspended sessions. User and role rooms derive exclusively from `current_user()` / authenticated Flask session identity; client-supplied `userId` and `role` claims are ignored. Removed wildcard `cors_allowed_origins` to restore default same-origin checking. `static/forge_demo.html` emits `join` without identity claims. Added `tests/test_socket_security.py` for connection rejection, user/role isolation, forged join claims, and absence of wildcard origins. Full host suite: 15 passed in 1.86s, 17 non-blocking deprecation warnings. The origin test checks configuration; it is not a browser handshake integration test. Classification: SAFE_INCREMENTAL.

3. **Resolved in implementation — T-004 mobile transport/navigation.** Build-time exact HTTPS origins have no default. The policy rejects malformed/ambiguous URLs, credentials, non-HTTPS schemes, deceptive subdomains and unconfigured effective ports/IP origins. Explicitly configuring an HTTPS IP origin authorizes only that origin/port. Persisted values, Connect/save, initial source and navigation share the guard. Invalid saved values remain in recoverable settings without loading or automatic replacement. Classification: SAFE_INCREMENTAL.

   Android cleartext is disabled by a supported Expo manifest plugin, with no network-security-config override (the unsupported app.json field was removed). iOS ATS allows neither arbitrary loads, web-content exceptions nor local-network exceptions. Mixed content is `never`; popup callbacks discard every target, automatic JS windows are disabled, and Android multiple-window interception is enabled. Subframe navigation callbacks are denied.

   `originWhitelist=['*']` routes schemes through the exact policy callback, because installed react-native-webview otherwise sends whitelist rejections to OS Linking. It is not the authorization boundary. Native popup handlers were inspected. This is a navigation policy, not an HTTPS subresource/JavaScript network firewall; CSP remains separate backend work.

   Development origins require build profile `development`, `FORGE_MOBILE_DEVELOPMENT=1` and runtime `__DEV__`; they still require HTTPS and retain native restrictions. Preview/production ignore them. 33 mobile tests, lint, TypeScript and native preview/production introspection pass; signed release-device checks remain required.

4. **Resolved — T-003: CSRF/origin protection for authenticated unsafe API requests.** A `before_request` guard covers `/api/` requests with session `user_id`, except GET/HEAD/OPTIONS/TRACE. It requires `X-CSRF-Token` matching the random token stored in the signed Flask session and bound to that user ID, using constant-time `secrets.compare_digest`. Tokens use `secrets.token_urlsafe(32)`, rotate on register/login/demo-login, and are removed on logout or invalid-session cleanup. Authenticated `GET /api/auth/csrf-token` returns `csrfToken` with `Cache-Control: no-store`. Classification: SAFE_INCREMENTAL.

   Origin is authoritative when present; Referer is used only when Origin is absent. Scheme, hostname and effective port must match the direct WSGI request scheme/Host. Foreign, null, malformed, credential-bearing origins and requests missing both headers are rejected with 403 before route processing. Forwarded/X-Forwarded headers are ignored; no ProxyFix is installed. A TLS-terminating proxy that changes the scheme/Host visible to Flask requires separately reviewed deployment integration.

   The static API helper attaches tokens for authenticated POST/PUT/PATCH/DELETE; direct multipart upload adds the same header without overriding Content-Type. Client token state resets on authentication identity/session changes, logout, and CSRF rejection, with concurrent acquisition deduplication and stale-response protection. Unsafe requests are not automatically replayed. Failed logout does not falsely clear the logged-in UI.

   Anonymous login, registration, demo-login and password-reset behavior is unchanged and requires no CSRF token. Those routes are protected when an authenticated session is present. This change covers authenticated unsafe API requests; it does not redesign anonymous authentication, safe-method semantics, signed-cookie revocation, or the authentication architecture. Full suite: 56 passed, 179 existing deprecation warnings in 10.49s. T-005 is next P0.

5. **Resolved — T-005: debug/demo deployment configuration.** `FORGE_DEBUG` and `FORGE_DEMO_MODE` default off and are accepted only with `FORGE_ENV=development`. Flask debug mode alone does not expose `/api/auth/demo-login`; demo login, the `seed-demo` CLI command, and startup demo seeding require explicit demo mode. Environment names and boolean switches are parsed fail-closed. Unknown/misspelled environments are rejected. Staging and production/prod require a non-default secret of at least 32 characters and Secure session cookies; the documented placeholder secret is also rejected. Regression coverage includes direct configuration behavior and production import failure. Classification: SAFE_INCREMENTAL.

6. **Resolved — T-102: upload boundary and serving authorization.** Video uploads now have a multipart request-size ceiling plus bounded streamed file writes capped at 50 MiB. Supported extensions must match an expected container signature family (ISO-BMFF, EBML, or AVI). When ffmpeg is available, processing failures fail closed instead of publishing the original; when ffmpeg is unavailable, only signature-validated originals are retained with a placeholder thumbnail. Upload storage is configurable and isolated in tests. `/uploads/<path:name>` now requires authentication, only serves files referenced by active non-removed media posts, enforces the same role-feed boundary as the feed for non-admin users, and permits admin moderation access. Soft removal revokes serving immediately but deliberately retains bytes because irreversible deletion requires a separately approved retention policy. Classification: SAFE_INCREMENTAL.

## High-priority verified concerns
- Login throttling is in-process and keyed only by username; it is lost across restarts and does not provide distributed/IP-aware protection.
- Resolved — T-103: password-reset tokens are stored only as SHA-256 digests. The plaintext token is returned only by explicit local debug behavior, which is prohibited outside development by T-005. SMTP absence/failure has a minimal operational log without recipient, subject, body, exception, or token contents. In non-debug with no SMTP configured, reset delivery is intentionally unavailable while the generic response prevents account enumeration.
- Upload validation is currently shallow container-signature validation, not malware scanning or deep media validation. Soft-removed media bytes are retained after access is revoked; any automated physical deletion/retention lifecycle is intentionally deferred until an irreversible-data policy is approved.
- Data ownership is incomplete for network requests, suggested users, connection endorsements, and conversations: all authenticated users read/mutate shared rows. This is both an authorization defect and a data-model limitation.
- Security headers, HTTPS enforcement, CSP, and a reviewed proxy trust policy remain outstanding. T-001 now explicitly configures production Secure/HttpOnly session cookies. The static client uses `innerHTML`; output escaping exists in client helpers but needs regression coverage.
- External SMTP and the optional Anthropic call are synchronous request-path integrations. Mail bodies and errors can be logged when SMTP is absent/fails; coach history is sent to the provider when configured. Define consent, data minimization, audit, timeouts, and failure handling before production use.

## Existing protections observed

- Passwords use Werkzeug hash/check helpers; admin is excluded from public self-registration and provisioning requires a server-side secret.
- Most API routes call `require_login()` and role-gated admin/business/student routes return 403 for wrong roles.
- Public profile output respects visibility flags; notification-read checks notification ownership.
- Video filenames are sanitized and generated server-side; allowed extensions, a 50 MB post-save limit, subprocess argument lists, and ffmpeg timeouts are present.
- API responses use JSON and the web client escapes many user-rendered values.

## Security release gate

Roadmap P0 items T-001 through T-005 now have regression/configuration verification paths. This does **not** by itself authorize an internet-facing production release: the remaining high-priority findings above, signed mobile release-device checks, deployment/proxy review, operational controls, and an independent security review still apply.

## 2026-09-24 — T-203 route extraction review

Only notification read and onboarding handlers moved. They still call the existing `require_login`; the global CSRF/origin hook remains on the same app and is exercised against every moved mutation. Notification ownership checks, missing-resource handling, and user-scoped read-all queries are preserved. Configuration, session mutation, Socket.IO authorization, profile visibility, upload authorization, schema, and clients were not modified. Existing ownership/revocation/deployment concerns are neither resolved nor expanded by this extraction.

## 2026-09-24 — Issue #3 profile extraction review

The five moved routes use the existing session-derived login guard and application-wide CSRF/origin enforcement. Skills retain their student/alumni-only 400 gate; other profile workflows retain their current role-specific behavior. Forged user identifiers cannot redirect edits or exports. Exports retain caller-scoped notification/coach/application queries, full history, and existing serialization. Visibility truthiness and owner/admin access semantics remain intact. Image/media authorization, cleanup, retention, Socket.IO, models, and clients are unchanged. Existing security concerns above remain separate work.

## 2026-09-26 — Issue #5 analytics extraction review

All three moved handlers use the unchanged session-derived login guard, including suspension rejection and last-seen commit. Business analytics retains owner-scoped opportunities/listings/profile views; admin access remains platform-wide. Student profile views and peer context follow the caller, while existing shared-network/display-name attribution limitations remain untouched. All role/dashboard combinations and anonymous/missing/suspended sessions are covered. No session/CSRF/origin, Socket.IO, upload/media, model, client, or retention changes.

## T-104 design review — ownership remains unresolved (2026-09-26)

The seven network/conversation handlers still accept any active authenticated account against shared rows. Existing session/CSRF protections and session-derived Socket.IO rooms do not authorize those row accesses; GET conversation detail also clears global unread. Existing sockets are not automatically disconnected on later suspension. Social notification emission currently precedes its caller's commit; student analytics also exposes shared network counts.

[OWNERSHIP_DESIGN](OWNERSHIP_DESIGN.md) provides the current source trace, per-operation anonymous/participant/nonparticipant/suspended/admin matrix, concealed-404 policy, proposed actor/membership enforcement, race/revocation defenses and required future tests. D-012–D-015 are **PROPOSED / REQUIRES HUMAN APPROVAL**. This documentation does not fix any of these gaps, authorize private admin access, change authentication/CSRF, or approve retention/deletion policy.
