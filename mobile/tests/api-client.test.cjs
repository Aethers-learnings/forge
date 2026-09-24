
const { test, beforeEach, afterEach } = require('node:test');
const assert = require('node:assert/strict');

const client = require('../src/api/client');

let originalFetch;

beforeEach(() => {
  originalFetch = global.fetch;
});

afterEach(() => {
  global.fetch = originalFetch;
});

test('currentUser requests the contracted auth session endpoint', async () => {
  const calls = [];
  global.fetch = async (url, options) => {
    calls.push([url, options]);
    return new Response(JSON.stringify({ id: 7, username: 'sam', role: 'trade' }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  };

  const user = await client.currentUser('https://forge.example/');

  assert.equal(user.username, 'sam');
  assert.equal(calls[0][0], 'https://forge.example/api/auth/me');
  assert.equal(calls[0][1].credentials, 'include');
});

test('login uses the stable username/password contract', async () => {
  let request;

  global.fetch = async (url, options) => {
    request = { url, options };
    return new Response(JSON.stringify({ id: 7, username: 'sam', role: 'trade' }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  };

  await client.login('https://forge.example/', 'sam', 'password123');

  assert.equal(request.url, 'https://forge.example/api/auth/login');
  assert.equal(request.options.method, 'POST');
  assert.deepEqual(
    JSON.parse(request.options.body),
    { username: 'sam', password: 'password123' }
  );
});

test('server error messages are preserved for native UI', async () => {
  global.fetch = async () => new Response(
    JSON.stringify({ error: 'Invalid username or password' }),
    {
      status: 401,
      headers: { 'Content-Type': 'application/json' },
    }
  );

  await assert.rejects(
    client.login('https://forge.example/', 'sam', 'wrong'),
    error => error.status === 401 &&
      error.message === 'Invalid username or password'
  );
});

test('logout obtains CSRF token and sends same-origin protection headers', async () => {
  const calls = [];

  global.fetch = async (url, options) => {
    calls.push([url, options]);

    if (url.endsWith('/api/auth/csrf-token')) {
      return new Response(JSON.stringify({ csrfToken: 'token-123' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    return new Response(JSON.stringify({ ok: true }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  };

  await client.logout('https://forge.example/app');

  assert.equal(calls[1][0], 'https://forge.example/api/auth/logout');
  assert.equal(calls[1][1].method, 'POST');
  assert.equal(calls[1][1].headers.Origin, 'https://forge.example');
  assert.equal(calls[1][1].headers['X-CSRF-Token'], 'token-123');
});

test('network failure becomes a useful native error', async () => {
  global.fetch = async () => {
    throw new TypeError('network down');
  };

  await assert.rejects(
    client.currentUser('https://forge.example/'),
    error => error.network === true &&
      error.message.includes('could not reach the server')
  );
});

test('onboarding can be loaded from the native client', async () => {
  let requestUrl;

  global.fetch = async (url) => {
    requestUrl = url;
    return new Response(JSON.stringify({
      steps: ['welcome', 'add-photo'],
      step: 0,
      complete: false,
    }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  };

  const result = await client.getOnboarding('https://forge.example/');

  assert.equal(requestUrl, 'https://forge.example/api/onboarding');
  assert.equal(result.complete, false);
  assert.deepEqual(result.steps, ['welcome', 'add-photo']);
});

test('advance onboarding uses CSRF protected POST', async () => {
  const calls = [];

  global.fetch = async (url, options) => {
    calls.push([url, options]);

    if (url.endsWith('/api/auth/csrf-token')) {
      return new Response(JSON.stringify({ csrfToken: 'native-token' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    return new Response(JSON.stringify({
      steps: ['welcome', 'add-photo'],
      step: 1,
      complete: true,
    }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  };

  const result = await client.advanceOnboarding('https://forge.example/');

  assert.equal(calls[1][0], 'https://forge.example/api/onboarding/advance');
  assert.equal(calls[1][1].method, 'POST');
  assert.equal(calls[1][1].headers.Origin, 'https://forge.example');
  assert.equal(calls[1][1].headers['X-CSRF-Token'], 'native-token');
  assert.equal(result.complete, true);
});

test('skip onboarding uses the same CSRF protection', async () => {
  const calls = [];

  global.fetch = async (url, options) => {
    calls.push([url, options]);

    if (url.endsWith('/api/auth/csrf-token')) {
      return new Response(JSON.stringify({ csrfToken: 'skip-token' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    return new Response(JSON.stringify({
      steps: ['welcome'],
      step: 0,
      complete: true,
    }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  };

  await client.skipOnboarding('https://forge.example/');

  assert.equal(calls[1][0], 'https://forge.example/api/onboarding/skip');
  assert.equal(calls[1][1].method, 'POST');
  assert.equal(calls[1][1].headers['X-CSRF-Token'], 'skip-token');
});

