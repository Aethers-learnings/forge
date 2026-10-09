const { test, beforeEach, afterEach } = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const { once } = require('node:events');

const client = require('../src/api/client');

let originalFetch;
let originalSetTimeout;
let originalClearTimeout;

beforeEach(() => {
  originalFetch = global.fetch;
  originalSetTimeout = global.setTimeout;
  originalClearTimeout = global.clearTimeout;
});

afterEach(() => {
  global.fetch = originalFetch;
  global.setTimeout = originalSetTimeout;
  global.clearTimeout = originalClearTimeout;
});

test('native requests abort after the bounded transport timeout', async () => {
  let cleared = null;
  let seenSignal = null;

  global.setTimeout = (callback, milliseconds) => {
    assert.equal(milliseconds, 15000);
    queueMicrotask(callback);
    return 41;
  };
  global.clearTimeout = handle => { cleared = handle; };
  global.fetch = async (_url, options) => {
    seenSignal = options.signal;
    return new Promise((_resolve, reject) => {
      options.signal.addEventListener('abort', () => {
        const error = new Error('aborted');
        error.name = 'AbortError';
        reject(error);
      }, { once: true });
    });
  };

  await assert.rejects(
    client.currentUser('https://forge.example/'),
    error => error.timeout === true &&
      error.network === true &&
      error.message.includes('too long')
  );

  assert.equal(seenSignal.aborted, true);
  assert.equal(cleared, 41);
});

test('successful native requests clear their timeout and preserve response parsing', async () => {
  let cleared = null;
  let scheduledMilliseconds = null;
  let seenSignal = null;

  global.setTimeout = (_callback, milliseconds) => {
    scheduledMilliseconds = milliseconds;
    return 73;
  };
  global.clearTimeout = handle => { cleared = handle; };
  global.fetch = async (_url, options) => {
    seenSignal = options.signal;
    return new Response(JSON.stringify({ id: 7, username: 'sam', role: 'trade' }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  };

  const result = await client.currentUser('https://forge.example/');

  assert.equal(result.username, 'sam');
  assert.equal(scheduledMilliseconds, 15000);
  assert.equal(seenSignal.aborted, false);
  assert.equal(cleared, 73);
});

test('ordinary network failures remain distinct from timeouts', async () => {
  let cleared = null;
  global.setTimeout = () => 74;
  global.clearTimeout = handle => { cleared = handle; };
  global.fetch = async () => {
    throw new TypeError('offline');
  };

  await assert.rejects(
    client.currentUser('https://forge.example/'),
    error => error.network === true &&
      error.timeout !== true &&
      error.message.includes('could not reach the server')
  );
  assert.equal(cleared, 74);
});

test('the deadline remains active until a successful body is consumed', async () => {
  let finishBody;
  let cleared = null;
  global.setTimeout = () => 101;
  global.clearTimeout = handle => { cleared = handle; };
  global.fetch = async () => ({
    ok: true,
    json: () => new Promise(resolve => { finishBody = resolve; }),
  });

  const pending = client.currentUser('https://forge.example/');
  // Wait until request() has entered the body reader.
  while (!finishBody) await Promise.resolve();
  try {
    assert.equal(cleared, null);
  } finally {
    finishBody({ id: 7 });
  }
  assert.deepEqual(await pending, { id: 7 });
  assert.equal(cleared, 101);
});

test('an abort during JSON reading is reported as a timeout, not a null body', async () => {
  let expire;
  let cleared = null;
  global.setTimeout = callback => { expire = callback; return 102; };
  global.clearTimeout = handle => { cleared = handle; };
  global.fetch = async (_url, { signal }) => ({
    ok: true,
    json: async () => {
      expire();
      assert.equal(signal.aborted, true);
      throw new DOMException('Aborted', 'AbortError');
    },
  });
  await assert.rejects(client.currentUser('https://forge.example/'),
    error => error.network === true && error.timeout === true && error.status === undefined);
  assert.equal(cleared, 102);
});

test('a body reader completing after abort cannot report success', async () => {
  let expire;
  global.setTimeout = callback => { expire = callback; return 103; };
  global.clearTimeout = () => {};
  global.fetch = async () => ({
    ok: true,
    json: async () => { expire(); return { id: 7 }; },
  });
  await assert.rejects(client.currentUser('https://forge.example/'),
    error => error.network === true && error.timeout === true);
});

for (const status of [200, 503]) {
  test(`real fetch times out on a stalled ${status} response body`, { timeout: 5000 }, async () => {
    let headersSent = false;
    const server = http.createServer((_request, response) => {
      headersSent = true;
      response.writeHead(status, { 'Content-Type': 'application/json' });
      response.write('{"partial":');
      // Deliberately never finish the body. Only abort can complete this request.
    });
    server.listen(0, '127.0.0.1');
    await once(server, 'listening');
    // Keep real fetch/AbortController semantics, accelerating only the deadline.
    global.setTimeout = (callback, milliseconds, ...args) => originalSetTimeout(
      callback, milliseconds === 15000 ? 250 : milliseconds, ...args);
    // Release the original implementation's unbounded body read on failure.
    const watchdog = originalSetTimeout(() => server.closeAllConnections(), 1500);
    try {
      await assert.rejects(client.currentUser(`http://127.0.0.1:${server.address().port}/`),
        error => error.network === true && error.timeout === true && error.status === undefined);
      assert.equal(headersSent, true, 'the timeout must occur after headers have arrived');
    } finally {
      originalClearTimeout(watchdog);
      server.closeAllConnections();
      await new Promise(resolve => server.close(resolve));
    }
  });
}

for (const status of [200, 502]) {
  test(`malformed JSON retains the existing ${status} behavior and clears the timer`, async () => {
    let cleared = null;
    global.setTimeout = () => 104;
    global.clearTimeout = handle => { cleared = handle; };
    global.fetch = async () => new Response('not JSON', { status });
    if (status === 200) {
      assert.equal(await client.currentUser('https://forge.example/'), null);
    } else {
      await assert.rejects(client.currentUser('https://forge.example/'),
        error => error.status === status && error.body === null &&
          error.message === `Forge returned HTTP ${status}.` &&
          error.network === undefined && error.timeout === undefined);
    }
    assert.equal(cleared, 104);
  });
}

test('server errors retain their status and body and clear the deadline', async () => {
  let cleared = null;
  global.setTimeout = () => 105;
  global.clearTimeout = handle => { cleared = handle; };
  global.fetch = async () => new Response('{"error":"Not permitted"}', { status: 403 });
  await assert.rejects(client.currentUser('https://forge.example/'),
    error => error.status === 403 && error.message === 'Not permitted' &&
      error.body.error === 'Not permitted' && error.network === undefined && error.timeout === undefined);
  assert.equal(cleared, 105);
});
