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
