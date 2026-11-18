# Chapter 47 code: a tested mobile core, example Expo screens, and Claude Code setup

    mobile-core/     plain TypeScript: tokens, API client, offline queue, WebSocket, notification routing.
                     No React Native imports. 81 Jest tests.
        cd mobile-core && npm install && npm test && npx tsc --noEmit
    app_patterns/    example Expo SDK 58 files: lib/, app/, components/, app.config.ts, eas.json, .env.example.
                     Type-checked against Expo 58.0.23 / React Native 0.88.1 (not run on a device).
    claude_setup/    CLAUDE.md, .claude/settings.json, two commands, one read-only reviewer subagent.

See Step 2 and Step 3 of the chapter for copying these into an Expo project:
`lib/core` in the app is the contents of `mobile-core/src`, and the screens import it as `@/lib/core`.
The code is a starting point: adapt the endpoints, the refresh response and the WebSocket messages to
your own backend (Chapters 13 and 14).
