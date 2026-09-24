from pathlib import Path


HTML = Path("static/forge_demo.html").read_text()


def test_web_shell_has_keyboard_skip_navigation():
    assert 'class="skip-link" href="#content"' in HTML
    assert "main.setAttribute('tabindex', '-1')" in HTML
    assert "main.focus()" in HTML


def test_user_feedback_regions_are_announced_accessibly():
    assert 'id="toast"' in HTML
    assert 'aria-live="polite"' in HTML
    assert 'aria-atomic="true"' in HTML
    assert 'id="network-status"' in HTML


def test_offline_state_is_visible_and_recovers_on_reconnect():
    assert "window.addEventListener('offline', syncNetworkStatus)" in HTML
    assert "window.addEventListener('online', syncNetworkStatus)" in HTML
    assert "You’re offline." in HTML

def test_failed_view_has_actionable_retry_for_transient_errors():
    assert 'Couldn’t load this view.' in HTML
    assert 'onclick="loadView()">Try again</button>' in HTML
    assert "e.status >= 500" in HTML


def test_network_failures_are_distinguished_from_server_errors():
    assert "Forge could not reach the server. Check your connection and try again." in HTML
    assert "You’re offline. Reconnect and try again." in HTML
    assert "network: true" in HTML


def test_view_loading_rejects_stale_responses_and_exposes_busy_state():
    assert "let viewLoadGeneration = 0;" in HTML
    assert "const generation = ++viewLoadGeneration;" in HTML
    assert "generation !== viewLoadGeneration" in HTML
    assert "content.setAttribute('aria-busy', 'true')" in HTML
    assert "content.setAttribute('aria-busy', 'false')" in HTML
    assert 'role="status" aria-live="polite"' in HTML


def test_common_mutations_disable_trigger_buttons_while_pending():
    assert "async function runBusyButton(button, busyText, task)" in HTML
    assert "button.setAttribute('aria-busy', 'true')" in HTML
    assert 'likePost(${p.id}, this)' in HTML
    assert 'applyOpp(${o.id}, this)' in HTML
    assert 'toggleInterest(${e.id}, this)' in HTML
    assert "runBusyButton(ev.submitter, 'Publishing…'" in HTML
    assert "runBusyButton(ev.submitter, 'Sending…'" in HTML
    assert "runBusyButton(ev.submitter, 'Thinking…'" in HTML

