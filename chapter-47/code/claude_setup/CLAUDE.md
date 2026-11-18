# AI Chat mobile app

Expo SDK 58, React Native 0.88, expo-router, TypeScript (strict). Talks to our Django API.

## Commands
- Type check: `npx tsc --noEmit`
- Tests: `npm test`
- Project health: `npx expo-doctor`
- Run the app: `npx expo start --dev-client` (we use a development build, not Expo Go)

## How the app is organised (read this before changing anything)
- `lib/core/` is plain TypeScript with no React Native imports. It has Jest tests. Change it only with tests.
- ALL network calls go through `lib/api.ts` (`ApiClient`). Never call `fetch` directly in a screen.
- Tokens live in SecureStore, through `TokenStore`. Never AsyncStorage. Never log tokens, headers or bodies.
- Anything the user changes that must work offline goes through `queue.enqueue(...)` (an idempotency key is added for you).
- A tapped notification is routed ONLY by `routeForNotification()`. Never navigate to a path from a payload.
- Screens live in `app/` (expo-router). Signed-in screens sit inside `Stack.Protected`.

## Rules
- No new dependency without asking. Install with `npx expo install <package>` so the version matches the SDK.
- Do not edit `app.config.ts`, `eas.json`, or anything generated (`ios/`, `android/`) without asking first.
- Never read or print `.env` files. `EXPO_PUBLIC_*` values are public: they must never hold a secret.
- Ask before running anything that builds, submits or publishes (`eas build`, `eas submit`, `eas update`).
- Touch only the files the task needs. List every file you changed at the end.

## Definition of done
- `npx tsc --noEmit` and `npm test` both pass.
- New behaviour has a test (in `lib/core/` if it is logic).
- You have said what you could NOT check (for example: "not tried on a real device").
