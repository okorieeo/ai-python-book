cd ~/projects/ai-chat-app/mobile

npx expo install expo-dev-client expo-secure-store expo-notifications \
  expo-image-picker expo-camera expo-device expo-constants expo-splash-screen
npx expo install --dev jest-expo jest @types/jest

npm install -g eas-cli
eas login
eas init                       # creates the project id the push service needs
eas build --profile development --platform android   # or: npx expo run:android
