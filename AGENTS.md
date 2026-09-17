# Forge Agent Operating Rules

## Scope

This repository is Forge.

The repository root is the only project workspace.

Never intentionally access, modify, create, delete, enumerate, or
execute files outside the Forge workspace.

Never inspect:

- /home/pablo outside the Forge workspace
- unrelated repositories
- ~/.ssh
- browser profiles
- unrelated credentials
- unrelated projects
- system configuration

Never attempt to bypass filesystem or sandbox restrictions.

## Source of Truth

Use the existing Forge implementation and prototype as evidence.

Use these durable project records as the project-state source of truth:

agent/STATE.md
agent/ROADMAP.md
agent/TASKS.md
agent/ARCHITECTURE.md
agent/DECISIONS.md
agent/SECURITY.md
agent/API_MAP.md
agent/DATA_MODEL.md
agent/MOBILE_PLAN.md
agent/WEB_PLAN.md
agent/KNOWN_ISSUES.md
agent/TEST_RESULTS.md
agent/SESSION_LOG.md

Do not invent project state when it can be determined from the
repository.

## Existing Prototype

Understand the existing application before proposing or performing
major changes.

Do not rewrite working systems merely because they are monolithic,
messy, or old.

Prefer incremental extraction and migration over destructive rewrites.

## Autonomous Work

Routine engineering work does not require human approval.

This includes:

- bug fixes
- tests
- refactoring
- documentation
- UI improvements
- API implementation
- backend implementation
- database implementation that is additive/reversible
- performance improvements
- accessibility improvements
- ordinary dependency updates
- project-local tooling

Investigate first and make the least disruptive robust decision.

## Human Approval Required

Stop and request approval before:

- replacing the fundamental architecture
- replacing the primary frontend framework
- replacing the primary backend framework
- replacing the primary database technology
- destructive database migrations
- removing a major subsystem
- fundamentally changing authentication
- changing deployment architecture
- introducing a major external service dependency
- irreversible changes affecting substantial project data
- large-scale rewrites

Do not ask for approval for ordinary implementation choices.

## Required Engineering Loop

For meaningful work:

1. Inspect the existing implementation.
2. Inspect relevant documentation.
3. Inspect relevant tests.
4. Identify affected components.
5. Plan the change.
6. Implement incrementally.
7. Run appropriate tests.
8. Diagnose failures.
9. Review the Git diff.
10. Check regressions and security implications.
11. Update documentation.
12. Update project state.
13. Commit the completed coherent change.

Never mark work complete merely because the code compiles.

## Testing

Important behavior requires automated coverage where practical.

For bugs:

1. reproduce,
2. add a regression test,
3. fix,
4. verify.

Never weaken a test merely to make incorrect implementation pass.

## Security

Never expose secrets.

Never commit credentials.

Treat external input as untrusted.

Review authentication, authorization, uploads, subprocesses,
networking, AI provider calls, and file handling carefully.

## Desktop and Mobile

Desktop and mobile are both first-class targets.

Do not design desktop functionality with mobile as an afterthought.

Consider:

- responsive behavior
- touch interaction
- keyboard interaction
- accessibility
- performance
- unreliable mobile networking
- application lifecycle
- platform differences

Prefer shared code where technically appropriate.

## Git

Make coherent, reviewable commits.

Before committing:

- inspect git status,
- inspect the diff,
- run relevant tests,
- ensure unrelated changes are not included,
- ensure no secrets are included.

Never casually rewrite history.

Never reset or delete another person's work.

## Agent Memory

Keep agent documentation synchronized with implementation.

Important decisions belong in:

agent/DECISIONS.md

Current project state belongs in:

agent/STATE.md

Unfinished work belongs in:

agent/TASKS.md
agent/KNOWN_ISSUES.md

Testing evidence belongs in:

agent/TEST_RESULTS.md

Every important autonomous session should leave a record in:

agent/SESSION_LOG.md

## Current Checkout

Work in the current Forge checkout.

Do not silently create or switch to a separate managed repository,
clone, or worktree.

Do not change the project's fundamental architecture without the
human approval described above.
