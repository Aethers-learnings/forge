/** Parse strictly before URL canonicalization can repair ambiguous input. */
function parseUrl(value) {
  if (typeof value !== 'string' || !value || value !== value.trim() ||
      /[\\\s\u0000-\u001f\u007f]/u.test(value) || /%(?![0-9a-f]{2})/i.test(value) ||
      !/^https:\/\/[^/?#]+/i.test(value)) return null;
  try {
    const url = new URL(value);
    const authority = value.match(/^https:\/\/([^/?#]+)/i)[1];
    if (url.protocol !== 'https:' || url.username || url.password ||
        authority.includes('*') || authority.endsWith(':') || authority.includes('@') || authority.includes('%') || url.hostname.endsWith('.')) return null;
    return url;
  } catch { return null; }
}

/** Every entry explicitly authorizes its exact host and effective port, including IPs. */
function parseOrigins(value) {
  if (value === undefined || value === '') return [];
  if (typeof value !== 'string') throw new Error('Allowed origins must be a comma-separated string');
  return [...new Set(value.split(',').map((entry) => {
    const raw = entry.trim();
    const url = parseUrl(raw);
    if (!url || url.pathname !== '/' || url.search || url.hash ||
        !/^https:\/\/[^/?#]+\/?$/i.test(raw)) {
      throw new Error('Each allowed origin must be an exact HTTPS origin without credentials, path, query or fragment');
    }
    return url.origin;
  }))];
}

function allowedUrl(value, origins) {
  const url = parseUrl(value);
  if (!url || !Array.isArray(origins)) return null;
  // Validate runtime config too: missing/malformed entries never grant access.
  const allowed = origins.some((origin) => {
    const parsed = parseUrl(origin);
    return parsed && parsed.origin === origin && origin === url.origin;
  });
  return allowed ? url.href : null;
}

function runtimeOrigins(config, isDevelopment) {
  if (!config || typeof config !== 'object') return [];
  const production = Array.isArray(config.allowedOrigins) ? config.allowedOrigins : [];
  const development = isDevelopment && config.development === true &&
    Array.isArray(config.developmentOrigins) ? config.developmentOrigins : [];
  return [...production, ...development];
}

module.exports = { parseOrigins, allowedUrl, runtimeOrigins };
