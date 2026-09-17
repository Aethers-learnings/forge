# FORGE AUTONOMOUS ENGINEERING CONSTITUTION

## Mission

Develop Forge from its current prototype into a reliable production application while preserving existing product behavior unless a documented reason requires change.

Desktop and mobile are first-class targets.

## HARD BOUNDARY

The project workspace is the only authorized project scope.

Never intentionally access, modify, create, delete, enumerate, inspect, or execute files outside the authorized workspace.

Never inspect unrelated repositories, home-directory files, SSH material, browser profiles, credentials, system configuration, or unrelated environment files.

Never attempt to bypass sandbox restrictions.

If an operation requires access outside the workspace, do not perform it. Explain the blocker.

## AUTONOMY

Routine engineering does not require human approval:

- bug fixes
- refactoring
- tests
- documentation
- API implementation
- backend implementation
- frontend implementation
- mobile implementation
- performance work
- accessibility work
- project-local scripts
- reversible internal dependency changes

Investigate first and make the least disruptive sound decision.

## HUMAN APPROVAL REQUIRED

Ask before:

- replacing the fundamental architecture
- rewriting most of the application
- replacing the primary frontend or backend framework
- replacing the database technology
- destructive database migrations
- removing major subsystems
- changing the fundamental auth model
- changing deployment architecture
- introducing a major external service dependency
- irreversible operations affecting substantial data

Do not ask for approval for ordinary implementation details that fall within the existing architecture.

## REQUIRED LOOP

For every meaningful task:

1. Read current state and relevant code.
2. Inspect consumers, dependencies, and tests.
3. Define acceptance criteria.
4. Plan the smallest sound change.
5. Implement incrementally.
6. Run appropriate tests.
7. Review the Git diff.
8. Check regressions and edge cases.
9. Update documentation/state.
10. Commit the coherent change.

Never mark a task complete just because code exists or compiles.

## PROTOTYPE PRESERVATION

The current Forge prototype is valuable evidence of intended behavior. Do not rewrite it simply because it is monolithic or messy.

Prefer extraction and migration:

MONOLITH -> EXTRACT -> TEST -> VERIFY -> MIGRATE -> REMOVE OLD CODE

Do not use:

MONOLITH -> DELETE -> REWRITE

unless human approval has been obtained under the approval rules above.

## CURRENT FORGE CONTEXT

Current prototype characteristics discovered during project review:

- Flask + Flask-SQLAlchemy backend
- Flask-SocketIO realtime layer
- SQLite development database
- server-side sessions and Werkzeug password hashing
- Anthropic-powered AI coach with fallback behavior
- single large Flask-served HTML/JS client
- Expo/React Native mobile project currently centered on a WebView wrapper

Treat these as observed baseline facts, not permission to preserve them forever.

## SECURITY BASELINE

Treat as known areas for review:

- development SECRET_KEY fallback
- permissive CORS configuration
- file upload and video-processing paths
- subprocess/FFmpeg execution
- authentication and authorization boundaries
- AI provider/API-key handling
- admin account provisioning
- password reset/session behavior

Do not claim a vulnerability without evidence.

## DESKTOP + MOBILE

Do not treat mobile as a later retrofit. Every substantial feature should identify desktop and mobile implications.

Prefer shared business rules and API contracts over duplicated logic.

## DOCUMENTATION

Keep these files current:

- agent/STATE.md
- agent/ROADMAP.md
- agent/TASKS.md
- agent/DECISIONS.md
- agent/ARCHITECTURE.md
- agent/KNOWN_ISSUES.md
- agent/SECURITY.md
- agent/API_MAP.md
- agent/DATA_MODEL.md
- agent/MOBILE_PLAN.md
- agent/WEB_PLAN.md
- agent/TEST_RESULTS.md
- agent/SESSION_LOG.md

## GIT

Make coherent commits. Before each commit inspect status and diff and run relevant tests.

Never commit secrets, credentials, local databases, generated inspection archives, or unrelated files.
