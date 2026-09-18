const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const html = fs.readFileSync(path.join(__dirname, '../static/forge_demo.html'), 'utf8');
for (const match of html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)) new vm.Script(match[1]);
const helpers = html.slice(html.indexOf('let csrfToken = null;'), html.indexOf('let toastTimer = null;'));
const logout = html.slice(html.indexOf('async function logout()'), html.indexOf('/* ==================================================================== */', html.indexOf('async function logout()')));
const upload = html.slice(html.indexOf('async function uploadVideo('), html.indexOf('async function likePost('));
function setup() {
  const calls = [];
  const context = vm.createContext({ Headers, FormData, Blob, state: { user: null }, socket: null,
    document: { getElementById: () => null }, toast: () => {}, loadView: () => {}, renderApp: () => {},
    fetch: async (url, options) => {
      calls.push({url, options});
      return { ok: true, status: 200, json: async () => url === '/api/auth/csrf-token' ? {csrfToken: 'token'} : {} };
    }
  });
  vm.runInContext(helpers + logout + upload, context);
  return { context, calls, run: code => vm.runInContext(code, context) };
}
(async () => {
  let { context, calls, run } = setup();
  await run("api('/api/auth/login', {method: 'POST'})");
  assert.equal(calls.length, 1);
  assert.equal(calls[0].options.headers.has('X-CSRF-Token'), false);
  run("setCurrentUser({id: 1, name: 'Alice'}, true)");
  await run("Promise.all(['POST','PUT','PATCH','DELETE'].map(method => api('/api/example', {method, headers: {'X-Test': 'kept'}})))");
  assert.equal(calls.filter(c => c.url === '/api/auth/csrf-token').length, 1);
  for (const call of calls.filter(c => c.url === '/api/example')) {
    assert.equal(call.options.headers.get('X-CSRF-Token'), 'token');
    assert.equal(call.options.headers.get('X-Test'), 'kept');
  }
  await run("api('/api/feed')");
  assert.equal(calls.at(-1).options.headers.has('X-CSRF-Token'), false);
  await run("uploadVideo({files: [new Blob(['test'], {type: 'video/mp4'})]})");
  const video = calls.at(-1);
  assert.equal(video.url, '/api/posts/video');
  assert.equal(new Headers(video.options.headers).get('X-CSRF-Token'), 'token');
  assert.equal(new Headers(video.options.headers).has('Content-Type'), false);
  assert.ok(video.options.body instanceof FormData);
  run("setCurrentUser({id: 2}, true)");
  await run("api('/api/example', {method: 'PATCH'})");
  assert.equal(calls.filter(c => c.url === '/api/auth/csrf-token').length, 2);
  run("setCurrentUser({id: 2}, true)");
  await run("api('/api/example', {method: 'POST'})");
  assert.equal(calls.filter(c => c.url === '/api/auth/csrf-token').length, 3);
  let disconnected = false;
  context.socket = { disconnect: () => { disconnected = true; } };
  await run('logout()');
  assert.equal(context.state.user, null);
  assert.equal(run('csrfToken'), null);
  assert.equal(disconnected, true);
  assert.equal(calls.at(-1).options.headers.get('X-CSRF-Token'), 'token');

  ({ context, calls, run } = setup());
  run('setCurrentUser({id: 1})');
  const baseFetch = context.fetch;
  context.fetch = async (url, opts) => url === '/api/auth/logout'
    ? {ok: false, status: 403, json: async () => ({code: 'csrf_failed'})} : baseFetch(url, opts);
  await run('logout()');
  assert.equal(context.state.user.id, 1, 'failed logout must not pretend to end the session');
  assert.equal(run('csrfToken'), null);

  ({ context, calls, run } = setup());
  run('setCurrentUser({id: 1})');
  let resolve;
  context.fetch = () => new Promise(r => { resolve = r; });
  const pending = run("api('/api/example', {method: 'POST'})");
  run('setCurrentUser({id: 2}, true)');
  resolve({ok: true, json: async () => ({csrfToken: 'old-identity-token'})});
  await assert.rejects(pending);
  assert.equal(run('csrfToken'), null, 'late response must not repopulate an obsolete token');
  console.log('Frontend CSRF helper, multipart, identity, concurrency, and logout regressions passed.');
})().catch(error => { console.error(error); process.exitCode = 1; });
