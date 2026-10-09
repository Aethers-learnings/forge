# Engineering records

## Start here

Read [AGENTS.md](../AGENTS.md), [STATE](STATE.md), and [TASKS](TASKS.md) first. Everything else is reference material; consult it only when a task points to it. [TEST_RESULTS](TEST_RESULTS.md) and [SESSION_LOG](SESSION_LOG.md) are append-only logs written by `agent_runtime`; they are large, so do not read them in full.

Start with [STATE](STATE.md) for the latest verified status and [TASKS](TASKS.md) for unfinished work. Dated sections in these files preserve earlier evidence; the latest update and the actual code take precedence over historical snapshots.

| Need | Record |
| --- | --- |
| Work order and release gates | [ROADMAP](ROADMAP.md), [TASKS](TASKS.md) |
| Accepted and pending decisions | [DECISIONS](DECISIONS.md) |
| Architecture and data | [ARCHITECTURE](ARCHITECTURE.md), [DATA_MODEL](DATA_MODEL.md) |
| Current route inventory and contract | [API_MAP](API_MAP.md), [API_CONTRACT](API_CONTRACT.md) |
| Security and known limitations | [SECURITY](SECURITY.md), [KNOWN_ISSUES](KNOWN_ISSUES.md) |
| Approved ownership design and safety gate | [OWNERSHIP_DESIGN](OWNERSHIP_DESIGN.md), [SAFETY_DESIGN](SAFETY_DESIGN.md) |
| T-107 blocking implementation status | [T107_IMPLEMENTATION](T107_IMPLEMENTATION.md) |
| Client plans | [WEB_PLAN](WEB_PLAN.md), [MOBILE_PLAN](MOBILE_PLAN.md) |
| Verification and session history | [TEST_RESULTS](TEST_RESULTS.md), [SESSION_LOG](SESSION_LOG.md) |
| Local autonomous tooling | [AUTONOMY](AUTONOMY.md) |

The ownership and safety design documents contain both implemented and future behavior. Ownership-v2 and the T-107 directed blocking core now have reviewed implementation increments, but the default/production social mode remains legacy and T-107 reporting/reviewer work is still outstanding. Check [STATE](STATE.md), [TASKS](TASKS.md), [T107_IMPLEMENTATION](T107_IMPLEMENTATION.md), and the code before describing any design as production-complete.
