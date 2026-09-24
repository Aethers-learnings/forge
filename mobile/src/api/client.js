
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

async function logout(baseUrl) {
  const token = await csrfToken(baseUrl);
  const origin = new URL(baseUrl).origin;

  return request(baseUrl, '/api/auth/logout', {
    method: 'POST',
    headers: {
      Origin: origin,
      'X-CSRF-Token': token.csrfToken,
    },
  });
}

module.exports = {
  apiUrl,
  currentUser,
  login,
  logout,
};
