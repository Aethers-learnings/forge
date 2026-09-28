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


@pytest.fixture(scope="module")
def chromium():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        yield browser
        browser.close()


@pytest.fixture
def page(chromium, browser_server, request):
    context = chromium.new_context()
    # Optional third-party font/socket script is unavailable in offline CI.
    # The app's own CSP is served unchanged and API requests stay same-origin.
    context.route("https://**/*", lambda route: route.abort())
    tab = context.new_page()
    try:
        yield tab
    except Exception:
        artifact = ROOT / "test-results"
        artifact.mkdir(exist_ok=True)
        tab.screenshot(path=str(artifact / f"{request.node.name}.png"), full_page=True)
        raise
    finally:
        context.close()


def login(page, base, role="trade"):
    page.goto(base)
    page.locator('input[name="username"]').fill(f"demo_{role}")
    page.locator('input[name="password"]').fill("demo123")
    page.locator('form button[type=submit], form button.btn-primary.full').first.click()
    page.locator("#content[aria-busy=false] .composer").wait_for()
    page.locator(".onboarding-overlay button", has_text="Skip for now").first.click() if page.locator(".onboarding-overlay button", has_text="Skip for now").count() else None


def test_login_shell_role_nav_and_security_headers(page, browser_server):
    response = page.goto(browser_server)
    assert response.status == 200
    headers = response.headers
    assert "script-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com" in headers["content-security-policy"]
    assert headers["x-frame-options"] == "DENY"
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["cross-origin-opener-policy"] == "same-origin"
    assert page.locator('form button.btn-primary.full').is_visible()
    login(page, browser_server)
    assert page.locator(".sidebar [data-view=discover]").count() == 1
    assert page.locator(".sidebar [data-view=admin]").count() == 0
    assert page.locator(".sidebar [data-view=feed]").get_attribute("aria-current") == "page"


@pytest.mark.parametrize("role,expected,absent", [
    ("business", "listings", "discover"), ("admin", "admin", "listings"),
    ("grad", "discover", "admin"),
])
def test_role_navigation(page, browser_server, role, expected, absent):
    login(page, browser_server, role)
    assert page.locator(f".sidebar [data-view={expected}]").count() == 1
    assert page.locator(f".sidebar [data-view={absent}]").count() == 0


def test_skip_focus_dynamic_labels_and_keyboard_card(page, browser_server):
    login(page, browser_server)
    page.keyboard.press("Control+Home")
    page.locator(".skip-link").focus()
    page.keyboard.press("Enter")
    page.wait_for_function("document.activeElement?.id === 'content'")
    page.locator(".sidebar [data-view=profile]").click()
    page.locator("#content[aria-busy=false] .field label").first.wait_for()
    assert page.locator("#content .field label[for]").count() > 0
    assert page.evaluate("""() => [...document.querySelectorAll('#content .field label[for]')]
        .every(label => document.getElementById(label.htmlFor))""")
    page.locator(".sidebar [data-view=messages]").click()
    page.locator("#content[aria-busy=false] .conversation-card[onclick]").first.wait_for()
    card = page.locator("#content .conversation-card[onclick]").first
    assert card.get_attribute("role") == "button"
    card.focus()
    page.keyboard.press("Enter")
    page.locator("#content[aria-busy=false]").wait_for()
    assert page.evaluate("state.msgSlug !== null")


def test_delayed_loading_retry_and_busy_clear(page, browser_server):
    login(page, browser_server)
    pending = []
    def delay(route):
        pending.append(route)
    page.route("**/api/network", delay)
    page.locator(".sidebar [data-view=network]").click()
    page.locator("#content[aria-busy=true] .loading").wait_for()
    assert pending
    pending.pop().fulfill(status=503, content_type="application/json", body='{"error":"temporary"}')
    page.get_by_role("button", name="Try again").wait_for()
    page.unroute("**/api/network", delay)
    page.get_by_role("button", name="Try again").click()
    page.locator("#content[aria-busy=false]").wait_for()
    assert page.get_by_role("button", name="Try again").count() == 0


def test_offline_reconnect_and_mutation_dedup(page, browser_server):
    login(page, browser_server)
    page.context.set_offline(True)
    page.locator("#network-status").wait_for(state="visible")
    page.context.set_offline(False)
    page.locator("#network-status").wait_for(state="hidden")
    pending = []
    def delay(route):
        pending.append(route)
    page.route("**/api/posts", delay)
    page.locator('.composer textarea[name="body"]').fill("browser pending test")
    button = page.get_by_role("button", name="Publish post")
    button.click()
    page.locator(".composer button[aria-busy=true][disabled]").wait_for()
    page.locator(".composer button[aria-busy=true]").click(force=True)
    assert len(pending) == 1
    pending[0].continue_()
    page.locator("#content[aria-busy=false]").wait_for()
    assert len(pending) == 1


def test_escaped_user_text_responsive_and_reduced_motion(page, browser_server):
    login(page, browser_server)
    marker = '<img src=x onerror="window.__injected=1">'
    page.locator('.composer textarea[name="body"]').fill(marker)
    page.get_by_role("button", name="Publish post").click()
    page.locator(".post-copy", has_text=marker).first.wait_for()
    assert page.evaluate("window.__injected") is None
    assert page.locator(".post-copy img").count() == 0
    for width, height in ((1280, 800), (390, 844)):
        page.set_viewport_size({"width": width, "height": height})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.emulate_media(reduced_motion="reduce")
    page.locator(".bottomnav [data-view=profile]").click()
    page.locator("#content[aria-busy=false]").wait_for()
    assert page.locator("#content").is_visible()
