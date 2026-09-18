const { test } = require('node:test');
const assert = require('node:assert/strict');
const { parseOrigins, allowedUrl, runtimeOrigins } = require('../src/security/url-policy');
const buildConfig = require('../app.config');
const origins = parseOrigins('https://forge.example,https://forge.example:8443');

for (const url of [
  'http://forge.example', 'https://forge.example.evil.test', 'https://evilforge.example',
  'https://forge.example:444', 'https://user:pass@forge.example', 'https://@forge.example',
  'javascript:alert(1)', 'data:text/html,hi', 'file:///etc/passwd', 'intent://forge.example',
  '//forge.example', 'https:forge.example', 'https:///forge.example', 'https://forge.example:',
  'https://forge.example./', 'https://%66orge.example', 'https://forge.example/%zz',
  'https://forge.example\\@evil.test', 'https://forge.example\n', '', null,
  'https://127.0.0.1', 'https://2130706433', 'https://[::1]',
]) test(`reject ${JSON.stringify(url)}`, () => assert.equal(allowedUrl(url, origins), null));

test('exact origins, paths, default and explicitly configured ports', () => {
  assert.equal(allowedUrl('https://FORGE.example:443/a?q=1#x', origins), 'https://forge.example/a?q=1#x');
  assert.ok(allowedUrl('https://forge.example:8443/', origins));
  assert.equal(allowedUrl('https://forge.example', []), null);
  assert.equal(allowedUrl('https://forge.example', ['https://forge.example/path']), null);
});
test('IP literals require explicit exact configuration', () => {
  const ips = parseOrigins('https://127.0.0.1:8443,https://[::1]');
  assert.ok(allowedUrl('https://127.0.0.1:8443/', ips));
  assert.ok(allowedUrl('https://[::1]/', ips));
  assert.equal(allowedUrl('https://127.0.0.1/', ips), null);
});
test('invalid build origins fail configuration', () => {
  for (const value of ['http://forge.example', 'https://*.example', 'https://forge.example/a',
    'https://forge.example?x', 'https://forge.example#x', ',', 'https://u@forge.example']) {
    assert.throws(() => parseOrigins(value), value);
  }
});

test('build configuration defaults closed and isolates development from preview/production', () => {
  const keys = ['EAS_BUILD_PROFILE', 'FORGE_MOBILE_DEVELOPMENT', 'FORGE_MOBILE_ALLOWED_ORIGINS', 'FORGE_MOBILE_DEV_ORIGINS'];
  const previous = Object.fromEntries(keys.map(key => [key, process.env[key]]));
  try {
    keys.forEach(key => delete process.env[key]);
    const base = { extra: { preserved: true }, ios: { infoPlist: {
      NSAppTransportSecurity: { NSAllowsArbitraryLoads: true, NSExceptionDomains: { unsafe: {} } },
    } } };
    let result = buildConfig({ config: base });
    assert.deepEqual(result.extra.forgeSecurity.allowedOrigins, []);
    assert.equal(result.extra.preserved, true);
    assert.deepEqual(result.ios.infoPlist.NSAppTransportSecurity, {
      NSAllowsArbitraryLoads: false, NSAllowsArbitraryLoadsInWebContent: false, NSAllowsLocalNetworking: false,
    });
    process.env.FORGE_MOBILE_DEVELOPMENT = '1';
    process.env.FORGE_MOBILE_DEV_ORIGINS = 'https://localhost:8443';
    for (const profile of ['preview', 'production', 'unknown']) {
      process.env.EAS_BUILD_PROFILE = profile;
      result = buildConfig({ config: base }).extra.forgeSecurity;
      assert.deepEqual(runtimeOrigins(result, true), []);
    }
    process.env.EAS_BUILD_PROFILE = 'development';
    result = buildConfig({ config: base }).extra.forgeSecurity;
    assert.deepEqual(runtimeOrigins(result, true), ['https://localhost:8443']);
    assert.deepEqual(runtimeOrigins(result, false), []);
    process.env.FORGE_MOBILE_ALLOWED_ORIGINS = 'http://unsafe.example';
    assert.throws(() => buildConfig({ config: base }));
  } finally {
    for (const [key, value] of Object.entries(previous)) {
      if (value === undefined) delete process.env[key]; else process.env[key] = value;
    }
  }
});
