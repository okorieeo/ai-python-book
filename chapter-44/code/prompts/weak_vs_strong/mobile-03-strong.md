Add step 1 of 3 of push notifications: ask for permission and register the device token. Sending notifications comes in a later step, so do not build it.

Context: read https://docs.expo.dev/versions/latest/sdk/notifications/ and @mobile/app.config.ts. The token is registered with POST /api/v1/devices/ (see @backend/devices/views.py).

Constraints:
- Ask for permission only after the person's first successful reply, never at launch.
- If permission is denied, remember that in SecureStore and never ask again.
- expo-notifications is a native change: do not run eas build, and do not bump the version yourself. List exactly what will need a new store build.
- Do not touch the version gate or the consent gate.

Done when jest tests with the module mocked cover granted, denied, and already-asked, and `npm test` passes. End your reply with the list of changes that require a new build.
