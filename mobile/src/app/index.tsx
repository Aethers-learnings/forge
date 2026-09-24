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
  getFeed,
  createPost,
  togglePostLike,
  addPostComment,
  getOnboarding,
  advanceOnboarding,
  skipOnboarding,
  getOpportunities,
  toggleOpportunityApplication,
  getNotifications,
  markNotificationRead,
  markAllNotificationsRead,
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
  const [nativeSection, setNativeSection] =
    useState<'feed' | 'profile' | 'opportunities' | 'notifications'>('profile');
  const [feedPosts, setFeedPosts] = useState<any[]>([]);
  const [feedLoading, setFeedLoading] = useState(false);
  const [feedError, setFeedError] = useState<string | null>(null);
  const [feedBusyKey, setFeedBusyKey] = useState<string | null>(null);
  const [newPostBody, setNewPostBody] = useState('');
  const [commentDrafts, setCommentDrafts] =
    useState<Record<number, string>>({});
  const [opportunities, setOpportunities] = useState<any[]>([]);
  const [opportunitiesLoading, setOpportunitiesLoading] = useState(false);
  const [opportunitiesError, setOpportunitiesError] = useState<string | null>(null);
  const [opportunityBusyId, setOpportunityBusyId] = useState<number | null>(null);
  const [notifications, setNotifications] = useState<any[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [notificationsLoading, setNotificationsLoading] = useState(false);
  const [notificationsError, setNotificationsError] = useState<string | null>(null);
  const [notificationBusyId, setNotificationBusyId] =
    useState<number | 'all' | null>(null);

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
      setNativeSection('profile');
      setFeedPosts([]);
      setFeedError(null);
      setFeedBusyKey(null);
      setNewPostBody('');
      setCommentDrafts({});
      setOpportunities([]);
      setOpportunitiesError(null);
      setNotifications([]);
      setUnreadCount(0);
      setNotificationsError(null);
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

  useEffect(() => {
    if (
      !nativeMode ||
      !serverUrl ||
      !nativeUserId ||
      nativeSection !== 'feed'
    ) return;

    let cancelled = false;

    void getFeed(serverUrl)
      .then((items: any[]) => {
        if (!cancelled) {
          setFeedPosts(Array.isArray(items) ? items : []);
          setFeedError(null);
        }
      })
      .catch((error: any) => {
        if (!cancelled) {
          setFeedError(error?.message || 'Could not load your feed.');
        }
      })
      .finally(() => {
        if (!cancelled) setFeedLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [nativeMode, serverUrl, nativeUserId, nativeSection]);

  const handleCreatePost = async () => {
    if (!serverUrl || feedBusyKey !== null || !newPostBody.trim()) return;

    setFeedBusyKey('create');
    setFeedError(null);

    try {
      const created = await createPost(serverUrl, newPostBody.trim());
      setFeedPosts((items: any[]) => [
        created,
        ...items.filter((item: any) => item.id !== created.id),
      ]);
      setNewPostBody('');
    } catch (error: any) {
      setFeedError(error?.message || 'Could not publish your post.');
    } finally {
      setFeedBusyKey(null);
    }
  };

  const handleTogglePostLike = async (postId: number) => {
    if (!serverUrl || feedBusyKey !== null) return;

    const busyKey = `like:${postId}`;
    setFeedBusyKey(busyKey);
    setFeedError(null);

    try {
      const updated = await togglePostLike(serverUrl, postId);
      setFeedPosts((items: any[]) =>
        items.map((item: any) => item.id === postId ? updated : item)
      );
    } catch (error: any) {
      setFeedError(error?.message || 'Could not update the like.');
    } finally {
      setFeedBusyKey(null);
    }
  };

  const handleAddPostComment = async (postId: number) => {
    if (!serverUrl || feedBusyKey !== null) return;

    const text = (commentDrafts[postId] || '').trim();
    if (!text) return;

    const busyKey = `comment:${postId}`;
    setFeedBusyKey(busyKey);
    setFeedError(null);

    try {
      const updated = await addPostComment(serverUrl, postId, text);
      setFeedPosts((items: any[]) =>
        items.map((item: any) => item.id === postId ? updated : item)
      );
      setCommentDrafts((drafts) => ({
        ...drafts,
        [postId]: '',
      }));
    } catch (error: any) {
      setFeedError(error?.message || 'Could not add your comment.');
    } finally {
      setFeedBusyKey(null);
    }
  };

  const canUseOpportunities =
    nativeUser?.role === 'trade' || nativeUser?.role === 'grad';

  useEffect(() => {
    if (
      !nativeMode ||
      !serverUrl ||
      !nativeUserId ||
      !canUseOpportunities ||
      nativeSection !== 'opportunities'
    ) return;

    let cancelled = false;

    void getOpportunities(serverUrl)
      .then((items: any[]) => {
        if (!cancelled) setOpportunities(Array.isArray(items) ? items : []);
      })
      .catch((error: any) => {
        if (!cancelled) {
          setOpportunitiesError(
            error?.message || 'Could not load opportunities.'
          );
        }
      })
      .finally(() => {
        if (!cancelled) setOpportunitiesLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [
    nativeMode,
    serverUrl,
    nativeUserId,
    canUseOpportunities,
    nativeSection,
  ]);

  const handleToggleApplication = async (opportunityId: number) => {
    if (!serverUrl || opportunityBusyId !== null) return;

    setOpportunityBusyId(opportunityId);
    setOpportunitiesError(null);

    try {
      const updated = await toggleOpportunityApplication(
        serverUrl,
        opportunityId
      );

      setOpportunities((items: any[]) =>
        items.map((item: any) =>
          item.id === opportunityId ? updated : item
        )
      );
    } catch (error: any) {
      setOpportunitiesError(
        error?.message || 'Could not update your application.'
      );
    } finally {
      setOpportunityBusyId(null);
    }
  };

  useEffect(() => {
    if (
      !nativeMode ||
      !serverUrl ||
      !nativeUserId ||
      nativeSection !== 'notifications'
    ) return;

    let cancelled = false;

    void getNotifications(serverUrl)
      .then((value: any) => {
        if (!cancelled) {
          setNotifications(
            Array.isArray(value?.notifications) ? value.notifications : []
          );
          setUnreadCount(
            typeof value?.unreadCount === 'number' ? value.unreadCount : 0
          );
          setNotificationsError(null);
        }
      })
      .catch((error: any) => {
        if (!cancelled) {
          setNotificationsError(
            error?.message || 'Could not load notifications.'
          );
        }
      })
      .finally(() => {
        if (!cancelled) setNotificationsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [nativeMode, serverUrl, nativeUserId, nativeSection]);

  const handleMarkNotificationRead = async (notificationId: number) => {
    if (!serverUrl || notificationBusyId !== null) return;

    const target = notifications.find(
      (notification: any) => notification.id === notificationId
    );

    if (!target || target.read) return;

    setNotificationBusyId(notificationId);
    setNotificationsError(null);

    try {
      await markNotificationRead(serverUrl, notificationId);

      setNotifications((items: any[]) =>
        items.map((notification: any) =>
          notification.id === notificationId
            ? { ...notification, read: true }
            : notification
        )
      );
      setUnreadCount((count: number) => Math.max(0, count - 1));
    } catch (error: any) {
      setNotificationsError(
        error?.message || 'Could not mark the notification as read.'
      );
    } finally {
      setNotificationBusyId(null);
    }
  };

  const handleMarkAllNotificationsRead = async () => {
    if (!serverUrl || notificationBusyId !== null || unreadCount === 0) return;

    setNotificationBusyId('all');
    setNotificationsError(null);

    try {
      await markAllNotificationsRead(serverUrl);

      setNotifications((items: any[]) =>
        items.map((notification: any) => ({
          ...notification,
          read: true,
        }))
      );
      setUnreadCount(0);
    } catch (error: any) {
      setNotificationsError(
        error?.message || 'Could not mark notifications as read.'
      );
    } finally {
      setNotificationBusyId(null);
    }
  };

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
      setNativeSection('profile');
      setFeedPosts([]);
      setFeedError(null);
      setFeedBusyKey(null);
      setNewPostBody('');
      setCommentDrafts({});
      setOpportunities([]);
      setOpportunitiesError(null);
      setNotifications([]);
      setUnreadCount(0);
      setNotificationsError(null);
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

            <View style={styles.sectionTabs}>
              <TouchableOpacity
                accessibilityRole="button"
                accessibilityState={{ selected: nativeSection === 'feed' }}
                style={[
                  styles.sectionTab,
                  nativeSection === 'feed' && styles.sectionTabActive,
                ]}
                onPress={() => {
                  setFeedLoading(true);
                  setFeedError(null);
                  setNativeSection('feed');
                }}
              >
                <Text
                  style={[
                    styles.sectionTabText,
                    nativeSection === 'feed' && styles.sectionTabTextActive,
                  ]}
                >
                  Feed
                </Text>
              </TouchableOpacity>

              <TouchableOpacity
                accessibilityRole="button"
                accessibilityState={{ selected: nativeSection === 'profile' }}
                style={[
                  styles.sectionTab,
                  nativeSection === 'profile' && styles.sectionTabActive,
                ]}
                onPress={() => setNativeSection('profile')}
              >
                <Text
                  style={[
                    styles.sectionTabText,
                    nativeSection === 'profile' && styles.sectionTabTextActive,
                  ]}
                >
                  Profile
                </Text>
              </TouchableOpacity>

              {canUseOpportunities && (
                <TouchableOpacity
                  accessibilityRole="button"
                  accessibilityState={{ selected: nativeSection === 'opportunities' }}
                  style={[
                    styles.sectionTab,
                    nativeSection === 'opportunities' && styles.sectionTabActive,
                  ]}
                  onPress={() => {
                    setOpportunitiesLoading(true);
                    setOpportunitiesError(null);
                    setNativeSection('opportunities');
                  }}
                >
                  <Text
                    style={[
                      styles.sectionTabText,
                      nativeSection === 'opportunities' && styles.sectionTabTextActive,
                    ]}
                  >
                    Opportunities
                  </Text>
                </TouchableOpacity>
              )}

              <TouchableOpacity
                accessibilityRole="button"
                accessibilityState={{ selected: nativeSection === 'notifications' }}
                accessibilityLabel={
                  unreadCount > 0
                    ? `Notifications, ${unreadCount} unread`
                    : 'Notifications'
                }
                style={[
                  styles.sectionTab,
                  nativeSection === 'notifications' && styles.sectionTabActive,
                ]}
                onPress={() => {
                  setNotificationsLoading(true);
                  setNotificationsError(null);
                  setNativeSection('notifications');
                }}
              >
                <View style={styles.notificationTabContent}>
                  <Text
                    style={[
                      styles.sectionTabText,
                      nativeSection === 'notifications' && styles.sectionTabTextActive,
                    ]}
                  >
                    Notifications
                  </Text>

                  {unreadCount > 0 && (
                    <View style={styles.unreadBadge}>
                      <Text style={styles.unreadBadgeText}>
                        {unreadCount > 99 ? '99+' : unreadCount}
                      </Text>
                    </View>
                  )}
                </View>
              </TouchableOpacity>
            </View>

            {nativeSection === 'feed' && (
              <View>
                <View style={styles.opportunityHeader}>
                  <Text style={styles.cardEyebrow}>COMMUNITY</Text>
                  <Text style={styles.opportunityTitle}>Your Forge feed</Text>
                  <Text style={styles.opportunityIntro}>
                    Share progress, ideas and updates with your Forge community.
                  </Text>
                </View>

                <View style={styles.feedComposer}>
                  <Text style={styles.feedComposerTitle}>Create a post</Text>
                  <TextInput
                    accessibilityLabel="New post"
                    style={styles.feedInput}
                    value={newPostBody}
                    onChangeText={setNewPostBody}
                    placeholder="What are you working on?"
                    multiline
                    textAlignVertical="top"
                    editable={feedBusyKey === null}
                  />

                  <TouchableOpacity
                    accessibilityRole="button"
                    disabled={feedBusyKey !== null || !newPostBody.trim()}
                    style={[
                      styles.button,
                      (feedBusyKey !== null || !newPostBody.trim()) &&
                        styles.buttonDisabled,
                    ]}
                    onPress={handleCreatePost}
                  >
                    <Text style={styles.buttonText}>
                      {feedBusyKey === 'create' ? 'Publishing…' : 'Publish post'}
                    </Text>
                  </TouchableOpacity>
                </View>

                {feedLoading && feedPosts.length === 0 && (
                  <View style={styles.profileCard}>
                    <Text style={styles.profileBio}>Loading your feed…</Text>
                  </View>
                )}

                {feedError && (
                  <Text accessibilityRole="alert" style={styles.nativeError}>
                    {feedError}
                  </Text>
                )}

                {!feedLoading &&
                  !feedError &&
                  feedPosts.length === 0 && (
                    <View style={styles.profileCard}>
                      <Text style={styles.profileHeadline}>
                        Nothing here yet
                      </Text>
                      <Text style={styles.profileBio}>
                        Be the first to share something with your Forge community.
                      </Text>
                    </View>
                  )}

                {feedPosts.map((post: any) => {
                  const comments = Array.isArray(post.comments)
                    ? post.comments
                    : [];
                  const recentComments = comments.slice(-3);
                  const commentBusyKey = `comment:${post.id}`;
                  const likeBusyKey = `like:${post.id}`;

                  return (
                    <View key={post.id} style={styles.feedPostCard}>
                      <View style={styles.feedPostTopRow}>
                        <View style={styles.feedAuthorBlock}>
                          <Text style={styles.feedAuthor}>
                            {post.name || 'Forge member'}
                          </Text>
                          <Text style={styles.feedRole}>
                            {(post.role || 'member').toUpperCase()}
                          </Text>
                        </View>

                        {post.pick && (
                          <View style={styles.feedFeaturedBadge}>
                            <Text style={styles.feedFeaturedText}>FEATURED</Text>
                          </View>
                        )}
                      </View>

                      <Text style={styles.feedBody}>{post.body}</Text>

                      {post.media && (
                        <Text style={styles.feedMediaNote}>
                          Video post · open the full web experience to watch
                        </Text>
                      )}

                      <View style={styles.feedActions}>
                        <TouchableOpacity
                          accessibilityRole="button"
                          disabled={feedBusyKey !== null}
                          style={[
                            styles.feedActionButton,
                            post.likedByMe && styles.feedActionButtonActive,
                          ]}
                          onPress={() => handleTogglePostLike(post.id)}
                        >
                          <Text
                            style={[
                              styles.feedActionText,
                              post.likedByMe && styles.feedActionTextActive,
                            ]}
                          >
                            {feedBusyKey === likeBusyKey
                              ? 'Updating…'
                              : `${post.likedByMe ? 'Liked' : 'Like'} · ${post.likeCount || 0}`}
                          </Text>
                        </TouchableOpacity>
                      </View>

                      {recentComments.length > 0 && (
                        <View style={styles.feedComments}>
                          {comments.length > recentComments.length && (
                            <Text style={styles.feedCommentCount}>
                              Latest {recentComments.length} of {comments.length} comments
                            </Text>
                          )}

                          {recentComments.map((comment: any, index: number) => (
                            <View
                              key={`${post.id}-${index}-${comment.who}`}
                              style={styles.feedComment}
                            >
                              <Text style={styles.feedCommentWho}>
                                {comment.who}
                              </Text>
                              <Text style={styles.feedCommentText}>
                                {comment.text}
                              </Text>
                            </View>
                          ))}
                        </View>
                      )}

                      <View style={styles.feedCommentComposer}>
                        <TextInput
                          accessibilityLabel={`Comment on post by ${post.name || 'Forge member'}`}
                          style={styles.feedCommentInput}
                          value={commentDrafts[post.id] || ''}
                          onChangeText={(value) =>
                            setCommentDrafts((drafts) => ({
                              ...drafts,
                              [post.id]: value,
                            }))
                          }
                          placeholder="Add a comment"
                          editable={feedBusyKey === null}
                        />

                        <TouchableOpacity
                          accessibilityRole="button"
                          disabled={
                            feedBusyKey !== null ||
                            !(commentDrafts[post.id] || '').trim()
                          }
                          style={[
                            styles.feedCommentButton,
                            (feedBusyKey !== null ||
                              !(commentDrafts[post.id] || '').trim()) &&
                              styles.buttonDisabled,
                          ]}
                          onPress={() => handleAddPostComment(post.id)}
                        >
                          <Text style={styles.feedCommentButtonText}>
                            {feedBusyKey === commentBusyKey ? 'Sending…' : 'Send'}
                          </Text>
                        </TouchableOpacity>
                      </View>
                    </View>
                  );
                })}
              </View>
            )}

            {nativeSection === 'profile' && (
              <>
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

              </>
            )}

            {nativeSection === 'opportunities' && canUseOpportunities && (
              <View>
                <View style={styles.opportunityHeader}>
                  <Text style={styles.cardEyebrow}>OPPORTUNITIES</Text>
                  <Text style={styles.opportunityTitle}>
                    Find your next move
                  </Text>
                  <Text style={styles.opportunityIntro}>
                    Roles approved for Forge students and graduates.
                  </Text>
                </View>

                {opportunitiesLoading && opportunities.length === 0 && (
                  <View style={styles.profileCard}>
                    <Text style={styles.profileBio}>
                      Loading opportunities…
                    </Text>
                  </View>
                )}

                {opportunitiesError && (
                  <Text accessibilityRole="alert" style={styles.nativeError}>
                    {opportunitiesError}
                  </Text>
                )}

                {!opportunitiesLoading &&
                  !opportunitiesError &&
                  opportunities.length === 0 && (
                    <View style={styles.profileCard}>
                      <Text style={styles.profileHeadline}>
                        No opportunities yet
                      </Text>
                      <Text style={styles.profileBio}>
                        Check back as new approved roles are published.
                      </Text>
                    </View>
                  )}

                {opportunities.map((opportunity: any) => (
                  <View
                    key={opportunity.id}
                    style={styles.opportunityCard}
                  >
                    <View style={styles.opportunityTopRow}>
                      <View style={styles.opportunityTitleBlock}>
                        <Text style={styles.opportunityRole}>
                          {opportunity.title}
                        </Text>
                        <Text style={styles.opportunityCompany}>
                          {opportunity.co}
                        </Text>
                      </View>

                      <View
                        accessible
                        accessibilityLabel={`${opportunity.match}% match`}
                        style={styles.matchBadge}
                      >
                        <Text style={styles.matchValue}>
                          {opportunity.match}%
                        </Text>
                        <Text style={styles.matchLabel}>match</Text>
                      </View>
                    </View>

                    {Array.isArray(opportunity.tags) &&
                      opportunity.tags.length > 0 && (
                        <View style={styles.skillsRow}>
                          {opportunity.tags.slice(0, 5).map((tag: string) => (
                            <View key={tag} style={styles.skillChip}>
                              <Text style={styles.skillText}>{tag}</Text>
                            </View>
                          ))}
                        </View>
                      )}

                    {opportunity.matchIsFallback && (
                      <Text style={styles.matchNote}>
                        Match based on available profile information
                      </Text>
                    )}

                    <TouchableOpacity
                      accessibilityRole="button"
                      disabled={opportunityBusyId !== null}
                      style={[
                        opportunity.applied
                          ? styles.appliedButton
                          : styles.button,
                        opportunityBusyId !== null && styles.buttonDisabled,
                      ]}
                      onPress={() =>
                        handleToggleApplication(opportunity.id)
                      }
                    >
                      <Text
                        style={
                          opportunity.applied
                            ? styles.appliedButtonText
                            : styles.buttonText
                        }
                      >
                        {opportunityBusyId === opportunity.id
                          ? 'Updating…'
                          : opportunity.applied
                            ? 'Withdraw application'
                            : 'Apply'}
                      </Text>
                    </TouchableOpacity>
                  </View>
                ))}
              </View>
            )}

            {nativeSection === 'notifications' && (
              <View>
                <View style={styles.notificationHeader}>
                  <View style={styles.notificationHeadingBlock}>
                    <Text style={styles.cardEyebrow}>NOTIFICATIONS</Text>
                    <Text style={styles.opportunityTitle}>
                      What’s happening
                    </Text>
                    <Text style={styles.opportunityIntro}>
                      Updates from your Forge activity.
                    </Text>
                  </View>

                  {unreadCount > 0 && (
                    <TouchableOpacity
                      accessibilityRole="button"
                      disabled={notificationBusyId !== null}
                      style={styles.markAllButton}
                      onPress={handleMarkAllNotificationsRead}
                    >
                      <Text style={styles.markAllButtonText}>
                        {notificationBusyId === 'all'
                          ? 'Updating…'
                          : 'Mark all read'}
                      </Text>
                    </TouchableOpacity>
                  )}
                </View>

                {notificationsLoading && notifications.length === 0 && (
                  <View style={styles.profileCard}>
                    <Text style={styles.profileBio}>
                      Loading notifications…
                    </Text>
                  </View>
                )}

                {notificationsError && (
                  <Text accessibilityRole="alert" style={styles.nativeError}>
                    {notificationsError}
                  </Text>
                )}

                {!notificationsLoading &&
                  !notificationsError &&
                  notifications.length === 0 && (
                    <View style={styles.profileCard}>
                      <Text style={styles.profileHeadline}>
                        You’re all caught up
                      </Text>
                      <Text style={styles.profileBio}>
                        New Forge activity will appear here.
                      </Text>
                    </View>
                  )}

                {notifications.map((notification: any) => (
                  <View
                    key={notification.id}
                    style={[
                      styles.notificationCard,
                      !notification.read && styles.notificationCardUnread,
                    ]}
                  >
                    <View style={styles.notificationTopRow}>
                      <View style={styles.notificationTextBlock}>
                        <View style={styles.notificationTypeRow}>
                          {!notification.read && (
                            <View
                              accessible={false}
                              style={styles.unreadDot}
                            />
                          )}

                          <Text style={styles.notificationType}>
                            {(notification.type || 'update')
                              .replace(/[_-]/g, ' ')
                              .toUpperCase()}
                          </Text>
                        </View>

                        <Text style={styles.notificationText}>
                          {notification.text}
                        </Text>

                        {!!notification.createdAt && (
                          <Text style={styles.notificationDate}>
                            {new Date(notification.createdAt).toLocaleDateString()}
                          </Text>
                        )}
                      </View>
                    </View>

                    {!notification.read && (
                      <TouchableOpacity
                        accessibilityRole="button"
                        disabled={notificationBusyId !== null}
                        style={styles.notificationReadButton}
                        onPress={() =>
                          handleMarkNotificationRead(notification.id)
                        }
                      >
                        <Text style={styles.notificationReadButtonText}>
                          {notificationBusyId === notification.id
                            ? 'Updating…'
                            : 'Mark as read'}
                        </Text>
                      </TouchableOpacity>
                    )}
                  </View>
                ))}
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
  sectionTabs: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    backgroundColor: '#eadfce',
    borderRadius: 12,
    padding: 4,
    gap: 4,
    marginBottom: 16,
  },
  sectionTab: {
    flexGrow: 1,
    flexBasis: '48%',
    minHeight: 42,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 9,
  },
  sectionTabActive: {
    backgroundColor: '#fff8ee',
  },
  sectionTabText: {
    color: '#716558',
    fontSize: 13,
    fontWeight: '700',
  },
  sectionTabTextActive: {
    color: '#b5432b',
  },
  notificationTabContent: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 5,
  },
  unreadBadge: {
    minWidth: 20,
    height: 20,
    paddingHorizontal: 5,
    borderRadius: 10,
    backgroundColor: '#b5432b',
    alignItems: 'center',
    justifyContent: 'center',
  },
  unreadBadgeText: {
    color: '#fff8ee',
    fontSize: 10,
    fontWeight: '800',
  },
  feedComposer: {
    backgroundColor: '#fff8ee',
    borderWidth: 1,
    borderColor: '#dfd2c2',
    borderRadius: 18,
    padding: 16,
    marginBottom: 14,
  },
  feedComposerTitle: {
    color: '#1a1a1a',
    fontSize: 16,
    fontWeight: '800',
    marginBottom: 10,
  },
  feedInput: {
    minHeight: 92,
    borderWidth: 1,
    borderColor: '#d8c9b8',
    borderRadius: 12,
    backgroundColor: '#fffdf8',
    paddingHorizontal: 12,
    paddingVertical: 10,
    color: '#1a1a1a',
    fontSize: 14,
    lineHeight: 20,
    marginBottom: 12,
  },
  feedPostCard: {
    backgroundColor: '#fff8ee',
    borderWidth: 1,
    borderColor: '#dfd2c2',
    borderRadius: 18,
    padding: 18,
    marginBottom: 14,
  },
  feedPostTopRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: 12,
  },
  feedAuthorBlock: {
    flex: 1,
    paddingRight: 12,
  },
  feedAuthor: {
    color: '#1a1a1a',
    fontSize: 15,
    fontWeight: '800',
  },
  feedRole: {
    color: '#8a7767',
    fontSize: 10,
    fontWeight: '800',
    letterSpacing: 0.7,
    marginTop: 3,
  },
  feedFeaturedBadge: {
    backgroundColor: '#efe4d6',
    borderRadius: 8,
    paddingHorizontal: 8,
    paddingVertical: 5,
  },
  feedFeaturedText: {
    color: '#b5432b',
    fontSize: 9,
    fontWeight: '800',
    letterSpacing: 0.6,
  },
  feedBody: {
    color: '#27221d',
    fontSize: 15,
    lineHeight: 22,
  },
  feedMediaNote: {
    color: '#716558',
    fontSize: 11,
    lineHeight: 16,
    marginTop: 10,
  },
  feedActions: {
    flexDirection: 'row',
    marginTop: 14,
  },
  feedActionButton: {
    minHeight: 36,
    justifyContent: 'center',
    paddingHorizontal: 12,
    borderRadius: 9,
    backgroundColor: '#efe4d6',
  },
  feedActionButtonActive: {
    borderWidth: 1,
    borderColor: '#b5432b',
  },
  feedActionText: {
    color: '#625a50',
    fontSize: 12,
    fontWeight: '700',
  },
  feedActionTextActive: {
    color: '#b5432b',
  },
  feedComments: {
    borderTopWidth: 1,
    borderTopColor: '#eadfce',
    marginTop: 14,
    paddingTop: 12,
    gap: 9,
  },
  feedCommentCount: {
    color: '#8a7767',
    fontSize: 10,
  },
  feedComment: {
    backgroundColor: '#f4ede0',
    borderRadius: 10,
    paddingHorizontal: 11,
    paddingVertical: 9,
  },
  feedCommentWho: {
    color: '#1a1a1a',
    fontSize: 11,
    fontWeight: '800',
    marginBottom: 2,
  },
  feedCommentText: {
    color: '#514a42',
    fontSize: 12,
    lineHeight: 17,
  },
  feedCommentComposer: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginTop: 12,
  },
  feedCommentInput: {
    flex: 1,
    minHeight: 40,
    borderWidth: 1,
    borderColor: '#d8c9b8',
    borderRadius: 10,
    backgroundColor: '#fffdf8',
    paddingHorizontal: 11,
    color: '#1a1a1a',
    fontSize: 12,
  },
  feedCommentButton: {
    minHeight: 40,
    justifyContent: 'center',
    paddingHorizontal: 12,
    borderRadius: 10,
    backgroundColor: '#b5432b',
  },
  feedCommentButtonText: {
    color: '#fff8ee',
    fontSize: 11,
    fontWeight: '800',
  },
  notificationHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    gap: 12,
    marginBottom: 14,
  },
  notificationHeadingBlock: {
    flex: 1,
  },
  markAllButton: {
    minHeight: 36,
    justifyContent: 'center',
    paddingHorizontal: 10,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#b5432b',
  },
  markAllButtonText: {
    color: '#b5432b',
    fontSize: 11,
    fontWeight: '700',
  },
  notificationCard: {
    backgroundColor: '#fff8ee',
    borderWidth: 1,
    borderColor: '#dfd2c2',
    borderRadius: 16,
    padding: 16,
    marginBottom: 12,
  },
  notificationCardUnread: {
    borderColor: '#c46a54',
  },
  notificationTopRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
  },
  notificationTextBlock: {
    flex: 1,
  },
  notificationTypeRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 7,
    marginBottom: 7,
  },
  unreadDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: '#b5432b',
  },
  notificationType: {
    color: '#8a7767',
    fontSize: 10,
    fontWeight: '800',
    letterSpacing: 0.8,
  },
  notificationText: {
    color: '#1a1a1a',
    fontSize: 14,
    lineHeight: 20,
    fontWeight: '600',
  },
  notificationDate: {
    color: '#8a7767',
    fontSize: 11,
    marginTop: 8,
  },
  notificationReadButton: {
    alignSelf: 'flex-start',
    minHeight: 34,
    justifyContent: 'center',
    marginTop: 12,
    paddingHorizontal: 10,
    borderRadius: 8,
    backgroundColor: '#efe4d6',
  },
  notificationReadButtonText: {
    color: '#625a50',
    fontSize: 11,
    fontWeight: '700',
  },
  opportunityHeader: {
    marginBottom: 14,
  },
  opportunityTitle: {
    color: '#1a1a1a',
    fontSize: 23,
    fontWeight: '800',
    marginBottom: 5,
  },
  opportunityIntro: {
    color: '#625a50',
    fontSize: 14,
    lineHeight: 20,
  },
  opportunityCard: {
    backgroundColor: '#fff8ee',
    borderWidth: 1,
    borderColor: '#dfd2c2',
    borderRadius: 18,
    padding: 18,
    marginBottom: 14,
  },
  opportunityTopRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: 15,
  },
  opportunityTitleBlock: {
    flex: 1,
    paddingRight: 12,
  },
  opportunityRole: {
    color: '#1a1a1a',
    fontSize: 18,
    lineHeight: 23,
    fontWeight: '800',
  },
  opportunityCompany: {
    color: '#625a50',
    fontSize: 13,
    marginTop: 4,
  },
  matchBadge: {
    minWidth: 62,
    minHeight: 58,
    borderRadius: 12,
    backgroundColor: '#efe4d6',
    alignItems: 'center',
    justifyContent: 'center',
  },
  matchValue: {
    color: '#2c6e62',
    fontSize: 16,
    fontWeight: '800',
  },
  matchLabel: {
    color: '#716558',
    fontSize: 10,
    marginTop: 1,
  },
  matchNote: {
    color: '#8a7767',
    fontSize: 11,
    lineHeight: 16,
    marginTop: 10,
    marginBottom: 12,
  },
  appliedButton: {
    minHeight: 46,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#2c6e62',
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 15,
  },
  appliedButtonText: {
    color: '#2c6e62',
    fontWeight: '700',
    fontSize: 14,
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
