# Forge mobile

This Expo Router app provides native sign-in, profile, feed, opportunities, onboarding, and notifications. A WebView opens the existing Forge web client for workflows that have not moved to native screens. Native networking and messaging are not available yet; see [the mobile plan](../agent/MOBILE_PLAN.md).

## Local development

From this directory:

```bash
npm ci
npm start
```

Run checks with:

```bash
npm test
npm run lint
npx tsc --noEmit
```

The app connects only to approved HTTPS origins embedded at build time. Set `FORGE_MOBILE_ALLOWED_ORIGINS` to a comma-separated list of exact HTTPS origins before starting or building, for example `https://forge.example.test`. Without it, the app opens settings and connects to no server. This value is public configuration, not a credential. The optional development override and signed-device release checks are documented in [MOBILE_PLAN.md](../agent/MOBILE_PLAN.md). Do not assume native `fetch` and the WebView share a login session.

## Where things live

| Path | Responsibility |
| --- | --- |
| `src/app/index.tsx` | Native workflows, WebView fallback, connection settings |
| `src/api/client.js` | Native API requests and session/CSRF handling |
| `src/security/url-policy.js` | Exact-origin and URL policy |
| `app.config.js`, `plugins/` | Build-time origin and native transport configuration |
| `tests/` | Native client, screen, and security checks |

The About tab retains the `/explore` route so existing navigation links keep working. Some unused starter assets/components remain; review imports and platform variants before removing them.
