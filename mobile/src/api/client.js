const REQUEST_TIMEOUT_MS = 15000;

function apiUrl(baseUrl, path) {
  return new URL(path, baseUrl).href;
}

async function parseJson(response, signal) {
  try {
    return await response.json();
  } catch (error) {
    if (signal.aborted) throw error;
    return null;
  }
}

async function request(baseUrl, path, options = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  let response;
  let body;

  try {
    response = await fetch(apiUrl(baseUrl, path), {
      credentials: 'include',
      ...options,
      signal: controller.signal,
      headers: {
        Accept: 'application/json',
        ...(options.body ? { 'Content-Type': 'application/json' } : {}),
        ...(options.headers || {}),
      },
    });
    // Fetch may resolve at headers; the deadline also covers body consumption.
    body = await parseJson(response, controller.signal);
    if (controller.signal.aborted) throw new Error('Request timed out');
  } catch {
    if (controller.signal.aborted) {
      const error = new Error('Forge took too long to respond. Check your connection and try again.');
      error.network = true;
      error.timeout = true;
      throw error;
    }
    const error = new Error('Forge could not reach the server. Check your connection and try again.');
    error.network = true;
    throw error;
  } finally {
    clearTimeout(timeout);
  }

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

async function updateProfilePortfolio(baseUrl, fields) {
  return request(baseUrl, '/api/profile/portfolio', {
    method: 'PATCH',
    body: JSON.stringify(fields),
    headers: await csrfHeaders(baseUrl),
  });
}

async function updateProfileSkill(baseUrl, action, skill) {
  return request(baseUrl, '/api/profile/skills', {
    method: 'PATCH',
    body: JSON.stringify({ action, skill }),
    headers: await csrfHeaders(baseUrl),
  });
}

async function updateProfileVisibility(baseUrl, visibility) {
  return request(baseUrl, '/api/profile/visibility', {
    method: 'PATCH',
    body: JSON.stringify(visibility),
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
  updateProfilePortfolio,
  updateProfileSkill,
  updateProfileVisibility,
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
