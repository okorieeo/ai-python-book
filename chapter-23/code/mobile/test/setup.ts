import { resetData, setLatency } from '@/lib/data';

// Safe-area insets come from the phone; in tests, give every screen zero insets.
jest.mock('react-native-safe-area-context', () => require('react-native-safe-area-context/jest/mock').default);

beforeEach(() => {
  setLatency(0); // no pretend-network delay in tests
  resetData(); // every test starts from the same two conversations
});
