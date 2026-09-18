const { withAndroidManifest, AndroidConfig } = require('expo/config-plugins');

// Supported Expo config plugin: app.json android.usesCleartextTraffic is not a supported field.
module.exports = (config) => withAndroidManifest(config, (mod) => {
  const application = AndroidConfig.Manifest.getMainApplicationOrThrow(mod.modResults);
  application.$['android:usesCleartextTraffic'] = 'false';
  // Do not let a network security config override the cleartext ban.
  delete application.$['android:networkSecurityConfig'];
  return mod;
});
