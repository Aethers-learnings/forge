# Forge Discovery Mission

You are the lead Forge orchestrator.

This is a READ-ONLY discovery mission. Do not perform broad implementation changes.

Inspect the entire authorized Forge workspace and produce a reliable technical baseline.

Analyze:
- product behavior represented by the prototype
- Flask backend architecture
- routes and authorization
- SQLAlchemy models and relationships
- database initialization/migrations
- Socket.IO behavior
- authentication/session/password-reset flows
- AI provider integration
- file uploads and video processing
- frontend structure and major flows
- mobile structure and WebView dependencies
- tests and current testability
- dependency files
- deployment assumptions
- security-sensitive surfaces
- current Git state

Populate:
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

Create a dependency-aware roadmap with P0/P1/P2/P3 priorities.

Mark tasks that require human approval under the repository constitution.

Do not make a major rewrite.

At completion, summarize:
1. current architecture,
2. current product capabilities,
3. highest-risk areas,
4. first implementation milestone,
5. changes that must wait for human approval.
