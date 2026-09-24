# Forge

A professional networking platform for the Richfield/AAA community — built for the
2026 Richfield Hackathon. Forge connects current students, alumni, business
users (recruiters/employers), and campus administrators in one place: digital
portfolios, connections, an opportunity board, career pathways, and an
AI-assisted profile coach.

## Project overview

Four user types, each with a distinct role and access level:

- **Student** — authenticates with a Richfield/AAA institutional email
  (`@my.richfield.ac.za`, `@richfield.ac.za`, `@my.aaa.ac.za`, `@aaa.ac.za`),
  builds a portfolio-style profile, applies to opportunities, connects with
  peers and alumni.
- **Alumni** — graduates without an active student email; identity is
  verified through a manual review queue (document upload + admin approval)
  rather than institutional email.
- **Business user** — a verified recruiter/employer; registration requires
  admin approval before the account can post opportunities. Cannot see
  student data beyond what's explicitly made visible.
- **Administrator** — provisioned separately (never self-registered);
  manages users, content moderation, event publishing, opportunity approval,
  platform analytics, and announcements.

Core features: connections + activity feed, direct messaging, an opportunity
board with skill-based matching, a career pathway explorer, an AI profile
coach/onboarding assistant, CV-based skill extraction, video posts with
transcoding, real-time notifications (WebSocket), and three separate
analytics dashboards (student / business / admin).

## Technology choices

| Layer | Choice | Why |
|---|---|---|
| Backend | Flask + Flask-SQLAlchemy | Small team, fast iteration, ORM keeps the four-role data model manageable |
| Realtime | Flask-SocketIO | Live notifications, messages, and job matches without polling |
| Database | SQLite (dev) | Zero-setup for a hackathon build; schema is standard SQL and migrates cleanly to PostgreSQL for anything beyond a demo |
| Auth | Server-side sessions + Werkzeug password hashing | Institutional-domain filtering and a non-self-registerable admin role were easier to enforce directly on the backend than to bolt onto a third-party auth SDK under our timeline |
| AI coach | Anthropic API (Claude) when configured, rule-based fallback otherwise | Demo never breaks if the API key/quota isn't available |

> **Known gap:** the brief requires the mobile app to be built with Flutter,
> React Native, .NET MAUI, or native Kotlin/Swift. This prototype is a
> Flask-served web client. We are aware this does not meet the mandatory
> framework requirement and can speak to our mitigation plan in the
> presentation.

## Setup instructions

```bash
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env              # then fill in real values, see below
flask --app forge_backend seed-demo   # first run only — creates instance/forge.db
python forge_backend.py
```

Then open **http://localhost:5000**.

Demo logins (password `demo123`): `demo_trade`, `demo_grad`, `demo_business`,
`demo_admin`.

### Environment variables (`.env`)

| Variable | Required? | Purpose |
|---|---|---|
| `FORGE_SECRET_KEY` | Recommended | Flask session signing key |
| `ANTHROPIC_API_KEY` | Optional | Enables the real AI coach; falls back to rule-based replies without it |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `SMTP_FROM` | Optional | Enables real outbound email (sign-in alerts, password resets). Without SMTP, delivery is skipped and message contents are never logged. |

## Team

<!-- One line per member: name — what you built/own -->
-
-
-
