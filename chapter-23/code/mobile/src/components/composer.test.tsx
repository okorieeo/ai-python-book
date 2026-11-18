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
