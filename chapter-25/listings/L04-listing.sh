cd ~/projects/ai-chat-app
git checkout main && git pull
git checkout -b feature/mobile-resilience
cd mobile
npx expo install @react-native-community/netinfo
    @react-native-async-storage/async-storage
npx expo install @tanstack/react-query @tanstack/react-query-persist-client
npx expo install @tanstack/query-async-storage-persister expo-crypto expo-constants
npx expo install react-error-boundary zod @shopify/flash-list expo-image
npm install --save-dev tsx @types/node
