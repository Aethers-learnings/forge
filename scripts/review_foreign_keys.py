#!/usr/bin/env python3
"""Regenerate only canonical schema evidence using a NEW disposable database.

Run from Forge: .venv-delivery/bin/python scripts/review_foreign_keys.py
No input database argument: this command cannot inspect a persistent database.
"""

import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine
from forge_integrity import foreign_key_inventory, foreign_key_violations
from forge_migrations import (HEAD_REVISION, REVISION_ORDER, _expected_schema_for_revision,
                              initialize_fresh_database, schema_snapshot, verify_database)


USER_PURPOSE = {
    "alumni_verification": ("alumni evidence and approval record", "alumni submission/admin approval"),
    "application": ("application history", "opportunity apply, analytics, profile export"),
    "block_event": ("directed-block transition provenance", "blocking service and migration verifier; no admin evidence API"),
    "business_listing": ("business ownership and listing lifecycle", "business listing, approval and analytics"),
    "coach_message": ("caller coach history", "coach and profile export"),
    "conversation_member": ("immutable membership and read cursor", "owned history/send/read/delivery authorization"),
    "direct_conversation": ("pair identity and creation provenance", "owned list/detail/create/send and delivery"),
    "endorsement": ("actor/recipient endorsement provenance", "owned endorsement/disconnect/block projections"),
    "interest": ("event engagement", "event interest toggle"),
    "like": ("post engagement", "feed/post like toggle and analytics"),
    "network_edge": ("pair/request/last-change identity", "owned relationship transitions, analytics and delivery"),
    "notification": ("recipient notification history", "notification list/read, counts, export and delivery"),
    "opportunity": ("business publication ownership", "opportunities, application notification, business analytics"),
    "ownership_event": ("owned transition/create/revoke audit actor", "owned transactional service and migration verifier"),
    "profile_image": ("authenticated avatar storage index", "profile avatar lookup/serve/upload/delete"),
    "profile_view": ("viewed identity/viewer provenance", "public profile, applications and analytics"),
    "skill_search": ("search actor/analytics signal", "business candidate search and student analytics"),
    "testimonial": ("profile-target testimonial history; author is denormalized", "public profile projection"),
    "user_block": ("directed blocker/blocked identity including inactive history", "own block API and pair-wide authorization"),
}

PARENT_RUNTIME = {
    "post": "Admin DELETE is a removed=true soft update; like toggle deletes only the child; no hard parent delete",
    "opportunity": "No hard-delete route; listing status gates visibility and application access",
    "event": "Admin creation and interest toggle only; no parent-delete route",
    "conversation": "Legacy detail updates unread; send appends; no parent-delete route",
    "business_listing": "Listing/queue lifecycle changes status; no hard parent deletion",
    "approval_queue_item": "Approve/reject status transitions; no hard parent deletion",
    "network_edge": "State/version transitions with audit; no hard-delete service/route",
    "endorsement": "Revocation timestamp/version with audit; no hard-delete service/route",
    "direct_conversation": "Create/reuse and sequence advance; no hard-delete service/route",
    "conversation_member": "Read cursor advance only; immutable identity, no leave/delete route",
    "user_block": "Active/version transitions retaining events; no hard-delete service/route",
}


def origin(fk):
    for revision in REVISION_ORDER:
        schema = _expected_schema_for_revision(revision)["tables"]
        table = schema.get(fk["child_table"])
        if table and any(tuple(row["columns"]) == fk["child_columns"]
                         and row["referred_table"] == fk["parent_table"]
                         and tuple(row["referred_columns"]) == fk["parent_columns"]
                         for row in table["foreign_keys"]):
            return revision
    raise RuntimeError("Physical FK absent from managed revision manifests")


def columns(names):
    return "(" + ", ".join(names) + ")"


def generated_evidence(connection):
    fks = foreign_key_inventory(connection)
    actions = Counter(fk["on_delete"] for fk in fks)
    user_fks = [fk for fk in fks if fk["parent_table"] == "user"]
    other_fks = [fk for fk in fks if fk["parent_table"] != "user"]
    tables = schema_snapshot(connection)["tables"]
    lines = ["<!-- BEGIN GENERATED FK EVIDENCE -->", "## Schema summary", "",
             f"- Migration head: `{HEAD_REVISION}`.",
             f"- Application tables: **{len(tables)}** (migration ledger excluded; **{len(tables)+1}** physical user-defined tables including ledger).",
             f"- Constraints: **{len(fks)}** FKs; **{len(user_fks)}** separate FKs to `user.id` across **{len({fk['child_table'] for fk in user_fks})}** child tables.",
             f"- Delete actions: **{actions['RESTRICT']}** explicit `RESTRICT`; **{actions['NO ACTION']}** default `NO ACTION`; no CASCADE or SET NULL.",
             f"- Fresh migrated DB enforcement: `{connection.exec_driver_sql('PRAGMA foreign_keys').scalar()}`; FK-check violations: **{len(foreign_key_violations(connection))}**.",
             "- Normal application hook sets WAL/NORMAL only; actual app connections report **0 (OFF)** in maintained tests.",
             "", "## Complete FK matrix", "",
             "Each row is one physical PRAGMA foreign_key_list constraint; the composite message FK is one row. Nullable flags follow child-column order. Baseline provenance and later introductions are matched against every frozen revision manifest. All constraints are immediate, with default NO ACTION on update. Parent deletion is blocked with enforcement ON **when a matching non-NULL child exists**. A nullable FK permits NULL; it does not automatically set NULL on deletion. Unreferenced parents can be deleted by SQLite.", ""]
    for label, group in (("User identity references", user_fks), ("Other parent references", other_fks)):
        lines += [f"### {label}", "", "| Child / FK index | Child columns | Parent / columns | Child nullable | Actual delete | Introduced revision | Blocks matching parent with ON | Runtime requires OFF? |",
                  "| --- | --- | --- | --- | --- | --- | --- | --- |"]
        for fk in group:
            dependency = ("No intended dependency; old admin-remove exception assumption was unsafe"
                          if fk["parent_table"] == "user" else "No; current parent lifecycle retains rows")
            lines.append(f"| `{fk['child_table']}` / {fk['fk_index']} | `{columns(fk['child_columns'])}` | `{fk['parent_table']}{columns(fk['parent_columns'])}` | {', '.join('yes' if n else 'no' for n in fk['nullable'])} | {fk['on_delete']} | `{origin(fk)}` | Yes | {dependency} |")
        lines.append("")
    lines += ["## User-removal impact matrix", "",
              "Historical significance below describes existing provenance/history, **not a retention duration or erasure policy**. OFF/ON columns describe the old physical hard-delete attempt, not the hardened endpoint. The hardened endpoint suspends every referenced account; a clean account also suspends while FK-off concurrent writers prevent safe hard deletion. No nullable identity is nulled. Changing preservation through erasure, anonymization, nulling, cascade or legacy cleanup needs human policy approval under D-013/D-016.", "",
              "| Child / user columns | Required? | Purpose / historical significance | Current runtime consumer | Old delete OFF | Delete ON | Safe existing fallback | Policy approval for destructive change |",
              "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for fk in user_fks:
        purpose, consumer = USER_PURPOSE[fk["child_table"]]
        lines.append(f"| `{fk['child_table']}{columns(fk['child_columns'])}` | {'nullable' if any(fk['nullable']) else 'required'} | {purpose} | {consumer} | User removed; child unchanged/orphaned | Blocked | Suspend, preserve row | Yes; no policy inferred |")
    lines += ["", "## Non-user parent-delete matrix", "",
              "This covers every non-user FK, including owned chains. With OFF a physical delete leaves matching children; with ON each matching reference blocks. Existing routes do not hard-delete these parents, so no observed parent-delete route must be converted to CASCADE/SET NULL for enablement. Explicit empty-only migration downgrades are separate and refuse populated owned/block tables.", "",
              "| Parent | Child / columns | ON outcome | Current parent lifecycle / runtime risk |",
              "| --- | --- | --- | --- |"]
    for fk in other_fks:
        lines.append(f"| `{fk['parent_table']}{columns(fk['parent_columns'])}` | `{fk['child_table']}{columns(fk['child_columns'])}` | Blocked ({fk['on_delete']}) | {PARENT_RUNTIME[fk['parent_table']]}; manual/operator deletion must handle refusal |")
    lines += ["", "<!-- END GENERATED FK EVIDENCE -->"]
    return "\n".join(lines)


def regenerate():
    output = ROOT / "agent/FK_ADMIN_REVIEW.md"
    scratch = ROOT / "test-results"
    scratch.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=scratch, prefix="fk-review-") as directory:
        engine = create_engine(f"sqlite:///{Path(directory) / 'new-review.db'}")
        try:
            initialize_fresh_database(engine)
            verify_database(engine)
            with engine.connect() as connection:
                evidence = generated_evidence(connection)
        finally:
            engine.dispose()
    current = output.read_text()
    start = current.index("<!-- BEGIN GENERATED FK EVIDENCE -->")
    end = current.index("<!-- END GENERATED FK EVIDENCE -->") + len("<!-- END GENERATED FK EVIDENCE -->")
    output.write_text(current[:start] + evidence + current[end:])
    print("Regenerated agent/FK_ADMIN_REVIEW.md from a new migrated disposable database.")


if __name__ == "__main__":
    regenerate()
