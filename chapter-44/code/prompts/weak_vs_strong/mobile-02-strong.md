Show a dismissible "You're offline" banner at the top of the chat screen when the device has no connection, and disable the send button while offline.

Context: the screen is @mobile/app/chat/[id].tsx and the colours come from @mobile/src/theme.ts. Check package.json for @react-native-community/netinfo; if it is not installed, stop and tell me before adding it, because it is a native module.

Constraints:
- Reading the existing history must keep working offline.
- Use the existing theme colours, and do not poll; subscribe to connectivity changes.
- Do not change how messages are sent, only whether the button is enabled.

Done when a jest-expo test with NetInfo mocked shows the banner appears when offline, disappears when back online, and the send button is disabled only while offline. `npm test` passes.
