Add Settings > Account > Delete account to the Expo app. The App Store requires deletion to be possible inside the app.

Context: the Settings screen is @mobile/app/(tabs)/settings.tsx. The endpoint DELETE /api/v1/account/ already exists. Look at how @mobile/src/privacy/AiConsentGate.tsx handles SecureStore.

Constraints:
- Two-step confirmation: the person must type DELETE before the button is enabled.
- Do not clear anything locally until the server confirms the deletion. On success clear SecureStore and go to /welcome; on failure show a retry message.
- JavaScript only, no new native modules, so this can ship as an over-the-air update.
- Do not touch the version gate or the consent gate.

Done when:
- jest-expo tests cover the confirmation flow, success, and failure.
- A Maestro flow in .maestro/delete-account.yaml covers the happy path.
- `npm test` and `npx expo-doctor` pass.
