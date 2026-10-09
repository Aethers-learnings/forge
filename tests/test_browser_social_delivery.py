"""Delivery recovery and navigation in Chromium with disposable v2 HTTP.

The offline transport stub invokes actual client handlers. Real authenticated
Socket.IO room isolation is tested separately by _v2_delivery.py.
"""
import pytest

from test_browser_owned_social import browser_server
from test_browser_web_quality import chromium, page, login


def install_socket(page):
    page.add_init_script("""window.reviewHandlers = {};
      window.reviewCreated = 0; window.reviewRetired = 0;
      window.io = () => { window.reviewCreated++;
        const handlers = {}; window.reviewHandlers = handlers;
        return {on: (event, fn) => {handlers[event] = fn;},
          emit: () => {}, disconnect: () => {window.reviewRetired++;}}; };""")


def open_thread(page, base):
    install_socket(page)
    login(page, base)
    page.locator('.sidebar [data-view=messages]').click()
    page.locator('.conversation-card').first.click()
    page.get_by_role('textbox', name='Message', exact=True).wait_for()
    return page.evaluate('state.msgSlug')


@pytest.mark.parametrize('width', [390, 1280])
def test_invalidation_preserves_latest_draft_focus_and_selection(page, browser_server, width):
    slug = open_thread(page, browser_server)
    page.set_viewport_size({'width': width, 'height': 844})
    composer = page.get_by_role('textbox', name='Message', exact=True)
    composer.fill('Initial draft')
    # Hold the actual list response so typing during the refresh is covered.
    page.evaluate("""slug => {
      const original = window.fetch;
      window.fetch = async (...args) => {
        const response = await original(...args);
        if (String(args[0]).startsWith('/api/conversations?')) {
          await new Promise(resolve => {window.releaseDelivery = resolve;});
        }
        return response;
      };
      window.deliveryPending = reviewHandlers.new_message({conversationId:slug,lastSequence:55});
    }""", slug)
    page.wait_for_function('() => !!window.releaseDelivery')
    composer.fill('Unsent draft that must survive a peer message')
    composer.focus()
    composer.evaluate("input => input.setSelectionRange(7,12,'backward')")
    page.evaluate('() => {releaseDelivery(); return deliveryPending;}')
    assert composer.input_value() == 'Unsent draft that must survive a peer message'
    assert composer.evaluate("input => document.activeElement === input && input.selectionStart === 7 && input.selectionEnd === 12 && input.selectionDirection === 'backward'")
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


def test_csrf_rejection_recovers_socket_without_replaying_and_retires_old_handlers(page, browser_server):
    slug = open_thread(page, browser_server)
    page.evaluate('window.retiredHandlers = reviewHandlers;')
    mutations = []
    page.on('request', lambda request: mutations.append(request.url) if request.method == 'PATCH' else None)
    page.route('**/api/profile/visibility', lambda route: route.fulfill(
        status=403, content_type='application/json',
        body='{"error":"Invalid security token", "code":"csrf_failed"}'))
    page.evaluate("api('/api/profile/visibility', {method:'PATCH', body:JSON.stringify({profileVisible:true})}).catch(() => {})")
    page.unroute('**/api/profile/visibility')
    page.evaluate('getCsrfToken();')
    page.evaluate('socialMode()')
    assert page.evaluate('reviewCreated') == 2
    assert page.evaluate('reviewRetired') == 1
    assert len(mutations) == 1
    requests = []
    page.on('request', lambda request: requests.append(request.url))
    page.evaluate("slug => retiredHandlers.new_message({conversationId:slug,lastSequence:55})", slug)
    page.evaluate("retiredHandlers.notification({text:'Retired notice'})")
    assert requests == []
    page.evaluate("slug => reviewHandlers.new_message({conversationId:slug,lastSequence:55})", slug)
    assert any(url.endswith('/api/conversations/' + slug) for url in requests), (
        f'No history refresh after same-account CSRF recovery; sockets created={page.evaluate("reviewCreated")}'
    )


@pytest.mark.parametrize('previous', [None, 'another-thread'])
def test_message_notification_selects_authorized_thread(page, browser_server, previous):
    install_socket(page)
    login(page, browser_server)
    page.locator('button[aria-label="Notifications"]').click()
    page.get_by_role('heading', name='Notifications', exact=True).wait_for()
    note = page.evaluate("state.notes.find(note => note.type === 'owned_message')")
    assert note
    slug = note['link'].split(':')[1]
    # A previous selection must not override the notification's destination.
    page.evaluate('previous => {state.msgSlug = previous;}', previous)
    with page.expect_response(lambda response: response.url.endswith('/api/conversations/' + slug)) as refreshed:
        page.locator(f'[onclick="openNotification({note["id"]})"]').click()
    assert refreshed.value.status == 200
    assert refreshed.value.request.headers['x-forge-ownership-version'] == '2'
    assert refreshed.value.headers['cache-control'] == 'no-store'
    page.wait_for_function("() => state.view === 'messages' && document.getElementById('content').getAttribute('aria-busy') === 'false'")
    assert page.evaluate('state.msgSlug') == slug
    page.get_by_role('textbox', name='Message', exact=True).wait_for()


def test_invalidation_cannot_copy_draft_from_another_visible_thread(page, browser_server):
    slug = open_thread(page, browser_server)
    composer = page.get_by_role('textbox', name='Message', exact=True)
    composer.fill('Private draft from another thread')
    # Model the old DOM still visible while navigation has selected a new slug.
    page.locator('.chat-composer').evaluate("form => {form.dataset.conversationId = 'previous-thread';}")
    page.evaluate("slug => reviewHandlers.new_message({conversationId:slug,lastSequence:55})", slug)
    assert composer.input_value() == ''


def test_unknown_notification_hint_still_requires_http_history_lookup(page, browser_server):
    install_socket(page)
    login(page, browser_server)
    page.evaluate("state.notes = [{id:999999,type:'owned_message',link:'messages:nonmember-thread:1'}]")
    with page.expect_response(lambda response: response.url.endswith('/api/conversations/nonmember-thread')) as denied:
        page.evaluate('openNotification(999999)')
    assert denied.value.status == 404
    page.get_by_text('This item is unavailable.', exact=True).wait_for()
    assert page.locator('.bubble').count() == 0
