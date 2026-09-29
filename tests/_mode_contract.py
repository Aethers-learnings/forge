"""Fresh-process graph isolation assertions for maintenance and legacy modes."""
import re
from sqlalchemy import event
import forge_backend as forge
from forge_routes.owned_social import OwnedSocialService


def test_fixed_mode_and_sql_graph_isolation(client):
    mode = forge.app.config['FORGE_SOCIAL_MODE']
    assert mode in ('legacy', 'maintenance')
    a = forge.User(username='mode_a', name='Mode A', role='trade', password_hash='unused')
    b = forge.User(username='mode_b', name='Mode B', role='trade', password_hash='unused')
    forge.db.session.add_all([a, b])
    forge.db.session.commit()
    a_id, b_id = a.id, b.id
    with client.session_transaction() as session:
        session['user_id'] = a_id
        session['csrf_user_id'] = a_id
        session['csrf_token'] = 'valid'
    headers = {'Origin': 'http://localhost', 'X-CSRF-Token': 'valid'}
    traced = []
    def trace(connection, cursor, statement, parameters, context, executemany):
        traced.append(statement.lower())
    event.listen(forge.db.engine, 'before_cursor_execute', trace)
    try:
        assert client.post(f'/api/network/suggested/{b_id}/connect', json={'expectedVersion': 0},
                           headers={**headers, 'X-CSRF-Token': 'bad'}).status_code == 403
        if mode == 'maintenance':
            assert client.get('/api/network').status_code == 503
            assert client.get('/api/conversations/nonexistent').status_code == 503
            assert client.post(f'/api/network/suggested/{b_id}/connect', json={'expectedVersion': 0},
                               headers=headers).status_code == 503
            assert client.post('/api/conversations', json={'targetUserId': b_id},
                               headers=headers).status_code == 503
            assert not any(re.search(r'\b(?:from|into|update|join)\s+(?:network_request|suggested|connection_npc|conversation|message|network_edge|direct_conversation|direct_message|endorsement|conversation_member|ownership_event)\b', s) for s in traced)
        else:
            forge.db.session.add(forge.Suggested(name='Legacy', role='trade', color='#123456', status='new'))
            forge.db.session.commit()
            result = client.get('/api/network')
            assert result.status_code == 200 and result.json['suggested'][0]['name'] == 'Legacy'
            with_header = client.get('/api/network', headers={'X-Forge-Ownership-Version': '2'})
            assert with_header.json == result.json
            assert client.post('/api/conversations', json={'targetUserId': b_id}, headers=headers).status_code == 405
            assert client.post('/api/network/suggested/1/connect', json={'expectedVersion': 0},
                               headers=headers).status_code == 200
            assert not any(re.search(r'\b(?:into|update|delete\s+from)\s+(?:network_edge|direct_conversation|direct_message|endorsement|conversation_member|ownership_event)\b', s) for s in traced)
            assert OwnedSocialService(forge.db.engine, forge).own_edges(forge.db.session.get(forge.User, a_id)) == []
    finally:
        event.remove(forge.db.engine, 'before_cursor_execute', trace)
