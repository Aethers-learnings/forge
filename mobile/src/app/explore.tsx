import { ScrollView, StyleSheet } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { BottomTabInset, MaxContentWidth, Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';

export default function AboutScreen() {
  const insets = useSafeAreaInsets();
  const theme = useTheme();

  return (
    <ScrollView
      style={{ backgroundColor: theme.background }}
      contentContainerStyle={[
        styles.content,
        {
          paddingTop: insets.top + Spacing.four,
          paddingBottom: insets.bottom + BottomTabInset + Spacing.four,
        },
      ]}>
      <ThemedView style={styles.section}>
        <ThemedText type="subtitle">About Forge</ThemedText>
        <ThemedText themeColor="textSecondary">
          Forge brings profiles, opportunities, community activity, and career tools together.
        </ThemedText>
      </ThemedView>

      <ThemedView style={styles.section}>
        <ThemedText type="smallBold">In the mobile app</ThemedText>
        <ThemedText themeColor="textSecondary">
          Use Home for your profile, feed, opportunities, and notifications. You can also open the
          web experience from Home for other available Forge features.
        </ThemedText>
      </ThemedView>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  content: {
    alignSelf: 'center',
    width: '100%',
    maxWidth: MaxContentWidth,
    paddingHorizontal: Spacing.four,
    gap: Spacing.four,
  },
  section: {
    gap: Spacing.two,
  },
});
