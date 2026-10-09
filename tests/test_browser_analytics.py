"""Chromium renders owned counts and optional failures without client cutover logic."""
import pytest

from test_browser_owned_social import browser_server
from test_browser_web_quality import chromium, page, login


@pytest.mark.parametrize('role,total', [('trade', 1), ('grad', 0)])
def test_owned_profile_analytics_mobile_keyboard(page, browser_server, role, total):
    login(page, browser_server, role)
    profile = page.locator('.sidebar [data-view=profile]')
    profile.focus()
    with page.expect_response(lambda r: r.url.endswith('/api/analytics/student')) as analytics:
        page.keyboard.press('Enter')
    assert analytics.value.status == 200
    assert analytics.value.json()['connections']['total'] == total
    assert analytics.value.headers['cache-control'] == 'no-store'
    tile = page.locator('.stat-tile', has=page.locator('.stat-label', has_text='Connections'))
    assert tile.locator('.stat-value').inner_text() == str(total)
    for width in (390, 1280):
        page.set_viewport_size({'width': width, 'height': 844})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    assert page.get_by_role('button', name='Download my data').is_enabled()


def test_maintenance_analytics_is_optional_in_profile(page, browser_server):
    login(page, browser_server)
    page.route('**/api/analytics/student', lambda route: route.fulfill(
        status=503, content_type='application/json', body='{"error":"social maintenance"}'))
    page.locator('.sidebar [data-view=profile]').click()
    page.get_by_role('heading', name='Your profile', exact=True).wait_for()
    assert page.get_by_role('button', name='Download my data').is_enabled()
    assert page.get_by_text('Your insights', exact=True).count() == 0
    assert 'social maintenance' not in page.locator('#content').inner_text()
