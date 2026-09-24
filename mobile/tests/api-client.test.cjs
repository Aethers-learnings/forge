
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

test('feed uses the stable authenticated post contract', async () => {
  let requestUrl;

  global.fetch = async (url) => {
    requestUrl = url;
    return new Response(JSON.stringify([{
      id: 4,
      name: 'Sam',
      role: 'trade',
      color: '#2c6e62',
      body: 'Hello',
      media: false,
      videoUrl: null,
      thumbUrl: null,
      pick: false,
      flagged: false,
      likeCount: 0,
      likedByMe: false,
      comments: [],
    }]), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  };

  const result = await client.getFeed('https://forge.example/');

  assert.equal(requestUrl, 'https://forge.example/api/feed');
  assert.equal(result[0].body, 'Hello');
  assert.equal(result[0].likedByMe, false);
});

test('native post creation uses CSRF protected text contract', async () => {
  const calls = [];

  global.fetch = async (url, options) => {
    calls.push([url, options]);

    if (url.endsWith('/api/auth/csrf-token')) {
      return new Response(JSON.stringify({ csrfToken: 'post-token' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    return new Response(JSON.stringify({
      id: 5,
      name: 'Sam',
      role: 'trade',
      body: 'Building Forge',
      likeCount: 0,
      likedByMe: false,
      comments: [],
    }), {
      status: 201,
      headers: { 'Content-Type': 'application/json' },
    });
  };

  const result = await client.createPost(
    'https://forge.example/',
    'Building Forge'
  );

  assert.equal(calls[1][0], 'https://forge.example/api/posts');
  assert.equal(calls[1][1].method, 'POST');
  assert.equal(calls[1][1].headers.Origin, 'https://forge.example');
  assert.equal(calls[1][1].headers['X-CSRF-Token'], 'post-token');
  assert.deepEqual(
    JSON.parse(calls[1][1].body),
    { body: 'Building Forge' }
  );
  assert.equal(result.id, 5);
});

test('native post like toggle is CSRF protected', async () => {
  const calls = [];

  global.fetch = async (url, options) => {
    calls.push([url, options]);

    if (url.endsWith('/api/auth/csrf-token')) {
      return new Response(JSON.stringify({ csrfToken: 'like-token' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    return new Response(JSON.stringify({
      id: 5,
      name: 'Sam',
      role: 'trade',
      body: 'Building Forge',
      likeCount: 1,
      likedByMe: true,
      comments: [],
    }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  };

  const result = await client.togglePostLike(
    'https://forge.example/',
    5
  );

  assert.equal(calls[1][0], 'https://forge.example/api/posts/5/like');
  assert.equal(calls[1][1].method, 'POST');
  assert.equal(calls[1][1].headers['X-CSRF-Token'], 'like-token');
  assert.equal(result.likedByMe, true);
});

test('native comments use CSRF protected text contract', async () => {
  const calls = [];

  global.fetch = async (url, options) => {
    calls.push([url, options]);

    if (url.endsWith('/api/auth/csrf-token')) {
      return new Response(JSON.stringify({ csrfToken: 'comment-token' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    return new Response(JSON.stringify({
      id: 5,
      name: 'Sam',
      role: 'trade',
      body: 'Building Forge',
      likeCount: 0,
      likedByMe: false,
      comments: [{ who: 'Alex', text: 'Nice work' }],
    }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  };

  const result = await client.addPostComment(
    'https://forge.example/',
    5,
    'Nice work'
  );

  assert.equal(
    calls[1][0],
    'https://forge.example/api/posts/5/comments'
  );
  assert.equal(calls[1][1].method, 'POST');
  assert.equal(calls[1][1].headers['X-CSRF-Token'], 'comment-token');
  assert.deepEqual(
    JSON.parse(calls[1][1].body),
    { text: 'Nice work' }
  );
  assert.equal(result.comments[0].text, 'Nice work');
});

test('opportunities use the stable authenticated list contract', async () => {
  let requestUrl;

  global.fetch = async (url) => {
    requestUrl = url;

    return new Response(JSON.stringify([
      {
        id: 8,
        title: 'Junior developer',
        co: 'Forge',
        match: 80,
        matchIsFallback: true,
        tags: ['Python'],
        applied: false,
      },
    ]), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  };

  const result = await client.getOpportunities('https://forge.example/');

  assert.equal(
    requestUrl,
    'https://forge.example/api/opportunities'
  );
  assert.equal(result[0].id, 8);
  assert.equal(result[0].applied, false);
});

test('native opportunity application toggle is CSRF protected', async () => {
  const calls = [];

  global.fetch = async (url, options) => {
    calls.push([url, options]);

    if (url.endsWith('/api/auth/csrf-token')) {
      return new Response(JSON.stringify({ csrfToken: 'apply-token' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    return new Response(JSON.stringify({
      id: 8,
      title: 'Junior developer',
      co: 'Forge',
      match: 80,
      matchIsFallback: true,
      tags: ['Python'],
      applied: true,
    }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  };

  const result = await client.toggleOpportunityApplication(
    'https://forge.example/',
    8
  );

  assert.equal(
    calls[1][0],
    'https://forge.example/api/opportunities/8/apply'
  );
  assert.equal(calls[1][1].method, 'POST');
  assert.equal(calls[1][1].headers.Origin, 'https://forge.example');
  assert.equal(
    calls[1][1].headers['X-CSRF-Token'],
    'apply-token'
  );
  assert.equal(result.applied, true);
});

test('notifications use the stable summary contract', async () => {
  let requestUrl;

  global.fetch = async (url) => {
    requestUrl = url;

    return new Response(JSON.stringify({
      notifications: [{
        id: 4,
        type: 'application',
        text: 'Your application was received.',
        link: null,
        read: false,
        createdAt: '2026-09-24T12:00:00',
      }],
      unreadCount: 1,
    }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  };

  const result = await client.getNotifications(
    'https://forge.example/'
  );

  assert.equal(
    requestUrl,
    'https://forge.example/api/notifications'
  );
  assert.equal(result.unreadCount, 1);
  assert.equal(result.notifications[0].read, false);
});

test('mark notification read is CSRF protected', async () => {
  const calls = [];

  global.fetch = async (url, options) => {
    calls.push([url, options]);

    if (url.endsWith('/api/auth/csrf-token')) {
      return new Response(JSON.stringify({
        csrfToken: 'notification-token',
      }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    return new Response(JSON.stringify({ ok: true }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  };

  await client.markNotificationRead(
    'https://forge.example/',
    4
  );

  assert.equal(
    calls[1][0],
    'https://forge.example/api/notifications/4/read'
  );
  assert.equal(calls[1][1].method, 'POST');
  assert.equal(
    calls[1][1].headers['X-CSRF-Token'],
    'notification-token'
  );
});

test('mark all notifications read is CSRF protected', async () => {
  const calls = [];

  global.fetch = async (url, options) => {
    calls.push([url, options]);

    if (url.endsWith('/api/auth/csrf-token')) {
      return new Response(JSON.stringify({
        csrfToken: 'all-read-token',
      }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    return new Response(JSON.stringify({ ok: true }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  };

  await client.markAllNotificationsRead(
    'https://forge.example/'
  );

  assert.equal(
    calls[1][0],
    'https://forge.example/api/notifications/read-all'
  );
  assert.equal(calls[1][1].method, 'POST');
  assert.equal(
    calls[1][1].headers['X-CSRF-Token'],
    'all-read-token'
  );
});

