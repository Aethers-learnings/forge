"""Real Chromium checks against a local, migration-managed throwaway Forge server.

Install requirements-browser.txt and `python -m playwright install chromium`.
Run `pytest tests/test_browser_web_quality.py`. No production database is opened.
"""
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import urllib.request

import pytest

sync_playwright = pytest.importorskip("playwright.sync_api").sync_playwright


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def browser_server():
    with tempfile.TemporaryDirectory(prefix="forge-browser-", dir=ROOT / "tests") as directory:
        root = Path(directory)
        database = root / "browser.db"
        env = os.environ.copy()
        env.update(
            FORGE_DATABASE_URI=f"sqlite:///{database}",
            FORGE_SECRET_KEY="browser-test-secret-at-least-thirty-two-chars",
            FORGE_ENV="test",
            FORGE_SOCIAL_MODE="v2",
            FORGE_DEMO_MODE="0",
            FORGE_UPLOAD_DIR=str(root / "uploads"),
            FORGE_PROFILE_IMAGE_DIR=str(root / "profile_images"),
        )
        # Import and seed only after the disposable database path is set.
        setup = """from sqlalchemy import create_engine
from forge_migrations import initialize_fresh_database
import os
engine = create_engine(os.environ['FORGE_DATABASE_URI'])
initialize_fresh_database(engine)
engine.dispose()
import forge_backend as b
with b.app.app_context():
    b.seed_demo_data()
    from forge_routes.owned_social import OwnedSocialService
    svc = OwnedSocialService(b.db.engine, b)
    actor = b.User.query.filter_by(username='demo_trade').one()
    peers = [b.User(username=f'owned_{i}', name=f'Owned peer {i:02}', role='trade',
                    password_hash='unused', color='#123456') for i in range(25)]
    b.db.session.add_all(peers)
    b.db.session.commit()
    edge = svc.request(actor, peers[0].id, 0)
    svc.transition(peers[0], edge['id'], 'accept', 1)
    convo = svc.open_conversation(actor, peers[0].id)
    for i in range(55):
        svc.send(peers[0], convo['public_id'], f'History message {i+1}', f'seed-{i}')
    svc.request(peers[1], actor.id, 0)
    svc.request(actor, peers[2].id, 0)

"""
        subprocess.run([sys.executable, "-c", setup], cwd=ROOT, env=env, check=True)
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        base = f"http://127.0.0.1:{port}"
        server = subprocess.Popen(
            [sys.executable, "-m", "flask", "--app", "forge_backend:app", "run",
             "--host", "127.0.0.1", "--port", str(port), "--no-reload"],
            cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )
        try:
            import time
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                if server.poll() is not None:
                    raise RuntimeError(f"Forge server exited: {server.stderr.read().decode()[-2000:]}")
                try:
                    urllib.request.urlopen(base + "/api/auth/me", timeout=0.2).close()
                    break
                except OSError:
                    time.sleep(0.05)
            else:
                raise RuntimeError("Forge server did not start")
            yield base
        finally:
            server.terminate()
            try:
                server.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.communicate()



from test_browser_web_quality import chromium, page, login  # reuse real Chromium harness


def test_owned_network_actions_and_paging(page, browser_server):
    login(page, browser_server)
    page.locator('.sidebar [data-view=network]').click()
    page.get_by_role('heading', name='Incoming requests').wait_for()
    assert page.get_by_role('heading', name='Outgoing requests').is_visible()
    page.get_by_role('button', name='Load more suggested for you').click()
    page.get_by_role('button', name='Load more suggested for you').wait_for(state='detached')
    page.get_by_role('button', name='Cancel request', exact=True).click()
    page.locator('.card', has_text='Owned peer 02').wait_for(state='detached')
    page.get_by_role('button', name='Accept', exact=True).click()
    page.get_by_role('button', name='Ignore', exact=True).wait_for(state='detached')
    with page.expect_response(lambda response: response.url.endswith('/api/conversations') and response.request.method == 'POST') as created:
        page.locator('.card', has_text='Owned peer 01').get_by_role('button', name='Message', exact=True).click()
    assert created.value.status == 201
    page.get_by_role('textbox', name='Message', exact=True).wait_for()
    page.locator('.sidebar [data-view=network]').click()
    card = page.locator('.card', has_text='Owned peer 00')
    card.get_by_role('button', name='Endorse', exact=True).click()
    card.get_by_role('button', name='Remove endorsement', exact=True).wait_for()
    card.get_by_role('button', name='Remove endorsement', exact=True).click()
    card.get_by_role('button', name='Endorse', exact=True).wait_for()
    for width in (390, 1280):
        page.set_viewport_size({'width': width, 'height': 844})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


def test_owned_real_thread_history_send_read_and_readonly(page, browser_server):
    login(page, browser_server)
    page.locator('.sidebar [data-view=network]').click()
    card = page.locator('.card', has_text='Owned peer 00')
    reads = []
    page.on('request', lambda request: reads.append(request.post_data_json['upToSequence']) if request.url.endswith('/read') else None)
    card.get_by_role('button', name='Message', exact=True).click()
    page.get_by_role('button', name='Load older messages').wait_for()
    assert page.locator('[data-social-sequence]').count() == 50
    page.locator('[data-social-sequence="55"]').scroll_into_view_if_needed()
    page.wait_for_timeout(200)  # allow real IntersectionObserver delivery
    assert reads == []  # unloaded sequences 1..5 block the latest page
    with page.expect_response(lambda response: response.url.endswith('/read')) as read_response:
        page.get_by_role('button', name='Load older messages').click()
        page.locator('[data-social-sequence="1"]').scroll_into_view_if_needed()
    assert 0 < read_response.value.json()['lastReadSequence'] <= 55
    page.locator('[data-social-sequence="1"]').wait_for()
    sequences = page.locator('[data-social-sequence]').evaluate_all('(nodes)=>nodes.map(n=>+n.dataset.socialSequence)')
    assert sequences == list(range(1, 56))
    page.get_by_role('textbox', name='Message', exact=True).fill('Real user message')
    page.get_by_role('button', name='Send', exact=True).click()
    page.locator('.bubble', has_text='Real user message').wait_for()
    assert page.locator('[data-social-sequence]').count() == 56
    slug = page.evaluate('state.msgSlug')
    page.locator('.sidebar [data-view=network]').click()
    page.locator('.card', has_text='Owned peer 00').get_by_role('button', name='Disconnect', exact=True).click()
    page.locator('.card', has_text='Owned peer 00').wait_for(state='detached')
    page.locator('.sidebar [data-view=messages]').click()
    page.get_by_text('This conversation is read-only.', exact=False).wait_for()
    assert page.get_by_role('textbox', name='Message', exact=True).is_disabled()
    assert page.get_by_role('button', name='Send', exact=True).is_disabled()
    assert page.evaluate('state.msgSlug') == slug


def test_owned_errors_update_and_no_fallback(page, browser_server):
    login(page, browser_server)
    requests = []
    def unavailable(route):
        requests.append(route.request)
        route.fulfill(status=426, content_type='application/json', body='{"error":"private detail"}')
    page.route('**/api/network?*', unavailable)
    page.locator('.sidebar [data-view=network]').click()
    page.get_by_text('Forge needs an updated client.', exact=False).wait_for()
    assert len(requests) == 1
    assert requests[0].headers['x-forge-ownership-version'] == '2'
    assert 'private detail' not in page.locator('#content').inner_text()
    page.unroute('**/api/network?*', unavailable)


def test_owned_keyboard_list_and_mobile_thread(page, browser_server):
    login(page, browser_server)
    page.locator('.sidebar [data-view=messages]').click()
    card = page.locator('.conversation-card').first
    card.wait_for()
    card.focus()
    page.keyboard.press('Enter')
    page.locator('.message-thread').wait_for()
    page.set_viewport_size({'width':390,'height':844})
    page.emulate_media(reduced_motion='reduce')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    assert page.get_by_role('textbox', name='Message', exact=True).count() == 1


def test_owned_read_observer_does_not_skip_visible_later_message(page, browser_server):
    # Real IntersectionObserver and scrolling; deterministic three-message HTTP fixture.
    page.add_init_script("""new MutationObserver(() => {
      const thread = document.querySelector('.message-thread');
      if (!thread || thread.dataset.positioned) return;
      thread.dataset.positioned = 'true';
      thread.style.cssText = 'padding:0;flex:none;height:300px;max-height:300px;overflow:auto;display:block;scroll-behavior:auto!important';
      thread.querySelectorAll('.bubble').forEach(node => node.style.cssText = 'height:600px;margin:0');
      thread.scrollTop = 1200;
    }).observe(document, {childList:true,subtree:true});""")
    reads = []
    def history(route):
        import json
        response = route.fetch()
        data = response.json()
        data.update(messages=[{'sequence': i, 'who': 'them', 'text': f'Incoming {i}',
                               'createdAt': '2026-09-29T00:00:00Z'} for i in (1, 2, 3)],
                    lastReadSequence=0, lastSequence=3, unreadCount=3, hasMore=False, nextCursor=None)
        route.fulfill(response=response, body=json.dumps(data))
    def read(route):
        import json
        cursor = route.request.post_data_json['upToSequence']
        reads.append(cursor)
        route.fulfill(status=200, content_type='application/json',
                      body=json.dumps({'lastReadSequence': cursor, 'unreadCount': 3-cursor}))
    page.route('**/api/conversations/*', history)
    page.route('**/api/conversations/*/read', read)
    login(page, browser_server)
    page.locator('.sidebar [data-view=messages]').click()
    page.locator('.conversation-card').first.click()
    page.locator('[data-social-sequence="3"]').wait_for()
    page.wait_for_timeout(200)
    assert page.locator('.message-thread').evaluate('(node) => node.scrollTop') == 1200
    assert reads == []
    assert page.evaluate('Array.from(social.threads.get(state.msgSlug).observedSequences)') == [3]
    with page.expect_response(lambda response: response.url.endswith('/read')):
        page.locator('.message-thread').evaluate('(node) => {node.scrollTop = 0;}')
    assert reads == [1]
    with page.expect_response(lambda response: response.url.endswith('/read')):
        page.locator('.message-thread').evaluate('(node) => {node.scrollTop = 600;}')
    assert reads == [1, 3]  # sequence 3 was already observed, but could not skip 1/2
    page.locator('.message-thread').evaluate('(node) => {node.scrollTop = 1200;}')
    page.wait_for_timeout(200)
    assert reads == [1, 3]


def test_minimal_socket_invalidation_authorized_refresh_and_retired_account(page, browser_server):
    # CDN remains offline in this harness; backend tests exercise real sockets.
    # Feed the actual browser handlers while observing real HTTP authorization.
    page.add_init_script("""window.forgeSocketHandlers = {};
      window.forgeSocketRetired = 0;
      window.io = () => ({on: (event, fn) => {window.forgeSocketHandlers[event] = fn;},
        emit: () => {}, disconnect: () => {window.forgeSocketRetired++;}});""")
    login(page, browser_server)
    page.locator('.sidebar [data-view=messages]').click()
    card = page.locator('.conversation-card').first
    card.wait_for(); card.focus(); page.keyboard.press('Enter')
    page.locator('.message-thread').wait_for()
    slug = page.evaluate('state.msgSlug')
    with page.expect_response(lambda response: response.url.endswith('/api/conversations/' + slug)) as refreshed:
        page.evaluate("slug => forgeSocketHandlers.new_message({conversationId:slug,lastSequence:1})", slug)
    assert refreshed.value.status == 200
    assert refreshed.value.request.headers['x-forge-ownership-version'] == '2'
    assert refreshed.value.headers['cache-control'] == 'no-store'
    page.set_viewport_size({'width': 390, 'height': 844})
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.evaluate("slug => forgeSocketHandlers.new_message({conversationId:slug,lastSequence:999,text:'SOCKET SECRET',conversation:{messages:[{text:'SOCKET SECRET'}]}})", slug)
    assert 'SOCKET SECRET' not in page.locator('body').inner_text()
    page.evaluate("window.oldForgeHandlers = forgeSocketHandlers; setCurrentUser(null,true);")
    assert page.evaluate('forgeSocketRetired') == 1
    requests = []
    page.on('request', lambda request: requests.append(request.url))
    page.evaluate("slug => oldForgeHandlers.new_message({conversationId:slug,lastSequence:1})", slug)
    page.evaluate("oldForgeHandlers.notification({text:'SOCKET SECRET'})")
    page.wait_for_timeout(100)
    assert requests == [] and page.evaluate('social.threads.size') == 0
