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
