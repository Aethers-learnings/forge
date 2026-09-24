# Forge

Forge is a professional networking platform for the Richfield/AAA community. It connects students, alumni, employers, and campus administrators around profiles, opportunities, networking, messaging, events, and career development.

## Current product

- Student and alumni profiles with skills, portfolio links, CV-derived skills, profile images, and visibility controls
- Role-aware activity feeds, messaging, networking, endorsements, and notifications
- Opportunity discovery, matching, applications, employer approval, and listing moderation
- Student, business, and admin analytics
- AI-assisted profile/career coach with a rule-based fallback
- Video posts with upload validation and authenticated media access
- Expo mobile wrapper with an allowlisted HTTPS connection policy

Forge currently keeps the proven prototype architecture in place while it is hardened and improved incrementally.

## Stack

| Layer | Technology |
| --- | --- |
| Backend | Flask, Flask-SQLAlchemy, Flask-SocketIO |
| Database | SQLite |
| Web | Same-origin static HTML/CSS/JavaScript |
| Mobile | Expo / React Native WebView |
| Tests | pytest + Node-based frontend/mobile checks |

## Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

FORGE_ENV=development \
FORGE_DEMO_MODE=1 \
python forge_backend.py
```

Open `http://localhost:5000`.

When demo mode is enabled and the database is empty, Forge seeds these local accounts with password `demo123`:

- `demo_trade`
- `demo_grad`
- `demo_business`
- `demo_admin`

To run without demo users:

```bash
python forge_backend.py
```

## Test

```bash
pytest -q
```

Mobile checks live under `mobile/`:

```bash
cd mobile
npm ci
npm test
npm run lint
npx tsc --noEmit
```

## Repository map

```text
forge_backend.py   Flask API, data model, Socket.IO, and server entry point
static/            Current web client and PWA assets
mobile/            Expo mobile wrapper and mobile security policy
 tests/            Backend and client regression tests
agent/             Architecture, roadmap, security, state, and engineering records
agent_runtime/     Optional deterministic autonomous-task tooling
scripts/           Project helper commands
sandbox/           Locked-down agent execution environment
```

## Development approach

The existing prototype is treated as evidence, not disposable code. Changes are made incrementally behind regression tests. Framework replacement, destructive migrations, fundamental authentication changes, and other major architecture changes require explicit human approval.

The active engineering roadmap and verified project state are kept in `agent/TASKS.md`, `agent/ROADMAP.md`, and `agent/STATE.md`.

## Configuration

Copy `.env.example` only when you need persistent local configuration. Do not commit `.env` files or real secrets.

Deployment environments require an explicit non-default `FORGE_SECRET_KEY` of at least 32 characters. Debug and demo modes are intentionally restricted to local development.
