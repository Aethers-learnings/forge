"""Valid physical HEAD rows for whole-schema integrity/removal experiments."""

from sqlalchemy import text


# Explicit physical fixtures: all FK-bearing tables, including composite keys.
ROWS = {
    "user": [dict(id=i, username=f"fk_{i}", password_hash="unused",
                  role="admin" if i == 3 else "trade", name=f"Account {i}",
                  suspended=0) for i in (1, 2, 3)],
    "post": [dict(id=1, feed="trade", author_name="Account 1", author_role="trade", body="fixture")],
    "approval_queue_item": [dict(id=1, title="fixture", co="fixture")],
    "business_listing": [dict(id=1, owner_user_id=1, queue_item_id=1, title="fixture", co="fixture")],
    "opportunity": [dict(id=1, owner_user_id=1, listing_id=1, title="fixture", co="fixture")],
    "application": [dict(id=1, opportunity_id=1, user_id=1)],
    "event": [dict(id=1, title="fixture", place="fixture", day="1", mon="Jan")],
    "interest": [dict(id=1, event_id=1, user_id=1)],
    "like": [dict(id=1, post_id=1, user_id=1)],
    "comment": [dict(id=1, post_id=1, author_name="Account 1", text="private fixture")],
    "conversation": [dict(id=1, slug="legacy", name="fixture")],
    "message": [dict(id=1, conversation_id=1, who="me", text="private fixture")],
    "alumni_verification": [dict(id=1, user_id=1, document_ref="fixture")],
    "coach_message": [dict(id=1, user_id=1, who="user", text="private fixture")],
    "notification": [dict(id=1, user_id=1, type="test", text="private fixture")],
    "profile_image": [dict(id=1, user_id=1, filename="profile_" + "a" * 32 + ".jpg")],
    "profile_view": [dict(id=1, viewed_user_id=1, viewer_user_id=2)],
    "skill_search": [dict(id=1, skill="fixture", searcher_id=1)],
    "testimonial": [dict(id=1, user_id=1, author_name="fixture", text="private fixture")],
    "network_edge": [dict(id=1, user_low_id=1, user_high_id=2, requester_id=1,
                          recipient_id=2, changed_by_user_id=2, state="accepted", version=2,
                          created_at="2026-10-09", requested_at="2026-10-09",
                          updated_at="2026-10-09", accepted_at="2026-10-09")],
    "endorsement": [dict(id=1, network_edge_id=1, endorser_id=1, recipient_id=2,
                         skill_key="", version=1, created_at="2026-10-09", updated_at="2026-10-09")],
    "direct_conversation": [dict(id=1, public_id="owned", user_low_id=1, user_high_id=2,
                                 created_by_user_id=1, created_at="2026-10-09",
                                 updated_at="2026-10-09", last_seq=1)],
    "conversation_member": [dict(conversation_id=1, user_id=i, joined_at="2026-10-09", last_read_seq=0)
                            for i in (1, 2)],
    "direct_message": [dict(conversation_id=1, seq=1, sender_id=1, client_message_id="fixture",
                            text="private fixture", created_at="2026-10-09")],
    "ownership_event": [dict(id=1, network_edge_id=1, actor_user_id=2, entity_version=2,
                             event_type="accepted", created_at="2026-10-09"),
                        dict(id=2, endorsement_id=1, actor_user_id=1, entity_version=1,
                             event_type="endorsed", created_at="2026-10-09"),
                        dict(id=3, conversation_id=1, actor_user_id=1, entity_version=1,
                             event_type="created", created_at="2026-10-09")],
    "user_block": [dict(id=1, blocker_id=1, blocked_id=2, active=0, version=2,
                        created_at="2026-10-09", updated_at="2026-10-09", unblocked_at="2026-10-09")],
    "block_event": [dict(id=1, user_block_id=1, actor_user_id=1, block_version=1,
                         event_type="blocked", previous_state="unblocked", next_state="blocked",
                         created_at="2026-10-09"),
                    dict(id=2, user_block_id=1, actor_user_id=1, block_version=2,
                         event_type="unblocked", previous_state="blocked", next_state="unblocked",
                         created_at="2026-10-09")],
}


def populate(connection, tables=None):
    quote = connection.dialect.identifier_preparer.quote_identifier
    for table, rows in ROWS.items():
        if tables is not None and table not in tables:
            continue
        for row in rows:
            columns = ", ".join(quote(c) for c in row)
            values = ", ".join(f":{c}" for c in row)
            connection.execute(text(f"INSERT INTO {quote(table)} ({columns}) VALUES ({values})"), row)


def snapshot(connection):
    quote = connection.dialect.identifier_preparer.quote_identifier
    return {table: connection.exec_driver_sql(f"SELECT * FROM {quote(table)} ORDER BY rowid").all()
            for table in ROWS if table != "user"}
