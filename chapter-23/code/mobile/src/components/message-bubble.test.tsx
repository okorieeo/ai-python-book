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
