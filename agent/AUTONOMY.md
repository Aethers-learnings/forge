# Forge autonomous engineering MVP

`scripts/forge-auto` is a small local controller for future dependency-satisfied `SAFE_INCREMENTAL` tasks. It is developer tooling only and does not change Forge product behavior.

## Commands

`scripts/forge-auto status` parses the backlog and reports progress and the eligible next task. It makes zero model calls. `scripts/forge-auto next` prints the first incomplete, dependency-satisfied `SAFE_INCREMENTAL` task. `scripts/forge-auto run T-XYZ` verifies the requested task is safe, snapshots the dirty working tree, creates a run directory, and executes the bounded workflow. It never selects a different task.

## Architecture and boundaries

Python owns deterministic work: task parsing, dependency resolution, classification enforcement, protected-operation gates, git dirty/touched/staged-file handling, check selection, subprocess execution, repair limits, run records, and local commits. It refuses `MAJOR_REVIEW` and `HUMAN_APPROVAL_REQUIRED` tasks before any model is invoked, as well as destructive migrations, framework/backend/authentication replacement, irreversible operations, and major-subsystem removal.

Each role runs in a separate non-interactive Codex subprocess. The compact context packet contains the task, dependencies, applicable boundaries, and protected dirty paths; it deliberately does not copy all Forge documentation. The reviewer receives that packet plus diff and deterministic test evidence and must return strict JSON with `PASS` or `NEEDS_CHANGES`. Malformed reviewer output fails closed.

Default models are planner `gpt-5.6-luna`, implementer/repair `gpt-5.6-terra`, reviewer `gpt-5.6-luna`, and security/complex reviewer `gpt-5.6-sol`. Trivial documentation-only tasks use the Luna documentation implementer; title-matched sensitive work (security, CSRF, authentication, authorization, uploads, secrets, or tokens) uses the Sol reviewer. Environment variables `FORGE_AUTO_MODEL_PLANNER`, `FORGE_AUTO_MODEL_IMPLEMENTER`, `FORGE_AUTO_MODEL_DOCS`, `FORGE_AUTO_MODEL_REVIEWER`, `FORGE_AUTO_MODEL_SECURITY_REVIEWER`, and `FORGE_AUTO_MODEL_REPAIR` override them. Astra is never selected by default; using it requires an explicit model override/escalation.

Planning is off by default and can be enabled with `FORGE_AUTO_PLAN=1`. Ordinary runs use implementer plus reviewer (two calls). `FORGE_AUTO_MAX_CALLS` defaults to 4, hard-stopping excess calls; `FORGE_AUTO_MAX_REPAIRS` defaults to 2. Deterministic test failures are repaired before any review call.

Checks always include `git diff --check`; Python changes compile; backend/test changes run pytest; static frontend changes run `node tests/csrf_frontend.cjs`; mobile changes run its test, lint, and TypeScript checks. Commands, stdout, stderr, and exit status are retained.

## Git and records

Run artifacts are ignored under `.forge-agent/runs/<timestamp>-<task-id>/`: `task.json`, `context.txt`, agent outputs, check logs, review result, touched files, and final result. Inspect these files after a failed run. A failed run does not automatically clean or reset anything; inspect `git status`, the artifact’s `final-result.json`, and either repair manually or discard only changes you explicitly choose.

The controller snapshots existing dirty paths and refuses pre-existing staged files. Before committing it permits staging only task-touched files plus approved durable run records, uses `Forge Agent <forge-agent@local>`, and never pushes or amends commits. Stop a running invocation with Ctrl-C; it creates no automatic cleanup action.
