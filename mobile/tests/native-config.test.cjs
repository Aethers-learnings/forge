const { test } = require('node:test');
const assert = require('node:assert/strict');
const { execFileSync } = require('node:child_process');
const path = require('node:path');

for (const profile of ['preview', 'production']) {
  test(`${profile} generated native configuration enforces transport policy`, () => {
    const output = execFileSync(process.execPath, [require.resolve('expo/bin/cli'), 'config', '--type', 'introspect', '--json'], {
      cwd: path.resolve(__dirname, '..'), encoding: 'utf8',
      env: { ...process.env, CI: '1', EAS_BUILD_PROFILE: profile,
        FORGE_MOBILE_ALLOWED_ORIGINS: 'https://forge.example:8443',
        FORGE_MOBILE_DEVELOPMENT: '1', FORGE_MOBILE_DEV_ORIGINS: 'https://localhost:8443' },
      maxBuffer: 5 * 1024 * 1024,
    });
    const config = JSON.parse(output);
    assert.deepEqual(config.extra.forgeSecurity.allowedOrigins, ['https://forge.example:8443']);
    assert.deepEqual(config.extra.forgeSecurity.developmentOrigins, []);
    const mods = config._internal.modResults;
    const application = mods.android.manifest.manifest.application[0].$;
    assert.equal(application['android:usesCleartextTraffic'], 'false');
    assert.equal(application['android:networkSecurityConfig'], undefined);
    assert.deepEqual(mods.ios.infoPlist.NSAppTransportSecurity, {
      NSAllowsArbitraryLoads: false, NSAllowsArbitraryLoadsInWebContent: false, NSAllowsLocalNetworking: false,
    });
  });
}
