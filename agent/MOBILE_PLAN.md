# Mobile plan

Status: proposed incremental parity plan; current mobile behavior is verified separately.

## Verified baseline

The Expo Router app has one operational screen, `mobile/src/app/index.tsx`. It reads/writes an editable server URL from AsyncStorage, wraps it in `react-native-webview`, exposes a settings gear, handles Android back navigation, and shows WebView error text. Android configuration permits cleartext traffic. The WebView allows all origins and mixed content. It does not expose native Forge domain screens, local domain data, push notification integration, offline behavior, or authenticated transport controls.

## Plan

1. P0: constrain production transport to HTTPS approved Forge origins, reject arbitrary navigation, remove mixed/cleartext support, and verify configuration. Keep a clearly isolated development override only if justified. Classification: SAFE_INCREMENTAL.
2. Establish a tested API contract shared with web, including session/CSRF behavior and error schemas. Classification: SAFE_INCREMENTAL.
3. Build native authentication/session and profile/onboarding flows, retaining the WebView as the supported fallback. Classification: SAFE_INCREMENTAL.
4. Add native discovery, opportunities/applications, notifications, and messaging only after ownership/realtime policy is corrected. Classification: SAFE_INCREMENTAL.
5. Add lifecycle-aware networking, caching, retry/error states, accessibility, touch/keyboard support, and device notification strategy. Classification: SAFE_INCREMENTAL.
6. Decide whether WebView retirement is appropriate only after measurable native parity, security, and support evidence. Classification: MAJOR_REVIEW.

The current Expo/WebView application remains during native-mobile parity work. A fundamental authentication change or a major third-party mobile service requires human approval.
