# Security

Status: discovery findings with T-001/T-002/T-003/T-004 resolutions verified as of 2026-09-18. Open findings and implementation evidence are distinguished below.

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

## High-priority verified concerns

- The process defaults to `FORGE_DEBUG=1`, binds `0.0.0.0`, and provides `/api/auth/demo-login` in debug mode. Debug must be off outside a local development environment; demo accounts and endpoint must not be exposed.
- Login throttling is in-process and keyed only by username; it is lost across restarts and does not provide distributed/IP-aware protection.
- Password-reset tokens are stored in plaintext. In debug, a valid token is returned in the response; in non-debug with no SMTP configured, reset delivery is not available. Hash stored reset tokens, prevent debug deployment, and make delivery observable without logging sensitive contents.
- Upload checks happen after saving the complete request, rely on extension rather than file inspection, and `/uploads/<path:name>` is publicly served. Enforce request-size limits before buffering, validate content, define authorization/retention, and scan/serve media safely.
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

No internet-facing deployment should proceed until every P0 item has a regression test and a configuration verification path. Findings above are not a substitute for an independent security review.
