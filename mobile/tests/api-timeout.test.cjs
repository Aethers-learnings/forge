const { test, beforeEach, afterEach } = require('node:test');
const assert = require('node:assert/strict');

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
  global.fetch = async () => {
    throw new TypeError('offline');
  };

  await assert.rejects(
    client.currentUser('https://forge.example/'),
    error => error.network === true &&
      error.timeout !== true &&
      error.message.includes('could not reach the server')
  );
});
