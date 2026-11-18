# Chapter 47 — Building Mobile Apps with Claude Code: extended material

The printed edition of *Building AI-Powered Apps* keeps each chapter short. This file holds the longer material that was moved here so that nothing is lost: the full hands-on lab, troubleshooting tables, checklists, further exercises, and sections that were condensed for print.


---

# Sections condensed for print


## Mobile Work with Claude Code: What Changes › Expo's own help for assistants (SDK 58)

Expo SDK 58 shipped on 15 October 2026 with React Native 0.88, and its release notes put weight on working with coding assistants. They describe an agent-oriented command-line tool (`@expo/agent-cli`), agent "skills" for tasks such as upgrading a project (including one for Claude Code), and an Expo MCP server, and they note that Expo's tooling now runs non-interactively by default. These are new and some are marked experimental, so read the release notes (expo.dev/changelog/sdk-58) and the Expo documentation before you rely on them. They are a good example of a trend worth using: the tools you build on are starting to publish instructions for assistants. When a framework offers them, prefer them over what any assistant remembers from training.

> **Expect old advice: this is a fast-moving ecosystem**
>
> An assistant's memory of Expo and React Native is frozen at its training date, and these tools change every few months. In SDK 58 alone: new projects use development builds instead of Expo Go, a notification that arrives while the app is open is now shown by default, and Android release builds are minified by default. Always state your versions in the prompt ("Expo SDK 58, React Native 0.88, expo-router"), install packages with `npx expo install` so they match the SDK, and let the type checker catch names that have changed.


## Setting Up the Project So Claude Code Does Good Work › Create the project

Expo's SDK 58 notes say that, until the matching Expo Go app is released, `create-expo-app` creates SDK 57 projects by default, and that SDK 58 needs a **development build**. Ask for the right template explicitly, and make sure Node is new enough (the release notes require 22.13 or later on Node 22):

**bash terminal**

```bash
node -v                                    # 22.13 or newer
npx create-expo-app@latest mobile --template default@sdk-58
cd mobile
npx expo install expo-secure-store expo-notifications expo-camera expo-device \
  expo-constants expo-linking @react-native-community/netinfo \
  @react-native-async-storage/async-storage
```

`npx expo install` picks the version of each package that matches the installed SDK, which a plain `npm install` does not. This is the single most common source of "it worked in the tutorial" mobile errors, and it is worth putting in the rules file below so that Claude uses it too.


## Setting Up the Project So Claude Code Does Good Work › Enforce the important rules: permissions

Rules in `CLAUDE.md` are requests. Rules in the project's settings file are enforced by Claude Code itself: it checks each action against them before it runs. Commit this file so the whole team shares it:

**.claude/settings.json**

```
{
  "permissions": {
    "allow": [
      "Bash(npx tsc --noEmit)",
      "Bash(npm test)",
      "Bash(npx expo-doctor)",
      "Bash(git status)",
      "Bash(git diff)"
    ],
    "deny": [
      "Read(./.env)",
      "Read(./.env.*)",
      "Bash(eas build:*)",
      "Bash(eas submit:*)",
      "Bash(eas update:*)"
    ]
  }
}
```

The `allow` list lets common safe checks run without a prompt each time. The `deny` list refuses to read your `.env` files and to run `eas build`, `eas submit` or `eas update`, because each of those spends money, publishes something, or both. Personal exceptions go in `.claude/settings.local.json`, which should not be committed. **Do not trust a rule you have not tested.** The syntax for rules has changed over time, so the hands-on has a step where you ask Claude Code to do each forbidden thing on a scratch branch and confirm that it refuses (inspect the active rules with the `/permissions` command). For things that must *never* happen, Claude Code also supports **hooks**: scripts that run at defined moments, such as before a command, and can block it. Hooks run deterministically, which is why the documentation positions them as the enforcement tool.


## Setting Up the Project So Claude Code Does Good Work › A command and a reviewer you reuse

Two more files make good habits cheap. A **custom command** is a prompt saved in `.claude/commands/`, run as `/new-screen ...`. This one forces the "plan first" workflow every time:

**.claude/commands/new-screen.md**

```
---
description: Plan and build a new screen that follows this app's rules
argument-hint: <screen name and what it should do>
---
Add a new screen: $ARGUMENTS

Work in this order, and stop after step 1 so I can approve the plan:
1. Read CLAUDE.md, then look at one existing screen under `app/` and `lib/api.ts`. Write a short plan: the route file, the data it needs (which API endpoint), the states (loading, empty, error, offline), and the tests you will add. Do not write code yet.
2. After I approve: build it with the smallest change. Use `ApiClient` for reads and the offline queue for writes.
3. Run `npx tsc --noEmit` and `npm test` and show me the results.
4. List every file you changed and anything you could not check.
```

A **subagent** is a separate assistant with its own instructions and its own set of allowed tools. The reviewer below can only read files, which makes it safe to run on any change, and because it starts with a fresh context it is not biased by the conversation that wrote the code (Chapter 41 explained why that matters):

**.claude/agents/mobile-reviewer.md**

```
---
name: mobile-reviewer
description: Read-only reviewer for React Native and Expo changes. Use after a screen or library change is finished, before committing.
tools: Read, Grep, Glob
---
You review mobile app changes. You cannot edit files or run commands, so you only read.
Check authentication and token handling, offline behaviour, permission prompts (are they asked in
context, with an honest explanation, and is the "denied forever" case handled?), notification
handling, and accessibility labels on buttons. Report concerns ranked by seriousness, each with a
file and line and what would show you are wrong. Say clearly what you could not verify from the code.
```

The zip for this chapter also includes `review-diff.md`, a second command that runs a checklist over your uncommitted changes.


## Authentication and Secure Token Storage › Seven rules for tokens on a phone

| **Rule** | **Why** |
|---|---|
| **Tokens go in secure storage, never AsyncStorage** | AsyncStorage is plain text on the device. `expo-secure-store` uses the iOS Keychain and an Android keystore-backed store. |
| **Keep stored values small and validated** | Store the two tokens and an expiry as one small JSON value. If what you read back is malformed, treat it as signed out and remove it. |
| **Never put a secret in the app** | Anything shipped in the app can be extracted. The model API key, the payment secret and database passwords stay on your backend (Chapters 17, 29 and 36). |
| `EXPO_PUBLIC_` **variables are public** | Expo copies them into the app as plain text. They are for addresses and public identifiers only. |
| **One refresh at a time** | When several requests fail with 401 together, they must share one refresh. Refresh tokens are often single-use, so a second refresh would fail and sign the user out. |
| **Offline is not signed out** | If a refresh fails because the network is down, keep the tokens. Sign out only when the server refuses the refresh token. |
| **Never log tokens** | Log the request path, status and time, never headers or bodies. Logs are shared with colleagues and with assistants. |


## Push Notifications, Camera and Permissions › Least privilege: find out what your app really asks for

Every permission your app declares is shown in the store listing and examined in review, and each one is a question a user may ask. Assistants add permissions generously, and libraries add some of their own. You can see exactly what you declare, before any build, by letting Expo generate the native project in a scratch folder. This is real output from the example app:

**bash terminal (real output, relevant part only, before any change to the config)**

```bash
npx expo config --type public --json

"android": { "permissions": ["android.permission.CAMERA", "android.permission.RECORD_AUDIO"] }
```

The app only scans codes, yet the **microphone** permission is already in the list: the camera plugin adds it by default. After turning that off (shown below), I generated the native Android project with `expo prebuild`, which shows what the manifest really contains:

**bash terminal (real: the generated manifest, microphone already turned off)**

```bash
npx expo prebuild --platform android --no-install

"android.permission.CAMERA"
"android.permission.INTERNET"
"android.permission.READ_EXTERNAL_STORAGE"
"android.permission.SYSTEM_ALERT_WINDOW"
"android.permission.VIBRATE"
"android.permission.WRITE_EXTERNAL_STORAGE"
```

Two findings. First, as shown, the camera plugin asks for the microphone unless you set `recordAudioAndroid` to `false`. Second, the generated manifest includes external-storage and "draw over other apps" permissions that the app never uses. Both can be removed in `app.config.ts`:

**app.config.ts**

```
import type { ConfigContext, ExpoConfig } from "expo/config";

// Replace the identifiers below with your own. They cannot be changed after a store release.
export default ({ config }: ConfigContext): ExpoConfig => ({
  ...config,
  name: "AI Chat",
  slug: "ai-chat",
  scheme: "aichat", // lets a link such as aichat://chat/42 open the app
  version: "1.0.0",
  orientation: "portrait",
  ios: {
    bundleIdentifier: "com.example.aichat",
    supportsTablet: false,
  },
  android: {
    package: "com.example.aichat",
    // The template adds these by default. We do not use them, so we remove them: fewer permissions
    // means a shorter store listing, an easier review, and less to explain to users.
    blockedPermissions: [
      "android.permission.SYSTEM_ALERT_WINDOW",
      "android.permission.READ_EXTERNAL_STORAGE",
      "android.permission.WRITE_EXTERNAL_STORAGE",
    ],
  },
  plugins: [
    "expo-router",
    "expo-secure-store",
    // The text the system shows when it asks for permission. Say what you use it for, and be honest.
    [
      "expo-camera",
      {
        cameraPermission: "AI Chat uses the camera only to scan codes. Nothing is saved or uploaded.",
        // We never record video with sound, so do not ask for the microphone at all. The plugin
        // adds RECORD_AUDIO on Android by default, and a permission you do not need is a
        // permission a reviewer, and a user, will question.
        recordAudioAndroid: false,
        microphonePermission: false,
      },
    ],
    "expo-notifications",
  ],
  extra: {
    // Filled in by `eas init`. Push tokens need it. It identifies the project and is not secret.
    eas: { projectId: process.env.EAS_PROJECT_ID },
  },
});
```

**bash terminal (real, after the change)**

```bash
npx expo prebuild --platform android --no-install

<uses-permission android:name="android.permission.CAMERA"/>
<uses-permission android:name="android.permission.INTERNET"/>
<uses-permission android:name="android.permission.READ_EXTERNAL_STORAGE" tools:node="remove"/>
<uses-permission android:name="android.permission.SYSTEM_ALERT_WINDOW" tools:node="remove"/>
<uses-permission android:name="android.permission.VIBRATE"/>
<uses-permission android:name="android.permission.WRITE_EXTERNAL_STORAGE" tools:node="remove"/>
```

The three unwanted permissions are now marked for removal (`tools:node="remove"`), and the microphone is gone. On iOS, the generated `Info.plist` had the camera usage text and no microphone entry (the check counted one camera string and zero microphone strings). Notice what this teaches about assistants: they will happily write a plugin entry that works, and not notice that it asks for more than the app needs. **Ask Claude Code to list every permission the app declares and justify each one**, and run the command above yourself to see the truth. One caution: libraries can add permissions when the final app is built (for example, notifications on Android), so inspect the built app's manifest before a release too. I did not build one here.

> **Generated native folders: where to run prebuild**
>
> `expo prebuild` creates `ios/` and `android/` folders. In a project that uses Expo's managed approach, those are generated output that you normally do not commit. Run the commands above in a scratch copy of the project, or delete the folders afterwards, and tell Claude Code (in `CLAUDE.md`) not to edit them. If an assistant starts hand-editing generated native files, the next prebuild will erase its work.


## Testing on Simulators and Devices › A checklist worth running before every release

| **Case** | **What you should see** |
|---|---|
| **Airplane mode, then send a message** | The message appears at once, marked pending; the offline banner shows one waiting change; turning the network back on sends it, and the marker disappears |
| **Force-close the app while a message is pending** | After reopening and reconnecting, the message is sent exactly once |
| **Access token expires while the app is open** | The next request succeeds without the user noticing (set a very short token lifetime on a test backend) |
| **Refresh token revoked on the server** | The user is returned to the sign-in screen, and nothing from the old session remains on screen |
| **Sign out, then look at storage** | No tokens remain, and queued items from the old user are not sent as the new one |
| **Background the app for a minute, then return** | The socket reconnects without a duplicate burst; no stale data is shown as fresh |
| **Poor connection (throttled or far from the router)** | Timeouts appear as a clear message with a retry, not an endless spinner |
| **Camera permission denied, and denied for good** | The explanation screen appears, and "Open Settings" works |
| **Notification tapped: app closed, in the background, in the foreground** | The right screen opens in all three cases; a forged payload opens nothing |
| **Release build, not only a development build** | Nothing crashes that did not crash in development. SDK 58 minifies Android release builds by default, which can break code that relies on reflection |

When something fails, paste the **real error text** into Claude Code, with the steps you took and the platform, exactly as section 41.4 of Chapter 41 describes, and ask for a failing test first if the bug is in logic. Component tests for screens are possible with `jest-expo` and React Native Testing Library, and end-to-end tools such as Maestro drive a real app, but start with the logic tests: they are where this chapter's tests give you the most confidence for the least effort.


## EAS Build Configuration, Generated Safely

Chapter 26 covered EAS Build and store submission. Here the question is how to let an assistant write your build configuration without letting it spend money, change something permanent, or ship a build to the wrong place. Start with what the files do.

**eas.json**

```
{
  "cli": {
    "version": ">= 16.18.0",
    "appVersionSource": "remote"
  },
  "build": {
    "development": {
      "developmentClient": true,
      "distribution": "internal",
      "env": {
        "EXPO_PUBLIC_API_URL": "https://staging-api.example.com",
        "EXPO_PUBLIC_WS_URL": "wss://staging-api.example.com"
      }
    },
    "preview": {
      "distribution": "internal",
      "channel": "preview",
      "android": { "buildType": "apk" },
      "env": {
        "EXPO_PUBLIC_API_URL": "https://staging-api.example.com",
        "EXPO_PUBLIC_WS_URL": "wss://staging-api.example.com"
      }
    },
    "production": {
      "autoIncrement": true,
      "channel": "production",
      "env": {
        "EXPO_PUBLIC_API_URL": "https://api.example.com",
        "EXPO_PUBLIC_WS_URL": "wss://api.example.com"
      }
    }
  },
  "submit": {
    "production": {}
  }
}
```

| **Profile** | **What it is for** |
|---|---|
| **development** | `developmentClient: true` builds your app with Expo's developer tools, for daily work. `distribution: internal` means it is installed directly on test devices, not through the stores. |
| **preview** | A release-style build for testers (`internal` distribution; on Android an `apk` so it can be installed directly). Its `channel` is where over-the-air updates for testers are published (Chapter 26). |
| **production** | The build you submit to the stores. `autoIncrement` raises the build number each time, and with `appVersionSource` set to `remote` EAS keeps the build number, so versions cannot clash. |

The shape above matches the default that Expo's documentation shows for a new project (`development`, `preview` and `production` profiles, `appVersionSource: remote`, and an empty `submit.production`). The `env` entries set the public API and WebSocket addresses per profile, so a preview build talks to staging and a production build talks to production, and neither can be pointed at the wrong server by an edited `.env` file. They are `EXPO_PUBLIC_` values, so they are public: secrets do not belong here either.


### What to ask Claude Code, and what to forbid

- **Ask it to draft and explain**  `eas.json` and `app.config.ts` changes, and to run `npx expo config`, `npx expo-doctor` and a scratch `expo prebuild` to check them. These are safe, free and repeatable. The `expo config` output earlier in this chapter is exactly the kind of evidence to ask for.
- **Forbid it from running**  `eas build`, `eas submit` and `eas update`. Builds cost money or queue time, a submission is visible to Apple and Google, and an update is delivered to real users. The deny rules in `settings.json` and the line in `CLAUDE.md` do this. You run these commands, deliberately, after reading the diff.
- **Treat identifiers as permanent.** The bundle identifier and Android package name cannot be changed after you publish. The placeholders in the example (`com.example.aichat`) must be replaced with your own, once, on purpose. Do not let an assistant "tidy" them.
- **Never put secrets in either file.** Signing credentials are handled by EAS (Chapter 26). Keep keys and passwords out of `app.config.ts`, `eas.json` and `EXPO_PUBLIC_` variables.
- **Pin the facts that matter in** `CLAUDE.md`**:** the SDK version, the Node version, and the rule to use `npx expo install`.
> **Test a release build early**
>
> SDK 58's release notes say that Android release builds now minify code with R8 by default. Code that works in a development build can fail in release if a library depends on names that minification removes. Make a preview build in the first week, not the last, and run the checklist from section 47.8 on it.


### Verify before you build

| **Command** | **What it tells you** |
|---|---|
| `python -m json.tool eas.json` (or any JSON check) | That the file is valid JSON. This is all that was checked here: EAS validates the full schema when you run a build. |
| `npx expo config --type public --json` | That `app.config.ts` loads, which plugins and permissions resolve, and the SDK version |
| `npx expo-doctor` | Common problems with versions and configuration |
| `npx expo prebuild --platform android --no-install` (in a scratch copy) | The native files that a build would use, including the exact permissions |
| `npx tsc --noEmit` | That names, arguments and types match the installed SDK |
