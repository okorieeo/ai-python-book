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
