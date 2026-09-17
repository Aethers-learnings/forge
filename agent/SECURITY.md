# Security

Status: discovery findings. “Verified” means observed in code; it does not claim exploitation testing.

## P0 — verified findings

1. **Predictable fallback Flask secret.** `SECRET_KEY` defaults to the literal `dev-secret-change-me` when `FORGE_SECRET_KEY` is unset. A deployed instance with that fallback permits forged signed session cookies and therefore account/role impersonation. Require a non-default secret at startup and set secure cookie attributes in the production configuration. Classification: SAFE_INCREMENTAL.

2. **Unauthenticated Socket.IO room selection and permissive CORS.** Socket.IO is configured with `cors_allowed_origins="*"`; its `join` event accepts arbitrary `userId` and `role` values and joins rooms without consulting the Flask session. Any connected client can subscribe to another user’s notifications or a role’s events by choosing those values. Bind room membership to `current_user()`/the authenticated session and restrict allowed origins before exposing the service. Classification: SAFE_INCREMENTAL.

3. **Mobile WebView accepts arbitrary origins and insecure transport.** The wrapper persists an editable server address, permits `http://`, uses `originWhitelist={['*']}`, enables Android cleartext traffic, and enables mixed content. A user can be led to an attacker-controlled endpoint or expose session traffic on an untrusted network. Production mobile builds need an HTTPS allowlist, no mixed/cleartext content, and explicit navigation controls. Classification: SAFE_INCREMENTAL.

4. **No CSRF defense is present for cookie-authenticated state-changing routes.** The web client sends cookies (`credentials: same-origin`); Flask session cookies are `SameSite=Lax`, but the server has no CSRF token/origin validation and the Socket.IO CORS policy is wide open. Add a coherent CSRF/origin policy before production deployment. This is security hardening within the current authentication architecture; a fundamental auth replacement remains HUMAN_APPROVAL_REQUIRED.

## High-priority verified concerns

- The process defaults to `FORGE_DEBUG=1`, binds `0.0.0.0`, and provides `/api/auth/demo-login` in debug mode. Debug must be off outside a local development environment; demo accounts and endpoint must not be exposed.
- Login throttling is in-process and keyed only by username; it is lost across restarts and does not provide distributed/IP-aware protection.
- Password-reset tokens are stored in plaintext. In debug, a valid token is returned in the response; in non-debug with no SMTP configured, reset delivery is not available. Hash stored reset tokens, prevent debug deployment, and make delivery observable without logging sensitive contents.
- Upload checks happen after saving the complete request, rely on extension rather than file inspection, and `/uploads/<path:name>` is publicly served. Enforce request-size limits before buffering, validate content, define authorization/retention, and scan/serve media safely.
- Data ownership is incomplete for network requests, suggested users, connection endorsements, and conversations: all authenticated users read/mutate shared rows. This is both an authorization defect and a data-model limitation.
- No security headers, HTTPS enforcement, cookie `Secure`/explicit `HttpOnly` configuration, CSP, or proxy trust policy was found. The static client uses `innerHTML`; output escaping exists in client helpers but needs regression coverage.
- External SMTP and the optional Anthropic call are synchronous request-path integrations. Mail bodies and errors can be logged when SMTP is absent/fails; coach history is sent to the provider when configured. Define consent, data minimization, audit, timeouts, and failure handling before production use.

## Existing protections observed

- Passwords use Werkzeug hash/check helpers; admin is excluded from public self-registration and provisioning requires a server-side secret.
- Most API routes call `require_login()` and role-gated admin/business/student routes return 403 for wrong roles.
- Public profile output respects visibility flags; notification-read checks notification ownership.
- Video filenames are sanitized and generated server-side; allowed extensions, a 50 MB post-save limit, subprocess argument lists, and ffmpeg timeouts are present.
- API responses use JSON and the web client escapes many user-rendered values.

## Security release gate

No internet-facing deployment should proceed until every P0 item has a regression test and a configuration verification path. Findings above are not a substitute for an independent security review.
