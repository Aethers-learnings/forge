# Decisions

## D-001: Maintain the prototype during stabilization

Status: accepted

Forge will not receive a large rewrite merely because `forge_backend.py` and the static web client are monolithic. Incremental extraction, protected by regression tests, is the approved direction. Classification: SAFE_INCREMENTAL.

## D-002: Backend continuity

Status: accepted

Flask is the current backend. Replacing Flask is a fundamental architecture change and requires human approval. Classification: HUMAN_APPROVAL_REQUIRED.

## D-003: Web continuity

Status: accepted

The static web frontend remains the production/prototype frontend until an incremental migration path has been demonstrated against a stable contract. A wholesale frontend replacement is MAJOR_REVIEW; small accessibility, security, and testable component extractions are SAFE_INCREMENTAL.

## D-004: Mobile continuity

Status: accepted

The Expo/WebView application remains while native-mobile parity is developed. Native features must be introduced one workflow at a time without removing the wrapper prematurely. Classification: SAFE_INCREMENTAL.

## D-005: Data platform

Status: accepted

SQLite is the currently verified persistence technology. PostgreSQL is a future option only; its adoption, data migration, operational plan, and rollback require human approval. Classification: HUMAN_APPROVAL_REQUIRED.

## D-006: Authentication boundary

Status: accepted

The present signed-cookie/session mechanism remains the baseline only while P0 hardening is performed. Any fundamental authentication change (identity provider, token model, account model, or session replacement) requires human approval. Classification: HUMAN_APPROVAL_REQUIRED.
