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
