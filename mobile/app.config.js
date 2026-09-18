const { parseOrigins } = require('./src/security/url-policy');

module.exports = ({ config }) => {
  const development = process.env.EAS_BUILD_PROFILE === 'development' &&
    process.env.FORGE_MOBILE_DEVELOPMENT === '1';
  return {
    ...config,
    ios: {
      ...config.ios,
      infoPlist: {
        ...config.ios?.infoPlist,
        NSAppTransportSecurity: {
          NSAllowsArbitraryLoads: false,
          NSAllowsArbitraryLoadsInWebContent: false,
          NSAllowsLocalNetworking: false,
        },
      },
    },
    plugins: [...(config.plugins || []), './plugins/with-secure-transport'],
    extra: {
      ...config.extra,
      forgeSecurity: {
        allowedOrigins: parseOrigins(process.env.FORGE_MOBILE_ALLOWED_ORIGINS),
        development,
        developmentOrigins: development ? parseOrigins(process.env.FORGE_MOBILE_DEV_ORIGINS) : [],
      },
    },
  };
};
