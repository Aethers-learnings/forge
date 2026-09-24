import React, { useRef, useState, useEffect } from 'react';
import {
  StyleSheet, SafeAreaView, StatusBar, BackHandler, Platform,
  View, Text, TextInput, TouchableOpacity, KeyboardAvoidingView, ScrollView,
} from 'react-native';
import { WebView } from 'react-native-webview';
import AsyncStorage from '@react-native-async-storage/async-storage';
import Constants from 'expo-constants';
import { allowedUrl, runtimeOrigins } from '../security/url-policy';
import {
  currentUser,
  login,
  logout,
  getOnboarding,
  advanceOnboarding,
  skipOnboarding,
} from '../api/client';

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
  const [nativeMode, setNativeMode] = useState(true);
  const [nativeUser, setNativeUser] = useState<any>(null);
  const [authLoading, setAuthLoading] = useState(false);
  const [authChecked, setAuthChecked] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null);
  const [onboarding, setOnboarding] = useState<any>(null);
  const [onboardingBusy, setOnboardingBusy] = useState(false);
  const [onboardingError, setOnboardingError] = useState<string | null>(null);

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


  const submitNativeLogin = async (username: string, password: string) => {
    if (!serverUrl) return;

    setAuthLoading(true);
    setAuthError(null);

    try {
      const user = await login(serverUrl, username.trim(), password);
      setNativeUser(user);
      setAuthChecked(true);
    } catch (error: any) {
      setNativeUser(null);
      setAuthError(error?.message || 'Could not sign in.');
    } finally {
      setAuthLoading(false);
    }
  };

  const submitNativeLogout = async () => {
    if (!serverUrl) return;

    setAuthLoading(true);
    setAuthError(null);

    try {
      await logout(serverUrl);
      setNativeUser(null);
      setOnboarding(null);
      setOnboardingError(null);
      setAuthChecked(true);
    } catch (error: any) {
      setAuthError(error?.message || 'Could not sign out.');
    } finally {
      setAuthLoading(false);
    }
  };

  useEffect(() => {
    if (!nativeMode || !ready || editing || authChecked) return;

    const url = allowedUrl(serverUrl, ALLOWED_ORIGINS);
    if (!url) return;

    let cancelled = false;

    void currentUser(url)
      .then((user: any) => {
        if (!cancelled) setNativeUser(user);
      })
      .catch((error: any) => {
        if (!cancelled) {
          setAuthError(error?.message || 'Could not check your Forge session.');
        }
      })
      .finally(() => {
        if (!cancelled) setAuthChecked(true);
      });

    return () => {
      cancelled = true;
    };
  }, [nativeMode, ready, editing, authChecked, serverUrl]);

  const nativeUserId = nativeUser?.id;

  useEffect(() => {
    if (!nativeMode || !serverUrl || !nativeUserId) return;

    let cancelled = false;

    void getOnboarding(serverUrl)
      .then((value: any) => {
        if (!cancelled) {
          setOnboarding(value);
          setOnboardingError(null);
        }
      })
      .catch((error: any) => {
        if (!cancelled) {
          setOnboardingError(
            error?.message || 'Could not load onboarding progress.'
          );
        }
      });

    return () => {
      cancelled = true;
    };
  }, [nativeMode, serverUrl, nativeUserId]);

  const applyOnboardingState = (value: any) => {
    setOnboarding(value);
    setNativeUser((user: any) => user ? {
      ...user,
      onboarding: {
        complete: !!value.complete,
        step: value.step,
      },
    } : user);
  };

  const handleAdvanceOnboarding = async () => {
    if (!serverUrl || onboardingBusy) return;

    setOnboardingBusy(true);
    setOnboardingError(null);

    try {
      applyOnboardingState(await advanceOnboarding(serverUrl));
    } catch (error: any) {
      setOnboardingError(
        error?.message || 'Could not advance onboarding.'
      );
    } finally {
      setOnboardingBusy(false);
    }
  };

  const handleSkipOnboarding = async () => {
    if (!serverUrl || onboardingBusy) return;

    setOnboardingBusy(true);
    setOnboardingError(null);

    try {
      applyOnboardingState(await skipOnboarding(serverUrl));
    } catch (error: any) {
      setOnboardingError(
        error?.message || 'Could not skip onboarding.'
      );
    } finally {
      setOnboardingBusy(false);
    }
  };

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
      setAuthChecked(false);
      setNativeUser(null);
      setAuthError(null);
      setOnboarding(null);
      setOnboardingError(null);
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

  if (nativeMode && sourceUrl) {
    if (!authChecked) {
      return (
        <SafeAreaView style={styles.container}>
          <StatusBar barStyle="dark-content" backgroundColor="#f4ede0" />
          <View style={styles.nativeAuth}>
            <Text style={styles.brand}>Forge</Text>
            <Text accessibilityRole="text" style={styles.nativeSubtitle}>
              Checking your session…
            </Text>

            <TouchableOpacity
              accessibilityRole="button"
              style={styles.secondaryButton}
              onPress={() => setNativeMode(false)}
            >
              <Text style={styles.secondaryButtonText}>Use web experience</Text>
            </TouchableOpacity>

            <TouchableOpacity
              accessibilityRole="button"
              style={styles.linkButton}
              onPress={() => setEditing(true)}
            >
              <Text style={styles.linkText}>Server settings</Text>
            </TouchableOpacity>
          </View>
        </SafeAreaView>
      );
    }

    if (nativeUser) {
      const roleLabel =
        nativeUser.role === 'business'
          ? 'Business account'
          : nativeUser.role === 'admin'
            ? 'Administrator'
            : nativeUser.role === 'grad'
              ? 'Graduate'
              : 'Student';

      const roleDetail =
        nativeUser.role === 'business'
          ? nativeUser.company?.industry || nativeUser.headline || 'Business profile'
          : nativeUser.role === 'admin'
            ? 'Platform administration'
            : nativeUser.programme || nativeUser.headline || 'Build your professional profile';

      const onboardingSteps = onboarding?.steps || [];
      const onboardingStep = onboarding?.step ?? nativeUser.onboarding?.step ?? 0;
      const onboardingComplete =
        onboarding?.complete ?? nativeUser.onboarding?.complete ?? false;
      const currentStep = onboardingSteps[onboardingStep] || null;

      return (
        <SafeAreaView style={styles.container}>
          <StatusBar barStyle="dark-content" backgroundColor="#f4ede0" />

          <ScrollView
            contentContainerStyle={styles.nativeHome}
            showsVerticalScrollIndicator={false}
          >
            <View style={styles.homeHeader}>
              <View>
                <Text style={styles.brandCompact}>Forge</Text>
                <Text style={styles.homeTitle}>
                  {nativeUser.name || nativeUser.username}
                </Text>
                <Text style={styles.nativeMeta}>{roleLabel}</Text>
              </View>

              <View
                accessible
                accessibilityLabel={`Profile ${nativeUser.completion || 0}% complete`}
                style={styles.completionBadge}
              >
                <Text style={styles.completionValue}>
                  {nativeUser.completion || 0}%
                </Text>
                <Text style={styles.completionLabel}>complete</Text>
              </View>
            </View>

            <View style={styles.profileCard}>
              <Text style={styles.cardEyebrow}>PROFILE</Text>
              <Text style={styles.profileHeadline}>{roleDetail}</Text>

              {!!nativeUser.bio && (
                <Text style={styles.profileBio}>{nativeUser.bio}</Text>
              )}

              {nativeUser.role !== 'business' && (
                <View style={styles.profileFacts}>
                  {!!nativeUser.campus && (
                    <Text style={styles.profileFact}>Campus · {nativeUser.campus}</Text>
                  )}
                  {!!nativeUser.year && (
                    <Text style={styles.profileFact}>Year · {nativeUser.year}</Text>
                  )}
                </View>
              )}

              {nativeUser.role === 'business' && (
                <View style={styles.profileFacts}>
                  {!!nativeUser.company?.location && (
                    <Text style={styles.profileFact}>
                      Location · {nativeUser.company.location}
                    </Text>
                  )}
                  {!!nativeUser.company?.talentSought && (
                    <Text style={styles.profileFact}>
                      Hiring · {nativeUser.company.talentSought}
                    </Text>
                  )}
                </View>
              )}

              {Array.isArray(nativeUser.skills) && nativeUser.skills.length > 0 && (
                <View style={styles.skillsBlock}>
                  <Text style={styles.skillsTitle}>Skills</Text>
                  <View style={styles.skillsRow}>
                    {nativeUser.skills.slice(0, 6).map((skill: string) => (
                      <View key={skill} style={styles.skillChip}>
                        <Text style={styles.skillText}>{skill}</Text>
                      </View>
                    ))}
                  </View>
                </View>
              )}
            </View>

            {!onboardingComplete && (
              <View style={styles.onboardingCard}>
                <Text style={styles.cardEyebrow}>GET STARTED</Text>
                <Text style={styles.onboardingTitle}>
                  Finish setting up Forge
                </Text>

                {onboardingSteps.length > 0 && (
                  <>
                    <Text style={styles.onboardingProgress}>
                      Step {Math.min(onboardingStep + 1, onboardingSteps.length)} of {onboardingSteps.length}
                    </Text>

                    {!!currentStep && (
                      <Text style={styles.onboardingStep}>
                        {currentStep
                          .split('-')
                          .map((part: string) =>
                            part.charAt(0).toUpperCase() + part.slice(1)
                          )
                          .join(' ')}
                      </Text>
                    )}
                  </>
                )}

                {onboardingError && (
                  <Text accessibilityRole="alert" style={styles.nativeError}>
                    {onboardingError}
                  </Text>
                )}

                <TouchableOpacity
                  accessibilityRole="button"
                  disabled={onboardingBusy}
                  style={[
                    styles.button,
                    onboardingBusy && styles.buttonDisabled,
                  ]}
                  onPress={handleAdvanceOnboarding}
                >
                  <Text style={styles.buttonText}>
                    {onboardingBusy ? 'Updating…' : 'Continue setup'}
                  </Text>
                </TouchableOpacity>

                <TouchableOpacity
                  accessibilityRole="button"
                  disabled={onboardingBusy}
                  style={styles.linkButton}
                  onPress={handleSkipOnboarding}
                >
                  <Text style={styles.linkText}>Skip onboarding</Text>
                </TouchableOpacity>
              </View>
            )}

            {onboardingComplete && (
              <View style={styles.completeCard}>
                <Text style={styles.cardEyebrow}>ONBOARDING</Text>
                <Text style={styles.completeTitle}>You’re ready to use Forge.</Text>
              </View>
            )}

            {authError && (
              <Text accessibilityRole="alert" style={styles.nativeError}>
                {authError}
              </Text>
            )}

            <TouchableOpacity
              accessibilityRole="button"
              style={styles.secondaryButton}
              onPress={() => setNativeMode(false)}
            >
              <Text style={styles.secondaryButtonText}>
                Open full web experience
              </Text>
            </TouchableOpacity>

            <TouchableOpacity
              accessibilityRole="button"
              disabled={authLoading}
              style={styles.linkButton}
              onPress={submitNativeLogout}
            >
              <Text style={styles.linkText}>
                {authLoading ? 'Signing out…' : 'Sign out'}
              </Text>
            </TouchableOpacity>

            <TouchableOpacity
              accessibilityRole="button"
              style={styles.linkButton}
              onPress={() => setEditing(true)}
            >
              <Text style={styles.linkText}>Server settings</Text>
            </TouchableOpacity>
          </ScrollView>
        </SafeAreaView>
      );
    }

    return (
      <SafeAreaView style={styles.container}>
        <StatusBar barStyle="dark-content" backgroundColor="#f4ede0" />
        <NativeLogin
          loading={authLoading}
          error={authError}
          onSubmit={submitNativeLogin}
          onWeb={() => setNativeMode(false)}
          onSettings={() => setEditing(true)}
        />
      </SafeAreaView>
    );
  }

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

function NativeLogin({
  loading,
  error,
  onSubmit,
  onWeb,
  onSettings,
}: {
  loading: boolean;
  error: string | null;
  onSubmit: (username: string, password: string) => Promise<void>;
  onWeb: () => void;
  onSettings: () => void;
}) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');

  return (
    <KeyboardAvoidingView
      style={styles.nativeAuth}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <Text style={styles.brand}>Forge</Text>
      <Text style={styles.nativeTitle}>Sign in</Text>
      <Text style={styles.nativeSubtitle}>
        Your professional community, now starting natively.
      </Text>

      <Text style={styles.fieldLabel}>Username</Text>
      <TextInput
        accessibilityLabel="Username"
        style={styles.input}
        value={username}
        onChangeText={setUsername}
        autoCapitalize="none"
        autoCorrect={false}
        editable={!loading}
        returnKeyType="next"
      />

      <Text style={styles.fieldLabel}>Password</Text>
      <TextInput
        accessibilityLabel="Password"
        style={styles.input}
        value={password}
        onChangeText={setPassword}
        secureTextEntry
        editable={!loading}
        returnKeyType="go"
        onSubmitEditing={() => {
          if (username.trim() && password) void onSubmit(username, password);
        }}
      />

      {error && (
        <Text accessibilityRole="alert" style={styles.nativeError}>
          {error}
        </Text>
      )}

      <TouchableOpacity
        accessibilityRole="button"
        disabled={loading || !username.trim() || !password}
        style={[
          styles.button,
          (loading || !username.trim() || !password) && styles.buttonDisabled,
        ]}
        onPress={() => onSubmit(username, password)}
      >
        <Text style={styles.buttonText}>
          {loading ? 'Signing in…' : 'Sign in'}
        </Text>
      </TouchableOpacity>

      <TouchableOpacity
        accessibilityRole="button"
        style={styles.secondaryButton}
        onPress={onWeb}
      >
        <Text style={styles.secondaryButtonText}>Use web experience</Text>
      </TouchableOpacity>

      <TouchableOpacity
        accessibilityRole="button"
        style={styles.linkButton}
        onPress={onSettings}
      >
        <Text style={styles.linkText}>Server settings</Text>
      </TouchableOpacity>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f4ede0' },
  nativeHome: {
    paddingHorizontal: 22,
    paddingTop: 26,
    paddingBottom: 42,
    backgroundColor: '#f4ede0',
  },
  homeHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: 22,
  },
  brandCompact: {
    color: '#b5432b',
    fontWeight: '800',
    fontSize: 15,
    letterSpacing: 0.5,
    marginBottom: 8,
  },
  homeTitle: {
    color: '#1a1a1a',
    fontSize: 28,
    lineHeight: 34,
    fontWeight: '800',
    maxWidth: 235,
  },
  completionBadge: {
    minWidth: 72,
    minHeight: 72,
    borderRadius: 36,
    backgroundColor: '#fff8ee',
    borderWidth: 1,
    borderColor: '#d9cbbb',
    alignItems: 'center',
    justifyContent: 'center',
  },
  completionValue: {
    color: '#b5432b',
    fontSize: 18,
    fontWeight: '800',
  },
  completionLabel: {
    color: '#625a50',
    fontSize: 10,
    marginTop: 1,
  },
  profileCard: {
    backgroundColor: '#fff8ee',
    borderWidth: 1,
    borderColor: '#dfd2c2',
    borderRadius: 18,
    padding: 20,
    marginBottom: 16,
  },
  cardEyebrow: {
    color: '#8a7767',
    fontWeight: '800',
    fontSize: 11,
    letterSpacing: 1.2,
    marginBottom: 8,
  },
  profileHeadline: {
    color: '#1a1a1a',
    fontSize: 20,
    lineHeight: 26,
    fontWeight: '700',
  },
  profileBio: {
    color: '#625a50',
    fontSize: 14,
    lineHeight: 21,
    marginTop: 12,
  },
  profileFacts: {
    marginTop: 14,
    gap: 5,
  },
  profileFact: {
    color: '#625a50',
    fontSize: 13,
  },
  skillsBlock: {
    marginTop: 18,
  },
  skillsTitle: {
    color: '#39332d',
    fontSize: 12,
    fontWeight: '700',
    marginBottom: 9,
  },
  skillsRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 7,
  },
  skillChip: {
    backgroundColor: '#efe4d6',
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  skillText: {
    color: '#51483f',
    fontSize: 12,
    fontWeight: '600',
  },
  onboardingCard: {
    backgroundColor: '#fff8ee',
    borderWidth: 1,
    borderColor: '#dfd2c2',
    borderRadius: 18,
    padding: 20,
    marginBottom: 16,
  },
  onboardingTitle: {
    color: '#1a1a1a',
    fontSize: 19,
    fontWeight: '800',
    marginBottom: 5,
  },
  onboardingProgress: {
    color: '#8a7767',
    fontSize: 12,
    marginBottom: 10,
  },
  onboardingStep: {
    color: '#39332d',
    fontSize: 15,
    fontWeight: '700',
    marginBottom: 16,
  },
  completeCard: {
    backgroundColor: '#fff8ee',
    borderWidth: 1,
    borderColor: '#dfd2c2',
    borderRadius: 18,
    padding: 20,
    marginBottom: 16,
  },
  completeTitle: {
    color: '#2c6e62',
    fontSize: 17,
    fontWeight: '800',
  },
  nativeAuth: {
    flex: 1,
    justifyContent: 'center',
    paddingHorizontal: 28,
    backgroundColor: '#f4ede0',
  },
  brand: {
    fontSize: 18,
    fontWeight: '800',
    color: '#b5432b',
    marginBottom: 24,
    letterSpacing: 0.5,
  },
  nativeTitle: {
    fontSize: 32,
    fontWeight: '800',
    color: '#1a1a1a',
    marginBottom: 8,
  },
  nativeSubtitle: {
    fontSize: 15,
    lineHeight: 22,
    color: '#625a50',
    marginBottom: 28,
  },
  nativeName: {
    fontSize: 22,
    fontWeight: '700',
    color: '#1a1a1a',
    marginBottom: 4,
  },
  nativeMeta: {
    fontSize: 14,
    color: '#625a50',
    marginBottom: 28,
  },
  fieldLabel: {
    fontSize: 13,
    fontWeight: '700',
    color: '#39332d',
    marginBottom: 7,
  },
  nativeError: {
    color: '#9f2f1b',
    fontSize: 13,
    lineHeight: 18,
    marginBottom: 14,
  },
  buttonDisabled: {
    opacity: 0.5,
  },
  secondaryButton: {
    minHeight: 46,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 10,
    borderWidth: 1,
    borderColor: '#b5432b',
    borderRadius: 8,
  },
  secondaryButtonText: {
    color: '#b5432b',
    fontSize: 14,
    fontWeight: '700',
  },
  linkButton: {
    minHeight: 44,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 8,
  },
  linkText: {
    color: '#625a50',
    fontSize: 13,
    fontWeight: '600',
  },
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
