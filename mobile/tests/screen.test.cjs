const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');
const policy = require('../src/security/url-policy');

function screen(saved, options = {}) {
  let cursor = 0;
  const states = [], effects = [], writes = [];
  const react = {
    useRef: () => ({ current: null }),
    useState: (initial) => {
      const index = cursor++;
      if (!(index in states)) states[index] = initial;
      return [states[index], value => { states[index] = value; }];
    },
    useEffect: fn => { if (!mounted) effects.push(fn); },
    createElement: (type, props, ...children) => ({ type, props: props || {}, children }),
  };
  let mounted = false;
  const native = new Proxy({
    StyleSheet: { create: x => x }, Platform: { OS: 'ios' },
  }, { get: (target, name) => target[name] || name });
  const storage = {
    getItem: async () => { if (options.readFails) throw Error(); return saved; },
    setItem: async (key, value) => { if (options.writeFails) throw Error(); writes.push([key, value]); },
  };
  const modules = {
    react, 'react-native': native, 'react-native-webview': { WebView: 'WebView' },
    '@react-native-async-storage/async-storage': storage,
    'expo-constants': { expoConfig: { extra: { forgeSecurity: { allowedOrigins: ['https://forge.example'] } } } },
    '../security/url-policy': policy,
    '../api/client': {
      currentUser: async () => null,
      login: async () => null,
      logout: async () => ({ ok: true }),
      getOnboarding: async () => ({
        steps: ['welcome'],
        step: 0,
        complete: false,
      }),
      advanceOnboarding: async () => ({
        steps: ['welcome'],
        step: 0,
        complete: true,
      }),
      skipOnboarding: async () => ({
        steps: ['welcome'],
        step: 0,
        complete: true,
      }),
      getOpportunities: async () => [],
      toggleOpportunityApplication: async (_url, id) => ({
        id,
        title: 'Junior developer',
        co: 'Forge',
        match: 80,
        matchIsFallback: true,
        tags: ['Python'],
        applied: true,
      }),
    },
  };
  const source = ts.transpileModule(fs.readFileSync(require.resolve('../src/app/index.tsx'), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.React, esModuleInterop: true },
  }).outputText;
  const context = { exports: {}, require: name => {
    if (!(name in modules)) throw Error(name);
    return modules[name];
  }, __DEV__: false };
  vm.runInNewContext(source, context);
  const render = () => { cursor = 0; const tree = context.exports.default(); mounted = true; return tree; };
  render(); effects.forEach(fn => fn());
  return { render, writes };
}
function find(tree, type) {
  if (!tree || typeof tree !== 'object') return null;
  if (tree.type === type) return tree;
  for (const child of tree.children || []) {
    const result = find(child, type);
    if (result) return result;
  }
  return null;
}

function textContent(tree) {
  if (typeof tree === 'string') return tree;
  if (!tree || typeof tree !== 'object') return '';
  return (tree.children || []).map(textContent).join('');
}

function findComponent(tree, name) {
  if (!tree || typeof tree !== 'object') return null;

  if (
    typeof tree.type === 'function' &&
    tree.type.name === name
  ) {
    return tree;
  }

  for (const child of tree.children || []) {
    const result = findComponent(child, name);
    if (result) return result;
  }

  return null;
}

function findButtonByText(tree, label) {
  if (!tree || typeof tree !== 'object') return null;

  if (
    tree.type === 'TouchableOpacity' &&
    textContent(tree).includes(label)
  ) {
    return tree;
  }

  for (const child of tree.children || []) {
    const result = findButtonByText(child, label);
    if (result) return result;
  }

  return null;
}
const settle = () => new Promise(resolve => setImmediate(resolve));

test('invalid persisted URL is retained for correction without load or write', async () => {
  const app = screen('http://old.example'); await settle();
  const tree = app.render();
  assert.equal(find(tree, 'WebView'), null);
  assert.equal(find(tree, 'TextInput').props.value, 'http://old.example');
  assert.deepEqual(app.writes, []);
  find(tree, 'TextInput').props.onChangeText('https://evil.example');
  await find(app.render(), 'TouchableOpacity').props.onPress();
  assert.equal(find(app.render(), 'WebView'), null);
  assert.deepEqual(app.writes, []);
  find(app.render(), 'TextInput').props.onChangeText('https://forge.example/path');
  await find(app.render(), 'TouchableOpacity').props.onPress();

  // Native authentication is now the default T-205 entry point.
  // The hardened WebView remains an explicit fallback.
  findButtonByText(app.render(), 'Use web experience').props.onPress();

  assert.equal(find(app.render(), 'WebView').props.source.uri, 'https://forge.example/path');
  assert.deepEqual(app.writes, [['forge_server_url', 'https://forge.example/path']]);
});
test('initial source and navigation use the policy, popup callbacks never load a target', async () => {
  const app = screen('https://forge.example'); await settle();

  assert.equal(find(app.render(), 'WebView'), null);
  findButtonByText(app.render(), 'Use web experience').props.onPress();

  const web = find(app.render(), 'WebView');
  assert.equal(web.props.source.uri, 'https://forge.example/');
  for (const url of ['https://evil.example', 'http://forge.example', 'javascript:alert(1)', 'https://forge.example:8443']) {
    assert.equal(web.props.onShouldStartLoadWithRequest({ url }), false);
  }
  assert.equal(web.props.onShouldStartLoadWithRequest({ url: 'https://forge.example/next' }), true);
  assert.equal(web.props.onShouldStartLoadWithRequest({ url: 'https://forge.example', isTopFrame: false }), false);
  assert.equal(web.props.mixedContentMode, 'never');
  assert.equal(web.props.javaScriptCanOpenWindowsAutomatically, false);
  assert.equal(web.props.setSupportMultipleWindows, true);
  web.props.onOpenWindow({ nativeEvent: { targetUrl: 'https://evil.example' } });
  assert.equal(find(app.render(), 'WebView').props.source.uri, 'https://forge.example/');
  assert.deepEqual(app.writes, []);
});
test('missing storage, storage read and save failures remain recoverable', async () => {
  for (const options of [{}, { readFails: true }, { writeFails: true }]) {
    const app = screen(null, options); await settle();
    assert.ok(find(app.render(), 'TextInput'));
    if (options.writeFails) {
      find(app.render(), 'TextInput').props.onChangeText('https://forge.example');
      await find(app.render(), 'TouchableOpacity').props.onPress();
      assert.equal(find(app.render(), 'WebView'), null);
      assert.deepEqual(app.writes, []);
    }
  }
});
