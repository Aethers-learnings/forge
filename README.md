# Forge

Forge is a networking prototype for the Richfield/AAA community. It connects students, alumni, employers, and campus administrators around profiles, opportunities, events, and career development.

## Current product

- Student and alumni profiles with skills, portfolio links, CV-derived skills, profile images, and visibility controls
- Role-aware activity feeds and notifications; prototype networking, messaging, and endorsements
- Opportunity discovery, matching, applications, employer approval, and listing moderation
- Student, business, and admin analytics
- AI-assisted profile/career coach with a rule-based fallback
- Video posts with upload validation and authenticated media access
- Expo mobile app with native profile/feed/opportunity/notification workflows and an HTTPS-restricted WebView fallback

Forge currently keeps the proven prototype architecture in place while it is hardened and improved incrementally.

**Social safety status:** the current network and conversation routes still use shared legacy rows. Approved ownership and blocking/reporting designs are not live behavior. The owned-social schema revision is additive and does not import legacy identities or switch routes. See [current state](agent/STATE.md), [ownership design](agent/OWNERSHIP_DESIGN.md), and [safety design](agent/SAFETY_DESIGN.md) before testing social features with real users.

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

# Use a NEW file; db-init refuses all existing files, including empty ones.
export FORGE_DATABASE_URI="sqlite:///$(pwd)/instance/forge-local.db"
flask --app forge_backend db-init --confirm-schema-change

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

To run without demo users, use the initialized local database above with demo mode off:

```bash
python forge_backend.py
```

## Test

```bash
pytest -q
```

Mobile checks live under `mobile/` (see its [setup guide](mobile/README.md)):

```bash
cd mobile
npm ci
npm test
npm run lint
npx tsc --noEmit
```

## Repository map

| Path | Purpose |
| --- | --- |
| `forge_backend.py` | Flask app, shared models/security, remaining routes, Socket.IO, server entry point |
| `forge_routes/` | Incrementally extracted onboarding, profile, notification, and analytics routes |
| `forge_migrations.py`, `migrations/` | Explicit SQLite migration commands and revisions; no automatic social cutover |
| `static/` | Same-origin web client and PWA assets |
| `mobile/` | Expo native workflows and WebView fallback; [mobile guide](mobile/README.md) |
| `tests/` | Backend and web regression tests |
| `agent/` | [Index of engineering records](agent/README.md), decisions, status, and plans |
| `agent_runtime/`, `scripts/`, `sandbox/` | Optional local autonomous-task tooling and isolated execution support |

### Database commands

`flask --app forge_backend db-status` and `flask --app forge_backend db-verify` inspect the local configured SQLite database. `db-init`, `db-backup`, `db-baseline`, `db-upgrade`, and `db-downgrade` are explicit operator actions; schema changes require confirmation flags and recovery planning. Read [T-201 status](agent/TASKS.md) and the command help before using them on persistent data. Starting the server does not apply these revisions automatically.

### Startup policy (all persistent environments)

| Database state | Application startup | Explicit operator action |
| --- | --- | --- |
| Missing persistent file | Refuses; does not create a file | Select a new path, then `db-init --confirm-schema-change` |
| Existing unmanaged file, including an exact frozen baseline | Refuses; never auto-baselines | Inspect `db-status` / `db-verify`, take/verify backup, then `db-baseline --confirm-current-schema` and `db-upgrade --confirm-schema-change` if appropriate |
| Managed at migration HEAD | Verifies checksums, schema, physical revision objects and integrity; starts | None |
| Managed behind HEAD | Refuses; never auto-upgrades | Back up/rehearse, then `db-upgrade --confirm-schema-change` |
| Drift, invalid checksums/ledger, corrupt schema or integrity failure | Refuses without repair | Inspect status/verification and restore or review repair; never delete data to make startup pass |
| Fresh in-memory development/test database | Initializes through the migration helper and verifies | No persistent file; staging/production reject in-memory databases |
| Test fixture file | Explicit helper creates a new isolated file at HEAD | The harness disposes/removes only its own temporary files between tests |

For example, prefix every operator command with `flask --app forge_backend` and keep the **same explicit `FORGE_DATABASE_URI`** throughout. Do not point rehearsal commands at a real database by accident. Existing revision files and `migrations/baseline_schema.json` are immutable history. No startup path uses ORM `create_all()`; fresh initialization builds the frozen 23-table baseline and ordered revisions plus ledger in one SQLite transaction. Revision 02 adds six storage tables without changing social routes or interpreting legacy rows.

Direct execution, ordinary WSGI import (`forge_backend:app`) and `flask --app forge_backend run` verify before serving. Flask command discovery is permitted so migration recovery/help commands remain accessible on an unready database; `seed-demo` separately verifies readiness and still requires explicit local demo mode. Staging/production retain their secret/cookie and no-debug/no-demo rules. Application WAL/NORMAL settings remain on its engine, not on read-only startup probes; FK enforcement is not enabled globally.

Startup probes open persistent SQLite with `mode=ro`, including committed WAL contents (not `immutable=1`). SQLite may maintain read-lock bookkeeping in shared-memory sidecars; probes do not execute schema/DML or journal-mode changes against the source. Run schema-changing operator commands with application writers stopped. Startup verification is a readiness gate, not continuous monitoring for later out-of-band schema changes.

If fresh initialization fails or is interrupted, SQLite rolls back the transaction; an empty reserved file or recovery journal can remain. Startup refuses that uninitialized file. Inspect it and use a new disposable path for retry rather than forcing adoption or overwriting a persistent database. Tests cover both exceptions and process termination. Demo seeding happens **after** initialization and remains a separate data transaction: a seed failure does not roll back the already complete migration history.

## Development approach

The existing prototype is treated as evidence, not disposable code. Changes are made incrementally behind regression tests. Framework replacement, destructive migrations, fundamental authentication changes, and other major architecture changes require explicit human approval.

The [engineering records index](agent/README.md) links the active roadmap, verified state, contracts, and design gates.

## Configuration

Copy `.env.example` only when you need persistent local configuration. Do not commit `.env` files or real secrets.

Deployment environments require an explicit non-default `FORGE_SECRET_KEY` of at least 32 characters. Debug and demo modes are intentionally restricted to local development.
