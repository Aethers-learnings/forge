import React, { useRef, useState, useEffect } from 'react';
import {
  StyleSheet, SafeAreaView, StatusBar, BackHandler, Platform,
  View, Text, TextInput, TouchableOpacity, KeyboardAvoidingView,
} from 'react-native';
import { WebView } from 'react-native-webview';
import AsyncStorage from '@react-native-async-storage/async-storage';
import Constants from 'expo-constants';
import { allowedUrl, runtimeOrigins } from '../security/url-policy';

const STORAGE_KEY = 'forge_server_url';
const ALLOWED_ORIGINS = runtimeOrigins(Constants.expoConfig?.extra?.forgeSecurity, __DEV__);
const POLICY_ERROR = 'Enter an approved HTTPS server address. If none is configured, rebuild the app with approved origins.';

export default function Index() {
  const webviewRef = useRef<WebView>(null);
  const [canGoBack, setCanGoBack] = useState(false);
  const [serverUrl, setServerUrl] = useState<string | null>(null);
  const [inputValue, setInputValue] = useState('');
  const [ready, setReady] = useState(false);
  const [settingsError, setSettingsError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [lastError, setLastError] = useState<string | null>(null);

  useEffect(() => {
    AsyncStorage.getItem(STORAGE_KEY).then((saved) => {
      setInputValue(saved ?? '');
      const url = allowedUrl(saved, ALLOWED_ORIGINS);
      setServerUrl(url);
      setEditing(!url);
      if (!url) setSettingsError(POLICY_ERROR);
    }).catch(() => {
      setEditing(true);
      setSettingsError('Could not read the saved address. Enter an approved HTTPS address to retry.');
    }).finally(() => setReady(true));
  }, []);

  useEffect(() => {
    if (Platform.OS !== 'android') return;
    const onBackPress = () => {
      if (canGoBack && webviewRef.current) {
        webviewRef.current.goBack();
        return true;
      }
      return false;
    };
    const sub = BackHandler.addEventListener('hardwareBackPress', onBackPress);
    return () => sub.remove();
  }, [canGoBack]);

  const saveUrl = async () => {
    const url = allowedUrl(inputValue.trim(), ALLOWED_ORIGINS);
    if (!url) { setSettingsError(POLICY_ERROR); return; }
    try {
      await AsyncStorage.setItem(STORAGE_KEY, url);
      setServerUrl(url);
      setCanGoBack(false);
      setLastError(null);
      setSettingsError(null);
      setEditing(false);
    } catch {
      setSettingsError('Could not save the address. Please try again.');
    }
  };

  if (!ready) return null;

  if (editing) {
    return (
      <SafeAreaView style={styles.container}>
        <StatusBar barStyle="dark-content" backgroundColor="#f4ede0" />
        <KeyboardAvoidingView style={styles.settingsBox} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
          <Text style={styles.label}>Forge server address</Text>
          <TextInput
            style={styles.input}
            value={inputValue}
            onChangeText={setInputValue}
            placeholder="https://your-approved-server"
            autoCapitalize="none"
            autoCorrect={false}
            keyboardType="url"
          />
          {settingsError && <Text style={styles.errorText}>{settingsError}</Text>}
          <TouchableOpacity style={styles.button} onPress={saveUrl}>
            <Text style={styles.buttonText}>Connect</Text>
          </TouchableOpacity>
        </KeyboardAvoidingView>
      </SafeAreaView>
    );
  }

  const sourceUrl = allowedUrl(serverUrl, ALLOWED_ORIGINS);

  if (lastError || !sourceUrl) {
    return (
      <SafeAreaView style={styles.container}>
        <StatusBar barStyle="dark-content" backgroundColor="#f4ede0" />
        <View style={styles.settingsBox}>
          <Text style={styles.label}>Couldn&apos;t load Forge</Text>
          <Text style={styles.errorText}>{lastError || POLICY_ERROR}</Text>
          <TouchableOpacity style={styles.button} onPress={() => { setLastError(null); setEditing(true); }}>
            <Text style={styles.buttonText}>Edit server address</Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container}>
      <StatusBar barStyle="dark-content" backgroundColor="#f4ede0" />
      <WebView
        ref={webviewRef}
        source={{ uri: sourceUrl }}
        onShouldStartLoadWithRequest={(request) =>
          request.isTopFrame !== false && !!allowedUrl(request.url, ALLOWED_ORIGINS)
        }
        onOpenWindow={() => { /* Discard all target=_blank and window.open attempts. */ }}
        javaScriptCanOpenWindowsAutomatically={false}
        setSupportMultipleWindows={true}
        style={styles.webview}
        onNavigationStateChange={(navState) => setCanGoBack(navState.canGoBack)}
        onError={(syntheticEvent) => {
          const { nativeEvent } = syntheticEvent;
          setLastError(
            `code: ${nativeEvent.code}\ndescription: ${nativeEvent.description}\nurl: ${nativeEvent.url}`
          );
        }}
        onHttpError={(syntheticEvent) => {
          const { nativeEvent } = syntheticEvent;
          setLastError(
            `HTTP status: ${nativeEvent.statusCode}\nurl: ${nativeEvent.url}`
          );
        }}
        mixedContentMode="never"
        // Route every scheme through our exact-origin guard; narrower patterns can
        // cause react-native-webview to open rejected URLs via OS Linking.
        originWhitelist={['*']}
        javaScriptEnabled
        domStorageEnabled
        allowsBackForwardNavigationGestures
        startInLoadingState
      />
      {/* Long-press-free small settings tab, always reachable, doesn't cover content */}
      <TouchableOpacity style={styles.gear} onPress={() => setEditing(true)}>
        <Text style={styles.gearText}>⚙</Text>
      </TouchableOpacity>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f4ede0' },
  webview: { flex: 1 },
  settingsBox: { flex: 1, justifyContent: 'center', paddingHorizontal: 24 },
  label: { fontSize: 16, fontWeight: '600', color: '#1a1a1a', marginBottom: 8 },
  errorText: { fontSize: 13, color: '#5a5248', marginBottom: 20, fontFamily: Platform.OS === 'android' ? 'monospace' : 'Menlo' },
  input: {
    borderWidth: 1, borderColor: '#b5432b', borderRadius: 8,
    paddingHorizontal: 14, paddingVertical: 12, fontSize: 15,
    backgroundColor: '#fff', marginBottom: 14,
  },
  button: {
    backgroundColor: '#b5432b', borderRadius: 8,
    paddingVertical: 13, alignItems: 'center',
  },
  buttonText: { color: '#fff8ee', fontWeight: '700', fontSize: 15 },
  gear: {
    position: 'absolute', bottom: 18, right: 18,
    width: 40, height: 40, borderRadius: 20,
    backgroundColor: 'rgba(26,26,26,0.55)',
    alignItems: 'center', justifyContent: 'center',
  },
  gearText: { color: '#fff8ee', fontSize: 18 },
});
