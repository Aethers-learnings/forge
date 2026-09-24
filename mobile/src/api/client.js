
function apiUrl(baseUrl, path) {
  return new URL(path, baseUrl).href;
}

async function parseJson(response) {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

async function request(baseUrl, path, options = {}) {
  let response;

  try {
    response = await fetch(apiUrl(baseUrl, path), {
      credentials: 'include',
      ...options,
      headers: {
        Accept: 'application/json',
        ...(options.body ? { 'Content-Type': 'application/json' } : {}),
        ...(options.headers || {}),
      },
    });
  } catch {
    const error = new Error('Forge could not reach the server. Check your connection and try again.');
    error.network = true;
    throw error;
  }

  const body = await parseJson(response);

  if (!response.ok) {
    const error = new Error(
      body && typeof body.error === 'string'
        ? body.error
        : `Forge returned HTTP ${response.status}.`
    );
    error.status = response.status;
    error.body = body;
    throw error;
  }

  return body;
}

async function currentUser(baseUrl) {
  return request(baseUrl, '/api/auth/me');
}

async function login(baseUrl, username, password) {
  return request(baseUrl, '/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  });
}

async function csrfToken(baseUrl) {
  return request(baseUrl, '/api/auth/csrf-token');
}

async function csrfHeaders(baseUrl) {
  const token = await csrfToken(baseUrl);
  return {
    Origin: new URL(baseUrl).origin,
    'X-CSRF-Token': token.csrfToken,
  };
}

async function logout(baseUrl) {
  return request(baseUrl, '/api/auth/logout', {
    method: 'POST',
    headers: await csrfHeaders(baseUrl),
  });
}

async function getFeed(baseUrl) {
  return request(baseUrl, '/api/feed');
}

async function createPost(baseUrl, body) {
  return request(baseUrl, '/api/posts', {
    method: 'POST',
    body: JSON.stringify({ body }),
    headers: await csrfHeaders(baseUrl),
  });
}

async function togglePostLike(baseUrl, postId) {
  return request(baseUrl, `/api/posts/${postId}/like`, {
    method: 'POST',
    headers: await csrfHeaders(baseUrl),
  });
}

async function addPostComment(baseUrl, postId, text) {
  return request(baseUrl, `/api/posts/${postId}/comments`, {
    method: 'POST',
    body: JSON.stringify({ text }),
    headers: await csrfHeaders(baseUrl),
  });
}

async function getOpportunities(baseUrl) {
  return request(baseUrl, '/api/opportunities');
}

async function toggleOpportunityApplication(baseUrl, opportunityId) {
  return request(baseUrl, `/api/opportunities/${opportunityId}/apply`, {
    method: 'POST',
    headers: await csrfHeaders(baseUrl),
  });
}

async function getNotifications(baseUrl) {
  return request(baseUrl, '/api/notifications');
}

async function markNotificationRead(baseUrl, notificationId) {
  return request(baseUrl, `/api/notifications/${notificationId}/read`, {
    method: 'POST',
    headers: await csrfHeaders(baseUrl),
  });
}

async function markAllNotificationsRead(baseUrl) {
  return request(baseUrl, '/api/notifications/read-all', {
    method: 'POST',
    headers: await csrfHeaders(baseUrl),
  });
}

async function getOnboarding(baseUrl) {
  return request(baseUrl, '/api/onboarding');
}

async function advanceOnboarding(baseUrl) {
  return request(baseUrl, '/api/onboarding/advance', {
    method: 'POST',
    headers: await csrfHeaders(baseUrl),
  });
}

async function skipOnboarding(baseUrl) {
  return request(baseUrl, '/api/onboarding/skip', {
    method: 'POST',
    headers: await csrfHeaders(baseUrl),
  });
}

module.exports = {
  apiUrl,
  currentUser,
  login,
  logout,
  getFeed,
  createPost,
  togglePostLike,
  addPostComment,
  getOpportunities,
  toggleOpportunityApplication,
  getNotifications,
  markNotificationRead,
  markAllNotificationsRead,
  getOnboarding,
  advanceOnboarding,
  skipOnboarding,
};
