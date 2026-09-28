"""The ORM maps migration-owned storage without creating or serving it."""

from datetime import datetime

from sqlalchemy import inspect

import forge_backend as forge
from forge_migrations import verify_application_database
from migrations.r20260928_02_owned_social_schema import OWNED_SOCIAL_TABLES


MODELS = (
    forge.NetworkEdge,
    forge.Endorsement,
    forge.DirectConversation,
    forge.ConversationMember,
    forge.DirectMessage,
    forge.OwnershipEvent,
)


def test_owned_model_columns_and_indexes_match_migrated_schema(app):
    with app.app_context():
        inspector = inspect(forge.db.engine)
        assert {model.__tablename__ for model in MODELS} == set(OWNED_SOCIAL_TABLES)
        for model in MODELS:
            table = model.__table__
            actual_columns = {column["name"]: column for column in
                              inspector.get_columns(table.name)}
            assert set(table.columns.keys()) == set(actual_columns)
            for column in table.columns:
                physical = actual_columns[column.name]
                assert str(column.type.compile(forge.db.engine.dialect)) == str(physical["type"])
                assert column.nullable == physical["nullable"]
                assert bool(column.primary_key) == bool(physical["primary_key"])
            assert {index.name for index in table.indexes} == {
                index["name"] for index in inspector.get_indexes(table.name)
            }
            assert {constraint.name for constraint in table.constraints
                    if isinstance(constraint, forge.db.CheckConstraint)} == {
                constraint["name"] for constraint in inspector.get_check_constraints(table.name)
            }
            with forge.db.engine.connect() as connection:
                unique_indexes = connection.exec_driver_sql(
                    f'PRAGMA index_list("{table.name}")'
                ).all()
                physical_unique_columns = {
                    tuple(row[2] for row in connection.exec_driver_sql(
                        f'PRAGMA index_info("{index_name}")'
                    ))
                    for _, index_name, is_unique, origin, _ in unique_indexes
                    if is_unique and origin == "u"
                }
            assert {tuple(column.name for column in constraint.columns)
                    for constraint in table.constraints
                    if isinstance(constraint, forge.db.UniqueConstraint)} == physical_unique_columns
            mapped_fks = {
                (tuple(fk.column_keys), tuple(element.target_fullname for element in fk.elements),
                 fk.ondelete)
                for fk in table.foreign_key_constraints
            }
            physical_fks = {
                (tuple(fk["constrained_columns"]),
                 tuple(f'{fk["referred_table"]}.{name}' for name in fk["referred_columns"]),
                 fk["options"].get("ondelete"))
                for fk in inspector.get_foreign_keys(table.name)
            }
            assert mapped_fks == physical_fks


def test_owned_models_round_trip_a_valid_pair_without_legacy_rows(app):
    now = datetime.utcnow()
    with app.app_context():
        a = forge.User(username="owned_a", password_hash="unused", role="trade", name="A")
        b = forge.User(username="owned_b", password_hash="unused", role="grad", name="B")
        forge.db.session.add_all((a, b))
        forge.db.session.flush()
        edge = forge.NetworkEdge(user_low_id=a.id, user_high_id=b.id,
                                 requester_id=a.id, recipient_id=b.id,
                                 state="accepted", version=2, created_at=now,
                                 requested_at=now, updated_at=now, accepted_at=now,
                                 changed_by_user_id=b.id)
        conversation = forge.DirectConversation(public_id="owned-pair", user_low_id=a.id,
                                                user_high_id=b.id, created_by_user_id=a.id,
                                                created_at=now, updated_at=now, last_seq=1)
        forge.db.session.add_all((edge, conversation))
        forge.db.session.flush()
        forge.db.session.add_all((
            forge.ConversationMember(conversation_id=conversation.id, user_id=a.id,
                                     joined_at=now, last_read_seq=0),
            forge.ConversationMember(conversation_id=conversation.id, user_id=b.id,
                                     joined_at=now, last_read_seq=0),
            forge.Endorsement(network_edge_id=edge.id, endorser_id=a.id,
                              recipient_id=b.id, skill_key="", version=1,
                              created_at=now, updated_at=now),
            forge.OwnershipEvent(network_edge_id=edge.id, actor_user_id=b.id,
                                 entity_version=2, event_type="accepted",
                                 previous_state="pending", next_state="accepted", created_at=now),
        ))
        forge.db.session.flush()
        forge.db.session.add(forge.DirectMessage(conversation_id=conversation.id, seq=1,
                                                 sender_id=a.id, client_message_id="retry-1",
                                                 text="Hello", created_at=now))
        forge.db.session.commit()
        forge.db.session.expire_all()

        assert forge.DirectMessage.query.filter_by(client_message_id="retry-1").one().text == "Hello"
        assert forge.ConversationMember.query.filter_by(conversation_id=conversation.id).count() == 2
        assert forge.NetworkRequest.query.count() == 0
        assert forge.Conversation.query.count() == 0
        verify_application_database(forge.db.engine)
