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
