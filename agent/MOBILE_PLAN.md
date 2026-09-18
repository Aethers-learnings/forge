# Mobile plan

Status: proposed incremental parity plan; current mobile behavior is verified separately.

## Verified implementation — T-004

The Expo WebView wrapper, Android back handling, settings and existing error display remain. Approved exact HTTPS origins are required at every server entry point. Missing configuration opens settings and permits no connection. Invalid saved addresses and storage failures are recoverable.

### Build configuration

- Supply `FORGE_MOBILE_ALLOWED_ORIGINS` as comma-separated complete HTTPS origins in the build environment. Non-default ports must be explicit. Paths, queries, fragments, credentials and wildcard hosts fail config validation. Explicit HTTPS IP origins authorize those IP/port combinations; otherwise IP origins are rejected.
- No hostname/default is embedded. Empty/missing configuration allows no server; malformed nonempty configuration fails evaluation. These values are public app configuration, not secrets.
- `app.config.js` embeds origins in `extra.forgeSecurity`. Supply the same environment for native builds and JS exports/updates. Native transport changes require a new binary. Expo Go is not release-native policy evidence.
- Optional development override requires `EAS_BUILD_PROFILE=development`, `FORGE_MOBILE_DEVELOPMENT=1`, and `FORGE_MOBILE_DEV_ORIGINS` containing explicit HTTPS origins; runtime also requires `__DEV__`. Preview/production ignore these origins. No HTTP exception exists, including development: use a trusted HTTPS endpoint.
- The Expo plugin enforces Android cleartext false; iOS ATS contains no arbitrary-load or local-network exceptions. EAS profiles were not modified.

### Manual release-device gates

On signed Android and iOS preview/release builds:

1. Inspect the final merged/packaged Android manifest and iOS Info.plist for cleartext false, no network-security override and no ATS exceptions.
2. Verify approved HTTPS login/session/CSRF workflows, back navigation and settings recovery; invalid saved values must not load or silently save.
3. Exercise redirects, links, forms, JS location changes, deceptive hosts, unexpected ports/IPs, custom schemes, target=_blank and window.open with/without user gestures. Disallowed destinations must neither load nor open an external browser/app.
4. Verify HTTP, mixed-content and untrusted/expired-certificate failures; missing configuration permits no connection and preview cannot use development overrides.
5. Verify workflows do not depend on popups or subframe navigation, both deliberately blocked. Native callback timing and WebView behavior require devices; Node screen tests mock native components.

No signed builds, packaged-binary inspection or device tests were performed. Introspection verifies generated configuration but does not replace those checks.

## Plan

1. T-004 implementation complete; perform the release-device gates above before release. Classification: SAFE_INCREMENTAL.
2. Establish a tested API contract shared with web, including session/CSRF behavior and error schemas. Classification: SAFE_INCREMENTAL.
3. Build native authentication/session and profile/onboarding flows, retaining the WebView as the supported fallback. Classification: SAFE_INCREMENTAL.
4. Add native discovery, opportunities/applications, notifications, and messaging only after ownership/realtime policy is corrected. Classification: SAFE_INCREMENTAL.
5. Add lifecycle-aware networking, caching, retry/error states, accessibility, touch/keyboard support, and device notification strategy. Classification: SAFE_INCREMENTAL.
6. Decide whether WebView retirement is appropriate only after measurable native parity, security, and support evidence. Classification: MAJOR_REVIEW.

The current Expo/WebView application remains during native-mobile parity work. A fundamental authentication change or a major third-party mobile service requires human approval.
