# Engineering records

Start with [STATE](STATE.md) for the latest verified status and [TASKS](TASKS.md) for unfinished work. Dated sections in these files preserve earlier evidence; the latest update and the actual code take precedence over historical snapshots.

| Need | Record |
| --- | --- |
| Work order and release gates | [ROADMAP](ROADMAP.md), [TASKS](TASKS.md) |
| Accepted and pending decisions | [DECISIONS](DECISIONS.md) |
| Architecture and data | [ARCHITECTURE](ARCHITECTURE.md), [DATA_MODEL](DATA_MODEL.md) |
| Current route inventory and contract | [API_MAP](API_MAP.md), [API_CONTRACT](API_CONTRACT.md) |
| Security and known limitations | [SECURITY](SECURITY.md), [KNOWN_ISSUES](KNOWN_ISSUES.md) |
| Approved ownership design and safety gate | [OWNERSHIP_DESIGN](OWNERSHIP_DESIGN.md), [SAFETY_DESIGN](SAFETY_DESIGN.md) |
| Client plans | [WEB_PLAN](WEB_PLAN.md), [MOBILE_PLAN](MOBILE_PLAN.md) |
| Verification and session history | [TEST_RESULTS](TEST_RESULTS.md), [SESSION_LOG](SESSION_LOG.md) |
| Local autonomous tooling | [AUTONOMY](AUTONOMY.md) |

The ownership and safety design documents specify future behavior. The current network/conversation handlers still use the legacy shared tables. The additive owned-social migration does not itself switch routes or import legacy ownership. Check [STATE](STATE.md) and the code before describing a design as implemented.
