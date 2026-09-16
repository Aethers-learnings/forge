import React, { useRef, useState, useEffect } from 'react';
import {
  StyleSheet, SafeAreaView, StatusBar, BackHandler, Platform,
  View, Text, TextInput, TouchableOpacity, KeyboardAvoidingView,
} from 'react-native';
import { WebView } from 'react-native-webview';
import AsyncStorage from '@react-native-async-storage/async-storage';

const STORAGE_KEY = 'forge_server_url';
const DEFAULT_URL = 'http://192.168.100.9:5000'; // fallback only — always editable below

export default function Index() {
  const webviewRef = useRef<WebView>(null);
  const [canGoBack, setCanGoBack] = useState(false);
  const [serverUrl, setServerUrl] = useState<string | null>(null);
  const [inputValue, setInputValue] = useState('');
  const [editing, setEditing] = useState(false);

  useEffect(() => {
    AsyncStorage.getItem(STORAGE_KEY).then((saved) => {
      const url = saved || DEFAULT_URL;
      setServerUrl(url);
      setInputValue(url);
    });
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
    let url = inputValue.trim();
    if (!/^https?:\/\//i.test(url)) url = 'http://' + url;
    await AsyncStorage.setItem(STORAGE_KEY, url);
    setServerUrl(url);
    setEditing(false);
  };

  if (!serverUrl) return null; // brief splash while reading storage

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
            placeholder="http://192.168.x.x:5000"
            autoCapitalize="none"
            autoCorrect={false}
            keyboardType="url"
          />
          <TouchableOpacity style={styles.button} onPress={saveUrl}>
            <Text style={styles.buttonText}>Connect</Text>
          </TouchableOpacity>
        </KeyboardAvoidingView>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container}>
      <StatusBar barStyle="dark-content" backgroundColor="#f4ede0" />
      <WebView
        ref={webviewRef}
        source={{ uri: serverUrl }}
        style={styles.webview}
        onNavigationStateChange={(navState) => setCanGoBack(navState.canGoBack)}
        mixedContentMode="always"
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
