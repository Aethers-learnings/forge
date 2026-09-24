const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const html = fs.readFileSync(require('node:path').join(__dirname, '../static/forge_demo.html'), 'utf8');
const helpers = html.slice(html.indexOf('let csrfToken = null;'), html.indexOf('let toastTimer = null;'));
const profile = html.slice(html.indexOf('let profileExportBusy = false;'), html.indexOf('async function toggleVisibility('));

function setup() {
  const calls = [], downloads = [], blobs = [], revoked = [], timers = [];
  const elements = {
    'profile-export': { setAttribute(key, value) { this[key] = value; } },
    'profile-export-status': {},
  };
  const user = { id: 1, role: 'trade', skills: [], portfolio: {}, visibility: {} };
  const payload = '{"profile":{"id":1},"notifications":[]}';
  const context = vm.createContext({ Headers, state: { user }, navigator: { onLine: true },
    esc: String, prettyRole: String, avatarHtml: () => '', studentAnalyticsHtml: async () => '',
    document: {
      getElementById: id => elements[id],
      body: { appendChild: link => { link.attached = true; } },
      createElement: tag => {
        assert.equal(tag, 'a');
        return { click() { assert.equal(this.attached, true); downloads.push(this); },
          remove() { this.attached = false; } };
      },
    },
    URL: { createObjectURL: blob => { blobs.push(blob); return 'blob:export'; },
      revokeObjectURL: url => revoked.push(url) },
    setTimeout: callback => timers.push(callback),
    fetch: async (url, options) => {
      calls.push({ url, options });
      return url === '/api/auth/me'
        ? new Response(JSON.stringify(user))
        : new Response(payload, { headers: { 'Content-Disposition': 'attachment; filename="forge-my-data.json"' } });
    },
  });
  const run = code => vm.runInContext(code, context);
  run(helpers + profile);
  return { context, run, calls, downloads, blobs, revoked, timers, elements, user, payload };
}

(async () => {
  const s = setup();
  for (const role of ['trade', 'grad', 'business', 'admin']) {
    s.user.role = role;
    const rendered = await s.run('renderProfileView()');
    assert.equal((rendered.match(/id="profile-export"/g) || []).length, 1, role);
    assert.match(rendered, /<button type="button" id="profile-export"/);
    assert.match(rendered, /onclick="downloadProfileData\(\)"/);
    assert.match(rendered, /aria-describedby="profile-export-status"/);
    assert.match(rendered, /role="status" aria-live="polite" aria-atomic="true"/);
    assert.doesNotMatch(rendered, /href="\/api\/profile\/export"/);
  }
  s.calls.length = 0;
  let finish;
  const fetch = s.context.fetch;
  s.context.fetch = async (...args) => { await new Promise(resolve => { finish = resolve; }); return fetch(...args); };
  const pending = s.run('downloadProfileData()');
  await Promise.resolve();
  assert.equal(s.elements['profile-export'].disabled, true);
  assert.equal(s.elements['profile-export']['aria-busy'], 'true');
  assert.match(s.elements['profile-export-status'].textContent, /Preparing/);
  // A new profile render while the request is pending must also stay disabled.
  assert.match(s.run('profileExportControls()'), /disabled/);
  await s.run('downloadProfileData()');
  finish();
  await pending;
  assert.equal(s.calls.length, 1);
  assert.equal(s.calls[0].url, '/api/profile/export');
  assert.equal(s.calls[0].options.credentials, 'same-origin');
  assert.equal(s.calls[0].options.method, 'GET');
  assert.equal(s.calls[0].options.cache, 'no-store');
  assert.equal(s.downloads[0].download, 'forge-my-data.json');
  assert.equal(await s.blobs[0].text(), s.payload);
  assert.equal(s.downloads[0].attached, false);
  s.timers.forEach(callback => callback());
  assert.deepEqual(s.revoked, ['blob:export']);
  assert.equal(s.elements['profile-export'].disabled, false);
  assert.match(s.elements['profile-export-status'].textContent, /Download started/);

  for (const [response, expected] of [
    [() => new Response('{"error":"Please try again later."}', { status: 500 }), /try again later/],
    [() => new Response('Unauthorized', { status: 401 }), /Sign in again/],
    [() => new Response('Forbidden', { status: 403 }), /Please try again/],
    [() => { throw new TypeError('Network failed'); }, /Check your connection/],
  ]) {
    const t = setup();
    t.context.fetch = async () => response();
    await t.run('downloadProfileData()');
    assert.match(t.elements['profile-export-status'].textContent, expected);
    assert.equal(t.elements['profile-export'].disabled, false);
    assert.equal(t.elements['profile-export']['aria-busy'], 'false');
    assert.equal(t.downloads.length, 0);
    t.context.fetch = async () => new Response('{}');
    await t.run('downloadProfileData()');
    assert.equal(t.downloads[0].download, 'forge-my-data.json', 'retry and missing-header fallback');
  }

  const t = setup();
  t.context.fetch = async () => new Response('{}', { headers: { 'Content-Disposition': 'attachment; filename="custom.json"' } });
  await t.run('downloadProfileData()');
  assert.equal(t.downloads[0].download, 'custom.json');
  t.context.fetch = async () => {
    t.run('setCurrentUser({id: 2}, true)');
    return new Response('{}');
  };
  await t.run('downloadProfileData()');
  assert.equal(t.downloads.length, 1, 'do not download a stale account response');
  assert.equal(t.elements['profile-export'].disabled, false);
  console.log('Profile export roles, session request, download, busy, recovery, and identity tests passed.');
})().catch(error => { console.error(error); process.exitCode = 1; });
