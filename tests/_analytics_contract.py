"""Run explicitly in fresh legacy/maintenance/v2 processes; trace real route SQL."""
import os
import re
from contextlib import contextmanager
from datetime import timedelta

import pytest
from sqlalchemy import event

import forge_backend as forge
from forge_routes.owned_social import OwnedSocialService
from test_analytics_routes import NOW, fixed_clock, login, series, user
from test_owned_social_analytics import connect

MODE = os.environ['FORGE_SOCIAL_MODE']
LEGACY = {'network_request', 'suggested', 'connection_npc', 'conversation', 'message'}
OWNED = {'network_edge', 'endorsement', 'direct_conversation', 'conversation_member',
         'direct_message', 'ownership_event', 'user_block', 'block_event'}


@contextmanager
def trace_sql():
    statements = []
    def trace(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement.lower())
    event.listen(forge.db.engine, 'before_cursor_execute', trace)
    try:
        yield statements
    finally:
        event.remove(forge.db.engine, 'before_cursor_execute', trace)


def queried(statements, tables):
    return {table for table in tables if any(re.search(
        rf'\b(?:from|join|into|update)\s+["`]?{table}\b', s) for s in statements)}


@pytest.fixture
def world():
    actors = [user(f'analytics_{i}', 'admin' if i == 3 else 'trade',
                   programme='Software', completion=40 + i, skills='Python') for i in range(4)]
    for actor in actors:
        actor.name = 'Same display name'
    forge.db.session.commit()
    service = OwnedSocialService(forge.db.engine, forge)
    return service, actors


def legacy_rows():
    forge.db.session.add_all([
        forge.NetworkRequest(name=str(d), role='grad', status='accepted', created_at=NOW - timedelta(days=d))
        for d in (0, 2, 14)] + [forge.NetworkRequest(name='pending', role='trade', status='pending')]
        + [forge.ConnectionNPC(name=f'NPC{i}', role='grad') for i in range(20)])
    forge.db.session.commit()


def fetch(client, actor, suffix='', headers=None):
    login(client, actor)
    return client.get('/api/analytics/student' + suffix, headers=headers)


def test_mode_graph_isolation_and_empty_owned_graph(client, world, app):
    service, (a, b, c, admin) = world
    legacy_rows()
    connect(service, b, c, NOW)
    expected = {'total': 23, 'series': series({2: 1, 1: 1, 0: 2})} if MODE == 'legacy' else {'total': 0, 'series': series()}
    # Client claims and even mutable app.config cannot redirect the captured mode.
    app.config['FORGE_SOCIAL_MODE'] = 'legacy' if MODE != 'legacy' else 'v2'
    try:
        with trace_sql() as statements:
            response = fetch(client, a, f'?user_id={b.id}&social_mode=legacy&actorId={admin.id}',
                             {'X-Forge-Ownership-Version': '2', 'X-User-Id': str(b.id), 'X-Forge-Social-Mode': 'legacy'})
    finally:
        app.config['FORGE_SOCIAL_MODE'] = MODE
    if MODE == 'maintenance':
        assert response.status_code == 503 and response.json == {'error': 'social maintenance'}
        assert queried(statements, LEGACY | OWNED) == set()
    else:
        assert response.status_code == 200
        assert response.json['connections'] == expected
        assert set(response.json) == {'profileViews', 'connections', 'engagement', 'peerComparison', 'topSearchedSkills'}
        assert queried(statements, OWNED if MODE == 'legacy' else LEGACY) == set()
        assert queried(statements, LEGACY if MODE == 'legacy' else OWNED) == (
            {'network_request', 'connection_npc'} if MODE == 'legacy' else {'network_edge'})
    if MODE != 'legacy':
        assert response.headers['Cache-Control'] == 'no-store'


def test_authentication_and_other_dashboards_remain_available(client, world):
    _, (a, b, _, admin) = world
    assert client.get('/api/analytics/student').status_code == 401
    login(client, b)
    b.suspended = True
    forge.db.session.commit()
    assert client.get('/api/analytics/student').status_code == 403
    login(client, admin)
    with trace_sql() as statements:
        for kind in ('business', 'admin'):
            assert client.get('/api/analytics/' + kind).status_code == 200
    assert queried(statements, LEGACY | OWNED) == set()
    # No new role gate for student analytics, including an ordinary admin.
    response = fetch(client, admin)
    assert response.status_code == (503 if MODE == 'maintenance' else 200)


@pytest.mark.parametrize('role', ['trade', 'grad', 'business', 'admin'])
def test_student_analytics_has_no_new_role_or_capability_gate(client, role):
    actor = user('role_caller', role)
    response = fetch(client, actor, '?social_mode=v2', {'X-Forge-Ownership-Version': 'invalid'})
    assert response.status_code == (503 if MODE == 'maintenance' else 200)


if MODE == 'v2':
    @pytest.mark.parametrize('days', [0, 13, 14])
    def test_acceptance_window_uses_acceptance_not_request_date(client, world, days):
        service, (a, b, _, _) = world
        edge = connect(service, a, b, NOW - timedelta(days=days))
        assert edge['created_at'] == edge['requested_at'] == NOW - timedelta(days=days + 30)
        counts = {i: 1 for i in range(days, -1, -1)} if days < 14 else {}
        assert fetch(client, a).json['connections'] == {'total': 1, 'series': series(counts)}

    def test_abc_admin_accepted_dates_and_unrelated_metrics(client, world):
        service, (a, b, c, admin) = world
        legacy_rows()
        connect(service, a, b, NOW)
        connect(service, b, c, NOW - timedelta(days=3))
        service.request(a, c.id, 0)
        connect(service, admin, c, NOW - timedelta(days=14))
        # Distinct created/request dates are 30 days before acceptance.
        forge.db.session.add_all([
            forge.ProfileView(viewed_user_id=a.id, created_at=NOW),
            forge.Post(author_name=a.name, author_role='grad', feed='grad', body='baseline', base_likes=7),
            forge.SkillSearch(skill='Python')])
        forge.db.session.commit()
        expected = [(a, 1, series({0: 1})), (b, 2, series({3: 1, 2: 1, 1: 1, 0: 2})),
                    (c, 2, series({3: 1, 2: 1, 1: 1, 0: 1})), (admin, 1, series())]
        for actor, total, growth in expected:
            response = fetch(client, actor, f'?user_id={b.id}', {'X-Forge-Ownership-Version': 'legacy'})
            assert response.status_code == 200
            assert response.json['connections'] == {'total': total, 'series': growth}
            assert response.headers['Cache-Control'] == 'no-store'
            assert response.json['engagement'] == {'posts': 1, 'likes': 7, 'comments': 0}
            assert response.json['topSearchedSkills'] == [{'skill': 'Python', 'count': 1}]
        a_response = fetch(client, a).json
        assert a_response['profileViews'] == {'total': 1, 'series': series({0: 1})}
        assert a_response['peerComparison'] == {'me': 40, 'programmeAvg': 41, 'programme': 'Software'}

    @pytest.mark.parametrize('state', ['pending', 'ignored', 'cancelled', 'disconnected', 'blocked'])
    def test_nonaccepted_and_blocked_edges_excluded(client, world, state):
        service, (a, b, _, _) = world
        edge = service.request(a, b.id, 0)
        if state in ('disconnected', 'blocked'):
            service.transition(b, edge['id'], 'accept', 1)
            if state == 'blocked':
                service.set_block(b, a.id, True, 0)
            else:
                service.transition(a, edge['id'], 'disconnect', 2)
        elif state != 'pending':
            service.transition(b if state == 'ignored' else a, edge['id'],
                               'ignore' if state == 'ignored' else 'cancel', 1)
        assert fetch(client, a).json['connections'] == {'total': 0, 'series': series()}
        if state == 'blocked':
            service.set_block(b, a.id, False, 1)
            assert fetch(client, a).json['connections'] == {'total': 0, 'series': series()}

    def test_missing_acceptance_timestamp_returns_generic_failure(client, world):
        service, (a, b, _, _) = world
        edge = connect(service, a, b, NOW)
        legacy_rows()
        with service.engine.begin() as connection:
            connection.execute(service.edge.update().where(service.edge.c.id == edge['id']).values(accepted_at=None))
        with trace_sql() as statements:
            response = fetch(client, a)
        assert response.status_code == 503
        assert response.json == {'error': 'analytics unavailable'}
        assert queried(statements, LEGACY) == set()
        assert response.headers['Cache-Control'] == 'no-store'
