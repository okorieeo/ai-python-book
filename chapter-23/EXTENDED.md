# Chapter 23 — React Native and Expo Fundamentals: extended material

The printed edition of *Building AI-Powered Apps* keeps each chapter short. This file holds the longer material that was moved here so that nothing is lost: the full hands-on lab, troubleshooting tables, checklists, further exercises, and sections that were condensed for print.


---

# Sections condensed for print


## Setting Up the Project › app.json: the app's identity

**app.json (the parts we changed or rely on)**

```
{
  "expo": {
    "name": "Chat App",            // shown under the icon on the home screen
    "slug": "chat-app",            // the app's id in Expo's services
    "scheme": "chatapp",           // makes links like chatapp://chat/welcome open the app
    "version": "1.0.0",
    "orientation": "portrait",
    "userInterfaceStyle": "automatic",   // follow the phone's light or dark setting
    "plugins": ["expo-router", ["expo-splash-screen", { "backgroundColor": "#208AEF" }]],
    "experiments": { "typedRoutes": true, "reactCompiler": true }
  }
}
```

| **Setting** | **What it does** |
|---|---|
| `scheme` | Registers your own URL scheme, so other apps and web pages can open yours (deep links, Section 23.8) |
| `userInterfaceStyle: "automatic"` | Lets the app switch between light and dark with the phone; without it, `useColorScheme` always reports light |
| `typedRoutes` | Generates TypeScript types for every route, so `router.push("/chta")` is a compile error |
| `reactCompiler` | Turns on React’s compiler, which automatically avoids unnecessary re-renders. You will write far fewer `useMemo` and `useCallback` calls than older tutorials show |
| `plugins` | Native configuration steps for libraries that need them, applied when you build the native app |

The generated starter includes demo screens and animated logos. We deleted them and kept only the theme helpers (`themed-text`, `themed-view`), so that every file in the project is one you will understand. The template’s `reset-project` script does the same.

Always add libraries with `npx expo install`. For example `npx expo install expo-secure-store` picks the version built for your SDK. Two diagnostic commands are worth knowing: `npx expo-doctor` checks your project for common problems, and `npx expo install --check` reports packages whose versions do not match your SDK.


## Styling Without CSS › Colour tokens and dark mode

The colours follow Chapter 19’s design-token idea: named by purpose, with a light and a dark set. The `useColorScheme()` hook reports what the phone is set to, and `useTheme()` picks the matching set.

**src/constants/colors.ts**

```
/**
 * Colour tokens, named by purpose (the same idea as Chapter 19's web tokens).
 * Components ask for "primary" or "textSecondary", never for a hex value.
 */
export const Colors = {
  light: {
    text: '#0f172a',
    textSecondary: '#475569',
    background: '#ffffff',
    backgroundElement: '#f1f5f9',
    backgroundSelected: '#e2e8f0',
    primary: '#1d4ed8',
    onPrimary: '#ffffff',
    danger: '#b91c1c',
    border: '#e2e8f0',
    inputBorder: '#64748b',
  },
  dark: {
    text: '#e2e8f0',
    textSecondary: '#a3b1c6',
    background: '#0b1120',
    backgroundElement: '#1e293b',
    backgroundSelected: '#273449',
    primary: '#60a5fa',
    onPrimary: '#0b1120',
    danger: '#f87171',
    border: '#1e293b',
    inputBorder: '#64748b',
  },
} as const;

export type ThemeColor = keyof typeof Colors.light & keyof typeof Colors.dark;
```

**src/hooks/use-theme.ts**

```
/**
 * Learn more about light and dark modes:
 * https://docs.expo.dev/guides/color-schemes/
 */

import { Colors } from '@/constants/theme';
import { useColorScheme } from '@/hooks/use-color-scheme';

export function useTheme() {
  const scheme = useColorScheme();
  const theme = scheme === 'dark' ? 'dark' : 'light';

  return Colors[theme];
}
```

**src/components/themed-text.tsx**

```
import { Platform, StyleSheet, Text, type TextProps } from 'react-native';

import { Fonts, ThemeColor } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';

export type ThemedTextProps = TextProps & {
  type?: 'default' | 'title' | 'small' | 'smallBold' | 'subtitle' | 'link' | 'linkPrimary' | 'code';
  themeColor?: ThemeColor;
};

export function ThemedText({ style, type = 'default', themeColor, ...rest }: ThemedTextProps) {
  const theme = useTheme();

  return <Text style={[{ color: theme[themeColor ?? 'text'] }, styles[type], style]} {...rest} />;
}

const styles = StyleSheet.create({
  small: {
    fontSize: 14,
    lineHeight: 20,
    fontWeight: 500,
  },
  smallBold: {
    fontSize: 14,
    lineHeight: 20,
    fontWeight: 700,
  },
  default: {
    fontSize: 16,
    lineHeight: 24,
    fontWeight: 500,
  },
  title: {
    fontSize: 48,
    fontWeight: 600,
    lineHeight: 52,
  },
  subtitle: {
    fontSize: 32,
    lineHeight: 44,
    fontWeight: 600,
  },
  link: {
    lineHeight: 30,
    fontSize: 14,
  },
  linkPrimary: {
    lineHeight: 30,
    fontSize: 14,
    color: '#3c87f7',
  },
  code: {
    fontFamily: Fonts.mono,
    fontWeight: Platform.select({ android: 700 }) ?? 500,
    fontSize: 12,
  },
});
```

`ThemedText` and `ThemedView` are the mobile equivalents of the web’s `bg-background text-foreground`: a text or a view that already knows the current theme. Screens use them instead of raw `Text` and `View` wherever a colour is involved, so switching the phone to dark mode recolours the whole app with no per-screen work. We reuse the web’s contrast test: a Jest test computes the contrast of every text and background pair in both themes, so a colour change can never make text unreadable.

**src/__tests__/colors.test.ts**

```
import { Colors } from '@/constants/colors';

import { contrastRatio } from '../../test/contrast';

// [text colour, background colour, minimum contrast]
const pairs: [keyof typeof Colors.light, keyof typeof Colors.light, number][] = [
  ['text', 'background', 4.5],
  ['text', 'backgroundElement', 4.5],
  ['text', 'backgroundSelected', 4.5],
  ['textSecondary', 'background', 4.5],
  ['textSecondary', 'backgroundElement', 4.5],
  ['onPrimary', 'primary', 4.5], // text on a primary button or bubble
  ['danger', 'background', 4.5], // error messages
  ['primary', 'background', 4.5], // links
  ['inputBorder', 'background', 3], // the outline of a text box
];

describe.each(['light', 'dark'] as const)('%s colour tokens', (scheme) => {
  it.each(pairs)('%s on %s has contrast of at least %s:1', (fg, bg, min) => {
    expect(contrastRatio(Colors[scheme][fg], Colors[scheme][bg])).toBeGreaterThanOrEqual(min);
  });
});
```


## Navigation with Expo Router › Layouts: the stack and the tabs

**src/app/_layout.tsx**

```
import { DarkTheme, DefaultTheme, Stack, ThemeProvider } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { useColorScheme } from 'react-native';

export default function RootLayout() {
  const scheme = useColorScheme();
  return (
    <ThemeProvider value={scheme === 'dark' ? DarkTheme : DefaultTheme}>
      <Stack>
        {/* The tab bar screens draw their own titles, so hide the stack header. */}
        <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
        <Stack.Screen name="chat/[id]" options={{ title: 'Chat' }} />
      </Stack>
      <StatusBar style="auto" />
    </ThemeProvider>
  );
}
```

The root layout renders a `Stack`: screens are pushed on top of each other, with a native header and back button. It also wraps everything in a `ThemeProvider`, so navigation chrome (headers, backgrounds) follows light and dark mode, and sets the status bar style. The `(tabs)` group hides the stack’s header, because its screens draw their own titles.

**src/app/(tabs)/_layout.tsx**

```
import AppTabs from '@/components/app-tabs';

export default function TabsLayout() {
  return <AppTabs />;
}
```

**src/components/app-tabs.tsx**

```
import { NativeTabs } from 'expo-router/native-tabs';
import { useColorScheme } from 'react-native';

import { Colors } from '@/constants/theme';

export default function AppTabs() {
  const scheme = useColorScheme();
  const colors = Colors[scheme === 'dark' ? 'dark' : 'light'];

  return (
    <NativeTabs
      backgroundColor={colors.background}
      indicatorColor={colors.backgroundSelected}
      labelStyle={{ selected: { color: colors.text } }}>
      <NativeTabs.Trigger name="index">
        <NativeTabs.Trigger.Label>Chats</NativeTabs.Trigger.Label>
        <NativeTabs.Trigger.Icon src={require('@/assets/images/tabIcons/chats.png')} renderingMode="template" />
      </NativeTabs.Trigger>

      <NativeTabs.Trigger name="settings">
        <NativeTabs.Trigger.Label>Settings</NativeTabs.Trigger.Label>
        <NativeTabs.Trigger.Icon src={require('@/assets/images/tabIcons/settings.png')} renderingMode="template" />
      </NativeTabs.Trigger>
    </NativeTabs>
  );
}
```

`NativeTabs` renders the platform’s **real** tab bar (including iOS’s translucent one), which is why it feels exactly native. The alternative is `Tabs` from `expo-router`, a JavaScript tab bar that you can restyle freely and that behaves the same on both platforms; choose it when you need a custom design. Either way, each `Trigger` names the file it controls (`index`, `settings`).


## Navigation with Expo Router › Screens are not unmounted

A key difference from web pages: when you push the chat screen on top of the Chats list, **the list stays mounted underneath** with its state intact, so Back is instant and scrolling position is preserved. The consequence is that a `useEffect` that loads data runs only once, when the screen first appears. To refresh data each time a screen comes back into view, use `useFocusEffect`, which runs whenever the screen gains focus. Our list screen uses it through a hook:

**src/hooks/use-conversations.ts**

```
import { useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';

import { listConversations } from '@/lib/data';
import type { Conversation } from '@/lib/types';

/** Loads the conversation list, and reloads it each time the screen comes into view. */
export function useConversations() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setConversations(await listConversations());
      setError(null);
    } catch {
      setError('Could not load your conversations.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  // Runs when the screen gains focus (also after coming back from a chat).
  useFocusEffect(
    useCallback(() => {
      load();
    }, [load]),
  );

  const refresh = useCallback(() => {
    setRefreshing(true); // shows the pull-to-refresh spinner
    load();
  }, [load]);

  const retry = useCallback(() => {
    setLoading(true);
    load();
  }, [load]);

  return { conversations, loading, refreshing, error, refresh, retry };
}
```

`useFocusEffect` requires its callback to be wrapped in `useCallback` so it does not re-run on every render. The hook tracks `loading` (first load), `refreshing` (pull to refresh) and `error` separately, so each one can be shown differently. The data functions it calls are the **seam** to the backend:

**src/lib/data.ts**

```
import type { Conversation, ConversationWithMessages, Message } from './types';

/*
 * A stand-in for the Django API, like lib/data.ts in the web app. In Chapter 24
 * these functions call the real backend and nothing that uses them changes.
 */

let latencyMs = 250; // pretend the network is not instant
export function setLatency(ms: number) {
  latencyMs = ms;
}
const wait = () => new Promise<void>((resolve) => setTimeout(resolve, latencyMs));

let nextMessageId = 100;
const store = new Map<string, ConversationWithMessages>();

function seed() {
  store.clear();
  nextMessageId = 100;
  const now = new Date().toISOString();
  const add = (id: string, title: string, lines: [Message['role'], string][]) => {
    const messages = lines.map(([role, content], i) => ({ id: i + 1, role, content, createdAt: now }));
    store.set(id, { id, title, updatedAt: now, lastMessage: messages.at(-1)?.content ?? null, messages });
  };
  add('welcome', 'Welcome', [
    ['user', 'What can you help me with?'],
    ['assistant', 'I can summarize documents, answer questions and draft text.'],
  ]);
  add('invoices', 'Invoice questions', [
    ['user', "How do I download last month's invoice?"],
    ['assistant', 'Open Billing, choose the month, then select Download PDF.'],
  ]);
}
seed();

/** Put the data back to how it started (used by tests). */
export function resetData() {
  seed();
}

const summary = ({ id, title, updatedAt, lastMessage }: ConversationWithMessages): Conversation => ({
  id,
  title,
  updatedAt,
  lastMessage,
});

export async function listConversations(): Promise<Conversation[]> {
  await wait();
  return [...store.values()].map(summary).sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
}

export async function getConversation(id: string): Promise<ConversationWithMessages | null> {
  await wait();
  return store.get(id) ?? null;
}

export async function createConversation(): Promise<Conversation> {
  await wait();
  const id = Math.random().toString(36).slice(2, 10);
  const now = new Date().toISOString();
  const conversation = { id, title: 'New conversation', updatedAt: now, lastMessage: null, messages: [] };
  store.set(id, conversation);
  return summary(conversation);
}

export async function sendMessage(
  conversationId: string,
  content: string,
): Promise<{ userMessage: Message; assistantMessage: Message }> {
  await wait();
  const conversation = store.get(conversationId);
  if (!conversation) throw new Error('Conversation not found');
  const make = (role: Message['role'], text: string): Message => ({
    id: nextMessageId++,
    role,
    content: text,
    createdAt: new Date().toISOString(),
  });
  const userMessage = make('user', content);
  const assistantMessage = make('assistant', `Echo: ${content}`); // the "AI"
  conversation.messages.push(userMessage, assistantMessage);
  conversation.lastMessage = assistantMessage.content;
  conversation.updatedAt = assistantMessage.createdAt;
  return { userMessage, assistantMessage };
}
```

It pretends the network takes 250 ms (`setLatency`), so you see the loading states while developing, and tests set it to zero. In Chapter 24 these four functions will call Django, and no screen changes.


## Navigation with Expo Router › Deep links

Because routes are URLs, your app can be opened **from outside** at a specific screen. The `scheme` in `app.json` (`chatapp`) makes `chatapp://chat/welcome` open the chat screen. That is how a push notification (Chapter 24) can open the conversation it is about, and how a link in an email can open the app instead of a web page. Try it on a simulator or phone running your app:

**terminal**

```bash
npx uri-scheme open chatapp://chat/welcome --ios       # or --android
```

A URL that matches no file shows `+not-found.tsx` instead of crashing, which matters because anyone can send your app any link.

**src/app/+not-found.tsx**

```
import { Link, Stack } from 'expo-router';
import { StyleSheet } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { Spacing } from '@/constants/theme';

// Shown when a deep link or navigation matches no file in src/app.
export default function NotFoundScreen() {
  return (
    <>
      <Stack.Screen options={{ title: 'Oops!' }} />
      <ThemedView style={styles.container}>
        <ThemedText type="subtitle">This screen doesn’t exist.</ThemedText>
        <Link href="/" style={styles.link}>
          <ThemedText type="linkPrimary">Go to the chats</ThemedText>
        </Link>
      </ThemedView>
    </>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: Spacing.four, gap: Spacing.three },
  link: { paddingVertical: Spacing.three },
});
 src/app/(tabs)/settings.tsx
import Constants from 'expo-constants';
import { Link } from 'expo-router';
import { useState } from 'react';
import { StyleSheet, Switch, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { BottomTabInset, Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';

export default function SettingsScreen() {
  const theme = useTheme();
  const [notifications, setNotifications] = useState(true);

  return (
    <ThemedView style={styles.screen}>
      <SafeAreaView style={styles.safeArea} edges={['top', 'left', 'right']}>
        <ThemedText type="subtitle" accessibilityRole="header" style={styles.title}>
          Settings
        </ThemedText>

        <ThemedView type="backgroundElement" style={styles.card}>
          <View style={styles.row}>
            <ThemedText nativeID="notifications-label">Notifications</ThemedText>
            <Switch
              value={notifications}
              onValueChange={setNotifications}
              accessibilityLabel="Notifications"
              trackColor={{ true: theme.primary }}
            />
          </View>
          <View style={styles.row}>
            <ThemedText>Appearance</ThemedText>
            <ThemedText themeColor="textSecondary">Follows your device</ThemedText>
          </View>
        </ThemedView>

        <View style={styles.footer}>
          <Link href="https://example.com/privacy" accessibilityRole="link">
            <ThemedText type="linkPrimary">Privacy policy</ThemedText>
          </Link>
          <ThemedText type="small" themeColor="textSecondary">
            Version {Constants.expoConfig?.version ?? '1.0.0'}
          </ThemedText>
        </View>
      </SafeAreaView>
    </ThemedView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  safeArea: { flex: 1, paddingHorizontal: Spacing.three, paddingBottom: BottomTabInset },
  title: { paddingVertical: Spacing.three },
  card: { borderRadius: Spacing.three, paddingHorizontal: Spacing.three },
  row: {
    minHeight: 56,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  footer: { marginTop: Spacing.four, gap: Spacing.two },
});
```

The Settings screen is the simplest: a `Switch`, a link to the privacy policy (`Link` opens external URLs in the browser) and the version from `expo-constants`. The notifications switch is only local state for now; Chapter 24 connects it to real push notifications.


## Testing Screens Without a Phone

You do not need a phone or a simulator to test most mobile code. **Jest** runs the tests, **jest-expo** simulates the React Native environment, and **React Native Testing Library (RNTL)** renders components and lets you find and press things the way a user would, exactly as in Chapter 18. Expo Router adds `renderRouter`, which builds a small fake app from the routes you give it, so navigation can be tested too.

**package.json (the Jest settings)**

```
"jest": {
  "preset": "jest-expo",
  "setupFilesAfterEnv": ["<rootDir>/test/setup.ts"],
  "moduleNameMapper": {
    "^@/assets/(.*)$": "<rootDir>/assets/$1",
    "^@/(.*)$": "<rootDir>/src/$1"
  },
  "testMatch": ["<rootDir>/src/**/*.test.ts?(x)"]
}
```

**test/setup.ts**

```
import { resetData, setLatency } from '@/lib/data';

// Safe-area insets come from the phone; in tests, give every screen zero insets.
jest.mock('react-native-safe-area-context', () => require('react-native-safe-area-context/jest/mock').default);

beforeEach(() => {
  setLatency(0); // no pretend-network delay in tests
  resetData(); // every test starts from the same two conversations
});
```

The setup file does three things before every test: it replaces the phone-specific safe-area library with a stand-in, removes the pretend network delay, and resets the mock data, so every test starts from the same two conversations and none depends on another.

> **RNTL 14 is asynchronous**
>
> Version 14 of React Native Testing Library makes its main functions asynchronous, so you write `await render(...)`, `await user.press(...)` and `await user.type(...)`. If you copy older examples that call `render()` without `await`, tests will pass or fail mysteriously. The interactions come from `userEvent.setup()`, which behaves like a real finger: it presses, types character by character and respects disabled buttons. A `Switch` is the exception; it has no press, so use `fireEvent(switch, 'valueChange', false)`.


### Component tests

**src/components/message-bubble.test.tsx**

```
import { render, screen } from '@testing-library/react-native';

import { MessageBubble } from './message-bubble';

describe('MessageBubble', () => {
  it('shows the text', async () => {
    await render(<MessageBubble message={{ role: 'assistant', content: 'Hello!' }} />);
    expect(screen.getByText('Hello!')).toBeOnTheScreen();
  });

  it('is announced to a screen reader as one item that says who wrote it', async () => {
    await render(<MessageBubble message={{ role: 'user', content: 'Hi there' }} />);
    expect(screen.getByLabelText('You: Hi there')).toBeOnTheScreen();
    await screen.rerender(<MessageBubble message={{ role: 'assistant', content: 'Hi there' }} />);
    expect(screen.getByLabelText('Assistant: Hi there')).toBeOnTheScreen();
  });

  it('shows text as text, never as markup', async () => {
    await render(<MessageBubble message={{ role: 'user', content: '<b>bold</b>' }} />);
    expect(screen.getByText('<b>bold</b>')).toBeOnTheScreen();
  });
});
```

**src/components/composer.test.tsx**

```
import { render, screen, userEvent } from '@testing-library/react-native';
import { useState } from 'react';

import { Composer } from './composer';

function Harness({ onSubmit, busy = false }: { onSubmit: () => void; busy?: boolean }) {
  const [value, setValue] = useState('');
  return <Composer value={value} onChangeText={setValue} onSubmit={onSubmit} busy={busy} />;
}

describe('Composer', () => {
  it('keeps Send disabled until there is real text', async () => {
    const user = userEvent.setup();
    await render(<Harness onSubmit={jest.fn()} />);
    const send = screen.getByRole('button', { name: 'Send' });
    expect(send).toBeDisabled();
    await user.type(screen.getByLabelText('Message'), '   ');
    expect(send).toBeDisabled(); // spaces do not count
    await user.type(screen.getByLabelText('Message'), 'Hi');
    expect(send).toBeEnabled();
  });

  it('calls onSubmit when Send is pressed', async () => {
    const onSubmit = jest.fn();
    const user = userEvent.setup();
    await render(<Harness onSubmit={onSubmit} />);
    await user.type(screen.getByLabelText('Message'), 'Hello');
    await user.press(screen.getByRole('button', { name: 'Send' }));
    expect(onSubmit).toHaveBeenCalledTimes(1);
  });

  it('does not submit when busy or empty', async () => {
    const onSubmit = jest.fn();
    const user = userEvent.setup();
    await render(<Harness onSubmit={onSubmit} busy />);
    await user.type(screen.getByLabelText('Message'), 'Hello');
    await user.press(screen.getByRole('button', { name: 'Send' }));
    expect(onSubmit).not.toHaveBeenCalled();
  });
});
```

**src/components/conversation-row.test.tsx**

```
import { render, screen, userEvent } from '@testing-library/react-native';

import { ConversationRow } from './conversation-row';

const conversation = { id: 'c1', title: 'Invoices', updatedAt: '2026-11-02T09:00:00Z', lastMessage: 'See Billing' };

describe('ConversationRow', () => {
  it('shows the title and a preview of the last message', async () => {
    await render(<ConversationRow conversation={conversation} onPress={jest.fn()} />);
    expect(screen.getByText('Invoices')).toBeOnTheScreen();
    expect(screen.getByText('See Billing')).toBeOnTheScreen();
  });

  it('says so when there are no messages yet', async () => {
    await render(<ConversationRow conversation={{ ...conversation, lastMessage: null }} onPress={jest.fn()} />);
    expect(screen.getByText('No messages yet')).toBeOnTheScreen();
  });

  it('is a button that reports which conversation was pressed', async () => {
    const onPress = jest.fn();
    const user = userEvent.setup();
    await render(<ConversationRow conversation={conversation} onPress={onPress} />);
    await user.press(screen.getByRole('button', { name: 'Invoices' }));
    expect(onPress).toHaveBeenCalledWith('c1');
  });
});
```

Queries use the same priority as on the web: by **role and name** (`getByRole('button', { name: 'Send' })`), then by label, then by text. The `Harness` component in the composer test gives the controlled input real state to work with, and the tests prove the Send button is disabled for empty text, for spaces only, and while busy.


### Screen and navigation tests

**src/__tests__/chats-screen.test.tsx**

```
import { Stack } from 'expo-router';
import { userEvent } from '@testing-library/react-native';
import { renderRouter, screen } from 'expo-router/testing-library';
import { Text } from 'react-native';

import ChatsScreen from '@/app/(tabs)/index';
import * as data from '@/lib/data';

// A tiny fake app: the real Chats screen, and a stand-in for the chat screen.
const routes = {
  _layout: () => <Stack screenOptions={{ headerShown: false }} />,
  index: ChatsScreen,
  'chat/[id]': () => <Text>Chat screen</Text>,
};

describe('the Chats screen', () => {
  it('shows a spinner, then the conversations', async () => {
    await renderRouter(routes, { initialUrl: '/' });
    expect(await screen.findByText('Welcome')).toBeOnTheScreen();
    expect(screen.getByText('Invoice questions')).toBeOnTheScreen();
    expect(screen.queryByLabelText('Loading conversations')).toBeNull();
  });

  it('opens a conversation when its row is pressed', async () => {
    const user = userEvent.setup();
    const app = await renderRouter(routes, { initialUrl: '/' });
    await user.press(await screen.findByRole('button', { name: 'Welcome' }));
    expect(app.getPathname()).toBe('/chat/welcome');
    expect(await screen.findByText('Chat screen')).toBeOnTheScreen();
  });

  it('creates a conversation and opens it with the New button', async () => {
    const user = userEvent.setup();
    const creating = jest.spyOn(data, 'createConversation');
    const app = await renderRouter(routes, { initialUrl: '/' });
    await user.press(await screen.findByRole('button', { name: 'New chat' }));
    expect(await screen.findByText('Chat screen')).toBeOnTheScreen();
    expect(creating).toHaveBeenCalledTimes(1);
    expect(app.getPathname()).toMatch(/^\/chat\/[a-z0-9]+$/); // a brand-new id
    expect(app.getPathname()).not.toBe('/chat/welcome');
    creating.mockRestore();
  });

  it('shows an error with a Try again button when loading fails', async () => {
    const user = userEvent.setup();
    const failing = jest.spyOn(data, 'listConversations').mockRejectedValueOnce(new Error('offline'));
    await renderRouter(routes, { initialUrl: '/' });
    expect(await screen.findByText('Could not load your conversations.')).toBeOnTheScreen();
    await user.press(screen.getByRole('button', { name: 'Try again' }));
    expect(await screen.findByText('Welcome')).toBeOnTheScreen();
    failing.mockRestore();
  });
});
```

**src/__tests__/chat-screen.test.tsx**

```
import { Stack } from 'expo-router';
import { userEvent } from '@testing-library/react-native';
import { renderRouter, screen } from 'expo-router/testing-library';

import ChatScreen from '@/app/chat/[id]';
import * as data from '@/lib/data';

const routes = {
  _layout: () => <Stack />,
  'chat/[id]': ChatScreen,
};
const open = (id: string) => renderRouter(routes, { initialUrl: `/chat/${id}` });

describe('the Chat screen', () => {
  it('loads the conversation named in the URL', async () => {
    await open('welcome');
    expect(await screen.findByLabelText('You: What can you help me with?')).toBeOnTheScreen();
    expect(screen.getByLabelText('Assistant: I can summarize documents, answer questions and draft text.')).toBeOnTheScreen();
  });

  it('says so when the conversation does not exist', async () => {
    await open('does-not-exist');
    expect(await screen.findByText('Conversation not found')).toBeOnTheScreen();
  });

  it('shows a sent message at once, then the assistant answer', async () => {
    const user = userEvent.setup();
    await open('welcome');
    await screen.findByLabelText(/^You: What can you help me with/);
    await user.type(screen.getByLabelText('Message'), 'Hello');
    await user.press(screen.getByRole('button', { name: 'Send' }));
    expect(await screen.findByLabelText('Assistant: Echo: Hello')).toBeOnTheScreen();
    expect(screen.getAllByLabelText('You: Hello')).toHaveLength(1); // not duplicated
    expect(screen.getByLabelText('Message')).toHaveDisplayValue(''); // the box was cleared
  });

  it('undoes the optimistic message and restores the text when sending fails', async () => {
    const user = userEvent.setup();
    const failing = jest.spyOn(data, 'sendMessage').mockRejectedValueOnce(new Error('offline'));
    await open('welcome');
    await screen.findByLabelText(/^You: What can you help me with/);
    await user.type(screen.getByLabelText('Message'), 'Important text');
    await user.press(screen.getByRole('button', { name: 'Send' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(/not sent/i);
    expect(screen.getByLabelText('Message')).toHaveDisplayValue('Important text');
    expect(screen.queryByLabelText('You: Important text')).toBeNull();
    failing.mockRestore();
  });
});
```

**src/__tests__/settings-screen.test.tsx**

```
import { fireEvent, render, screen } from '@testing-library/react-native';

import SettingsScreen from '@/app/(tabs)/settings';

describe('the Settings screen', () => {
  it('shows the settings and the app version', async () => {
    await render(<SettingsScreen />);
    expect(screen.getByRole('header', { name: 'Settings' })).toBeOnTheScreen();
    expect(screen.getByText(/^Version /)).toBeOnTheScreen();
    expect(screen.getByText('Privacy policy')).toBeOnTheScreen();
  });

  it('has a notifications switch that can be turned off and on', async () => {
    await render(<SettingsScreen />);
    const toggle = screen.getByLabelText('Notifications', { exact: true });
    expect(toggle).toHaveProp('value', true);
    await fireEvent(toggle, 'valueChange', false);
    expect(screen.getByLabelText('Notifications', { exact: true })).toHaveProp('value', false);
  });
});
```

**src/__tests__/data.test.ts**

```
import { createConversation, getConversation, listConversations, sendMessage } from '@/lib/data';

describe('the mock data layer', () => {
  it('starts with two conversations, newest activity first', async () => {
    const list = await listConversations();
    expect(list.map((c) => c.id).sort()).toEqual(['invoices', 'welcome']);
  });

  it('creates an empty conversation', async () => {
    const created = await createConversation();
    expect(created.lastMessage).toBeNull();
    expect((await getConversation(created.id))?.messages).toEqual([]);
  });

  it('adds the question and the answer, and updates the list preview', async () => {
    const { userMessage, assistantMessage } = await sendMessage('welcome', 'Hello');
    expect(userMessage).toMatchObject({ role: 'user', content: 'Hello' });
    expect(assistantMessage.content).toBe('Echo: Hello');
    const list = await listConversations();
    expect(list[0]).toMatchObject({ id: 'welcome', lastMessage: 'Echo: Hello' }); // moved to the top
  });

  it('rejects for an unknown conversation', async () => {
    await expect(sendMessage('missing', 'Hi')).rejects.toThrow('not found');
    expect(await getConversation('missing')).toBeNull();
  });
});
```

- `renderRouter(routes, { initialUrl })` takes an object whose keys are file names and whose values are components, and creates a fake `src/app` for the test. A `_layout` provides the navigator, as in the real app. The returned `app.getPathname()` lets us assert where the user ended up after pressing a row.
- **Stand-in screens** such as `() => <Text>Chat screen</Text>` keep a test focused: the Chats screen test does not need the real chat screen.
- `jest.spyOn(data, 'sendMessage').mockRejectedValueOnce(...)` simulates a server failure for one call, so we can test the rollback. Restore the spy afterwards with `mockRestore()`.
- `findBy...` **waits** for things to appear, such as the list after the spinner.
> **Timers inside navigation tests**
>
> Expo Router’s test helper runs with Jest’s *fake timers* so that animations finish instantly. The side effect: a `setTimeout` that **you** start directly in the test body (for example by awaiting a data function with a pretend delay) never fires and the test hangs until it times out. Assert through the screen instead (`findByText`, which advances the fake clock while it waits) or spy on the function and check how it was called, as the "New chat" test does.

> **What these tests cannot see**
>
> They do not cover the native tab bar, real gestures, the keyboard, or platform differences. Those need a phone, a simulator, or end-to-end tools (Chapter 39). Treat Jest as the fast safety net for logic and structure, and a real device as the final judge of feel.


## Running on a Device and Checking the Build

Besides Jest, three commands tell you whether the project is healthy. Each ran clean on our code:

| **Command** | **What it checks** |
|---|---|
| `npm run typecheck` | TypeScript, including the typed routes |
| `npx expo lint` | ESLint with Expo’s rules, including the rules of hooks |
| `npx expo export --platform ios --platform android` | Builds the real production JavaScript bundles with Hermes for both platforms. If this succeeds, the app compiles |
| `npx expo-doctor` | Common project problems; some of its checks need an internet connection to Expo’s servers |

During development, three habits make you fast: use **Fast Refresh** (save and see), keep the terminal open because `console.log` output appears there, and shake the phone (or press `m`) for the developer menu, where you can reload, open the element inspector or enable the performance monitor. For deeper debugging, press `j` in the terminal to open the debugger (React Native DevTools), whose component tree shows props and state live, as in the browser.
