# Chapter 26 — Building and Releasing Mobile Apps: extended material

The printed edition of *Building AI-Powered Apps* keeps each chapter short. This file holds the longer material that was moved here so that nothing is lost: the full hands-on lab, troubleshooting tables, checklists, further exercises, and sections that were condensed for print.


---

# Sections condensed for print


## A Release Is Not a Deploy › Three environments, three kinds of build

You already have three places your backend runs: your laptop, a staging or preview environment, and production. The mobile app mirrors that with three build types, each with a different audience:

| **Profile** | **Who installs it** | **Backend it talks to** | **How it is distributed** |
|---|---|---|---|
| development | You, with the dev client | Your laptop or a dev server | Internal link or simulator |
| preview | Teammates and testers | Staging | Internal link (APK, ad hoc iOS) |
| production | Everyone | Production | App Store and Google Play |

The rest of the chapter builds this ladder one rung at a time, and then adds the safety nets that let you climb it with confidence.


## Before You Build: Identity, Versions and Configuration › Decision 3: one codebase, three installable identities

If your development, preview and production builds all share one identifier, installing one replaces the other on your phone, and you can never compare the stable app with the one you are testing. **App variants** fix this by giving each build type its own identifier, name and deep-link scheme so all three live side by side.

The variants are plain data in a small file with no Expo imports, which makes them easy to test:

**mobile/config/variants.ts**

```
export type VariantName = "development" | "preview" | "production";

export interface Variant {
  name: VariantName;
  appName: string;
  /** iOS bundle identifier AND Android application id. */
  bundleId: string;
  /** Deep-link scheme, unique per variant so links open the right build. */
  scheme: string;
}

// REPLACE with a reverse-domain name you own. It can never change after release.
export const BASE_BUNDLE_ID = "com.example.aichat";

export const VARIANTS: Record<VariantName, Variant> = {
  development: {
    name: "development",
    appName: "AI Chat (Dev)",
    bundleId: `${BASE_BUNDLE_ID}.dev`,
    scheme: "aichat-dev",
  },
  preview: {
    name: "preview",
    appName: "AI Chat (Preview)",
    bundleId: `${BASE_BUNDLE_ID}.preview`,
    scheme: "aichat-preview",
  },
  production: {
    name: "production",
    appName: "AI Chat",
    bundleId: BASE_BUNDLE_ID,
    scheme: "aichat",
  },
};

/**
 * Turn the APP_VARIANT environment variable into a variant.
 * Unset means "development" (what you want on your laptop). A value we do not
 * recognise is a typo, and a typo must stop the build, not quietly ship the
 * wrong identity.
 */
export function resolveVariant(raw: string | undefined): Variant {
  if (raw === undefined || raw === "") return VARIANTS.development;
  if (Object.prototype.hasOwnProperty.call(VARIANTS, raw)) {
    return VARIANTS[raw as VariantName];
  }
  throw new Error(
    `Unknown APP_VARIANT "${raw}". Use one of: ${Object.keys(VARIANTS).join(", ")}.`,
  );
}
```

Notice `resolveVariant`. An unset `APP_VARIANT` means development (what you want on a laptop), but a value it does not recognise, such as `prod` instead of `production`, **throws**. A typo that silently built the wrong identity would be far worse than a failed build.

`app.config.ts` then turns the chosen variant into Expo’s configuration. It replaces the static `app.json` from earlier chapters; Expo reads whichever one exists, and the dynamic form is what lets one file produce three identities.

**mobile/app.config.ts**

```
import type { ConfigContext, ExpoConfig } from "expo/config";

import { resolveVariant } from "./config/variants";

// Created by `eas init`. Replace both values.
const EAS_PROJECT_ID = "00000000-0000-0000-0000-000000000000";
const EXPO_OWNER = "your-expo-username";

export default ({ config }: ConfigContext): ExpoConfig => {
  const variant = resolveVariant(process.env.APP_VARIANT);

  return {
    ...config,
    name: variant.appName,
    slug: "ai-chat-app",
    owner: EXPO_OWNER,
    // The version people see in the store. You change this by hand, on purpose.
    // The build number / version code is NOT here: Expo Build manages it
    // remotely (cli.appVersionSource = "remote" in eas.json).
    version: "1.0.0",
    orientation: "portrait",
    icon: "./assets/icon.png",
    scheme: variant.scheme,
    userInterfaceStyle: "automatic",

    // An update may only reach builds with the same native code. "appVersion"
    // ties the runtime version to `version` above (see 26.9).
    runtimeVersion: { policy: "appVersion" },
    updates: { url: `https://u.expo.dev/${EAS_PROJECT_ID}` },

    ios: {
      bundleIdentifier: variant.bundleId,
      supportsTablet: true,
      infoPlist: {
        // We only use the encryption built into iOS (HTTPS). See 26.7.
        ITSAppUsesNonExemptEncryption: false,
        // Adjust these two to match the permissions you added in Chapter 24.
        NSCameraUsageDescription:
          "AI Chat uses the camera so you can attach a photo to a message.",
        NSPhotoLibraryUsageDescription:
          "AI Chat reads photos you choose so you can attach them to a message.",
      },
    },
    android: {
      package: variant.bundleId,
      adaptiveIcon: {
        foregroundImage: "./assets/adaptive-icon.png",
        backgroundColor: "#1E3A8A",
      },
    },
    plugins: ["expo-router", "expo-secure-store"],
    extra: {
      variant: variant.name,
      eas: { projectId: EAS_PROJECT_ID },
    },
  };
};
```

Four details in that file deserve a pause:

- **There is no** `buildNumber` **or** `versionCode`**.** That is on purpose; the remote counter owns them.
- `runtimeVersion` **uses the** `appVersion` **policy.** An update can only reach builds with a matching runtime version, and this policy makes it equal to `version`. Section 26.9 explains why that is the safe default.
- `ITSAppUsesNonExemptEncryption: false` answers Apple’s export-compliance question in advance. It is a legal statement: it is true here because the app uses only the encryption built into iOS (HTTPS). The Fernet encryption from Chapter 17 runs on your server, not in the app. If you later add your own encryption inside the app, revisit this.
- **The permission strings** (camera, photo library) must explain *why* in plain language. Apple reviewers read them, and a vague string is a common rejection reason.

## Before You Build: Identity, Versions and Configuration › Decision 4: where settings and secrets live

Mobile apps have a rule that surprises backend developers: **there are no secrets in the app.** Anything inside the bundle can be extracted by anyone who downloads it. Variables prefixed `EXPO_PUBLIC_` are inlined into the JavaScript at build time and are therefore public by design, which makes them right for an API base URL and wrong for an API key.

Expo Services has its own environment variables, scoped to the `development`, `preview` and `production` environments, with visibility levels (plain text, sensitive, secret). Use them for per-environment values like `APP_VARIANT` and `EXPO_PUBLIC_API_URL`, and select the environment in each build profile with the `environment` field. Because `eas update` takes an `--environment` flag as well, an update is built with the same values as the matching build. Values written in the `env` block of `eas.json` are committed to Git and, as Expo’s reference points out, are not available to updates, so they are the wrong home for anything that must match.

**Create the per-environment variables (run once)**

```
# Flags can differ between eas-cli versions: run `eas env:create --help`,
# or add the same values in the Expo dashboard under Environment variables.
eas env:create --environment production --name APP_VARIANT --value production --visibility plaintext
eas env:create --environment production --name EXPO_PUBLIC_API_URL --value https://api.yourdomain.com --visibility plaintext

# Repeat for preview (staging API) and development (your laptop):
eas env:create --environment preview --name APP_VARIANT --value preview --visibility plaintext
```

> **Where your AI provider key lives**
>
> The Anthropic API key stays on the Django server (Chapter 29), exactly as in Chapter 17. The app never calls the AI provider directly; it calls your backend, which authenticates the user, enforces the token budget and then calls the provider. If you ever find yourself writing `EXPO_PUBLIC_ANTHROPIC_API_KEY`, stop: the release check in Chapter 26 will fail the build, and it is right to.


## Expo Build and eas.json › The commands you will actually use

| **Goal** | **Command** |
|---|---|
| First-time setup (creates `eas.json`, links the project) | `eas build:configure` then `eas init` |
| Development client for a real Android phone | `eas build --platform android --profile development` |
| iOS Simulator build, no Apple account needed | `eas build --platform ios --profile development-simulator` |
| Test build for testers | `eas build --platform all --profile preview` |
| Store build | `eas build --platform all --profile production` |
| Build, then submit when it finishes | `eas build --platform android --profile production --auto-submit` |
| Build on your own machine instead of Expo’s | add `--local` to any build command |

A cloud build moves through a queue, then installs dependencies, builds the native project and uploads the result. When it fails, the build page shows the full log and groups it into phases. **Always scroll to the first error**, not the last: the last lines are usually the build tool summarising a failure that started much earlier.

> **Cost and speed**
>
> Expo’s free plan includes a limited number of builds, with lower priority in the queue than paid plans. The exact allowances change, so read the current pricing page before planning a launch week. Building locally with `--local` is free, but needs your own toolchain (and a Mac for iOS).

> **Pin your Node version for repeatable builds**
>
> A build profile accepts a `node` field. If a build that worked last month suddenly fails, an unpinned toolchain is a common suspect. Pin it once the app is stable, and bump it deliberately.


## App Signing, Demystified › Rules that keep you out of trouble

1. **Never commit a keystore,** `.p8` **key or service-account JSON.** Add them to `.gitignore` today. Chapter 17’s secret-scanning habit applies here too.
2. **Back up the Android credentials** the first time they are created.
3. **Use an organization-owned account, not a personal one,** once the app matters. If the only person who can log in to the developer account leaves, you are locked out of your own app.
4. **Turn on two-factor authentication** on your Apple, Google and Expo accounts. These accounts can publish software to your users.
5. **Know who is allowed to run production builds.** An `EXPO_TOKEN` in CI is a credential with real power; scope and rotate it like any other.
> **Certificates expire**
>
> An expired iOS distribution certificate does not break apps already installed, but it blocks your next build until it is renewed. Put the expiry date in the team calendar. If you let Expo manage credentials, it can usually renew during a build, but the Apple account still has to be reachable.


## Store Accounts and Listings › What a listing needs

Both stores require far more than a name and an icon. Collect these *before* the first submission so the review is not the first time you notice something is missing:

- **Name, subtitle or short description, full description, keywords.** Do not mention other platforms or competing products in the name; reviewers reject it.
- **Screenshots** in the sizes each store currently asks for, and a high-resolution icon with no transparency for iOS. Both stores publish the current size lists; follow them rather than guessing.
- **A privacy policy at a public URL.** Both stores require one for any app that handles personal data, and an AI chat app clearly does.
- **Support contact and a support page.**
- **Category and age rating.** Both stores ask a questionnaire. Answer it honestly for what the AI can produce, not only for what you intend.
- **Review notes and a demo account** (Apple) so the reviewer can get past your login. The bundle includes a template at `store/review-notes-template.md`.
> **Write the listing in the app’s own voice, once**
>
> Draft the description, screenshots text and privacy policy in one sitting, and keep them in the repository. When a reviewer asks “what does this app do?”, the answer should already exist and match what the app and the listing say.


## Submitting with eas submit › Android: a service account

Google does not let tools use your login. Instead you create a **service account**, a robot identity inside Google Cloud, download its JSON key, and grant it permission to publish for your app in Play Console. Then give the key to Expo:

**Terminal**

```bash
eas credentials --platform android
# choose: production > Google Service Account > Set up a Google Service Account Key for Play Store Submissions
```

For a brand-new app, Expo’s documentation says the default `eas submit` works out of the box and creates the first release on the **internal testing track**. The app remains a draft in Play Console until you complete the store listing and the setup tasks, and that has to happen before anything can be promoted to production. Before you run it, the app must already exist in Play Console, and `android.package` must be set.


## Submitting with eas submit › iOS: an App Store Connect API key and an app id

Create the app record in App Store Connect with your bundle identifier. Its numeric **Apple ID** (shown in the app’s information page) goes into `eas.json` as `ascAppId`. Then run the submit; the first time, Expo asks you to authorise with an App Store Connect API key, which it can create and store.

**Terminal**

```bash
eas submit --platform ios --profile production
eas submit --platform android --profile production
```

After upload, the iOS build sits in “Processing” for a while, then appears in TestFlight. From there you attach it to a version in App Store Connect, fill in the review information and press **Submit for Review**. Expo uploads the binary; it does not write your listing or press the final button, and that is by design.


## Submitting with eas submit › Typical rejections and what they usually mean

| **Symptom** | **Usual cause** | **Fix** |
|---|---|---|
| Apple: app crashed or is incomplete (2.1) | Reviewer could not log in or hit an empty state | Provide a working demo account and review notes |
| Apple: missing consent or privacy information (5.1.1, 5.1.2) | No AI-sharing consent, vague permission strings, no account deletion | Section 26.7, then resubmit with notes explaining where each lives |
| Apple: metadata does not match the app (2.3) | Screenshots or description show features not in the build | Make the listing describe this build |
| Apple: in-app purchase rules (3.1.1) | Digital goods sold through an external payment flow | Read the current guidelines for your countries |
| Google: policy or Data safety mismatch | Declaration says no data shared; the app shares data | Correct the form from your worksheet |
| Google: target API level too low | Old SDK | Upgrade the Expo SDK |
| Upload refused: version already used | Build number reused | Use `appVersionSource: remote` with `autoIncrement` |

A rejection is a conversation, not a verdict. Read the exact guideline number quoted, fix the cause, reply in the review thread with what changed, and resubmit. Apple lets you reply to a reviewer, and a short polite note about where to find the fixed behaviour often saves a round trip.


## Over-the-Air Updates with Expo Update › Channels and branches

Two words do the routing. A **channel** is a name baked into each build: `production`, `preview`. A **branch** is a named stream of updates. The channel points at a branch, and a build listens to its channel. Publishing with `--channel` is the everyday shortcut:

**Terminal**

```bash
# JS-only fix for testers (this is what mobile-update.yml does on every merge):
eas update --channel preview --environment preview --message "Fix retry on 429"

# After testers confirm, publish the same fix to real users:
eas update --channel production --environment production --message "Fix retry on 429"
```

Keeping `preview` and `production` as separate channels is what lets testers run tomorrow’s JavaScript safely while real users stay on today’s. The release check in Chapter 26 fails the pipeline if both profiles ever point at the same channel.

> **Promote the tested update instead of rebuilding it**
>
> Publishing again with `--channel production` creates a *new* bundle, built from whatever your working tree contains at that moment. To ship exactly what testers approved, re-publish the existing update to the production channel with `eas update:republish`, and check `--help` for the flags of your CLI version. “Tested” should mean “this very bundle”.


## Over-the-Air Updates with Expo Update › When the update arrives

By default `expo-updates` checks for an update at launch, downloads it in the background and **applies it on the next launch**. A person can therefore be a launch behind. That is usually what you want: nobody has their chat reloaded under them. The component below downloads an update when one exists, then offers a restart instead of forcing one.

**mobile/src/release/UpdateBanner.tsx**

```
/**
 * Downloads an over-the-air update in the background and offers a restart.
 * Never restarts on its own: reloading in the middle of a chat loses the draft.
 * Disabled in development builds, where expo-updates is not active.
 */
export function UpdateBanner() {
  const { isUpdateAvailable, isUpdatePending } = Updates.useUpdates();

  useEffect(() => {
    if (isUpdateAvailable && !isUpdatePending) {
      Updates.fetchUpdateAsync().catch(() => {
        /* offline or server hiccup: try again next launch */
      });
    }
  }, [isUpdateAvailable, isUpdatePending]);

  if (!isUpdatePending) return null;

  return (
    <View style={styles.bar} accessibilityRole="alert">
      <Text style={styles.text}>An update is ready.</Text>
      <Pressable accessibilityRole="button" onPress={() => Updates.reloadAsync()}>
        <Text style={styles.action}>Restart to apply</Text>
      </Pressable>
    </View>
  );
}
```

**Know what you are running.** When a tester says “it still crashes”, the first question is always which build and which update they have. Put these on a Settings or About screen, and ask for them in every bug report:

**mobile/src/release/releaseInfo.ts**

```
/** Everything support needs to know about THIS install. Show it on the About screen. */
export function getReleaseInfo() {
  return {
    variant: (Constants.expoConfig?.extra as { variant?: string } | undefined)?.variant ?? "unknown",
    version: Application.nativeApplicationVersion ?? "unknown",
    build: Application.nativeBuildVersion ?? "unknown", // build number (iOS) / version code (Android)
    runtimeVersion: Updates.runtimeVersion ?? "none",
    channel: Updates.channel ?? "none",
    updateId: Updates.updateId ?? "embedded", // "embedded" = no update applied yet
    isEmbeddedLaunch: Updates.isEmbeddedLaunch,
  };
}
```

`updateId` reads `embedded` until an update has been applied, which tells you at a glance whether a report is about the store binary or an update layered on top.


## Over-the-Air Updates with Expo Update › Rolling out and rolling back

Expo Update supports two safety nets worth knowing before you need them. A **rollout** delivers an update to a percentage of eligible users first, so you can watch for problems before everyone has it. A **rollback** tells apps to stop using a bad update, either reverting to the previous update or to the JavaScript embedded in the build. Practise both on the preview channel once. A rollback you have never run is a plan you cannot trust at 2 a.m. See Expo’s rollouts and rollbacks pages for the current commands.

> **An update that crashes everyone cannot always rescue itself**
>
> `expo-updates` has some built-in recovery if an update fails during launch, but a bug that appears later, on a particular screen or with particular data, is not caught. The only real protection is the habit: **preview channel, then a staged rollout, then everyone.**


## Safety Nets: The Server-Side Version Gate › Choosing the right tool

| **Problem** | **Reach for** | **Why** |
|---|---|---|
| Typo or logic bug in JavaScript | Update on `preview`, then `production` | Minutes, no review |
| A new update is crashing | Roll back the update | Stops the bleeding without a store release |
| Bug in native code or a missing permission | New build, staged rollout | Only a binary can fix it |
| A new build is crashing | Halt the staged rollout, ship a fix, raise the minimum version | Limits exposure, then retires the bad build |
| API change old apps cannot handle | Raise `MOBILE_MIN_VERSION` | Old installs are told to update |
| Planned backend downtime | `MOBILE_MAINTENANCE=true` | Friendly message, not a wall of errors |

Crash reporting is what tells you which row you are in. Chapter 55 sets up monitoring, and it matters more on mobile than on the web: you cannot open a server log for a phone in someone’s pocket.


## Automating Releases and Checking Them Automatically

Manual releases drift. Someone forgets to bump a version, runs a build with the wrong profile, or points preview at production. Chapter 17 added `manage.py check --deploy` so that unsafe configuration fails loudly. A release deserves the same.


### The release check

`scripts/checkRelease.ts` takes the parsed `eas.json` and the resolved app config for each variant, and returns findings. It is a pure function, so every rule has a test that proves it fires, and the CLI wrapper simply loads the files and sets the exit code. The rules fall into groups:

| **Group** | **What it catches** | **Rule ids** |
|---|---|---|
| Versions | Local version source, `autoIncrement` off | R001, R003 |
| Production profile | Dev client, internal distribution or APK in production; wrong environment | R004 to R007 |
| Channels | Missing production channel; preview and production sharing one | R008 to R010 |
| Secrets | Secret-looking names in committed `env` or `EXPO_PUBLIC_` values | R011, R012 |
| Identity | Placeholder identifiers, bad version, missing runtime version or update URL, placeholder project id | R014 to R021 |
| Variants | Two variants sharing one identifier | R022 |
| Submit and environment | Placeholder App Store id; `http://` or private-network API URL | R023 to R025 |

Here are two representative rules, so you can see how little code a useful check takes:

**mobile/scripts/checkRelease.ts (excerpt)**

```
  // ---- eas.json: channels ----------------------------------------------------
  if (!production.channel) {
    add("R008", "error", "production has no channel: it will never receive over-the-air updates.");
  }
  const preview = build.preview ? resolveProfile(build, "preview") : undefined;
  if (preview && preview.channel && preview.channel === production.channel) {
    add("R009", "error", "preview and production share a channel: a test update would reach real users.");
  }
  if (preview && !preview.channel) {
    add("R010", "warn", "preview has no channel, so testers cannot receive preview updates.");
  }

  // ---- eas.json: committed values are public ---------------------------------
  for (const [name, profile] of Object.entries(build)) {
    for (const key of Object.keys(profile.env ?? {})) {
      if (!SECRET_NAME.test(key)) continue;
      if (key.startsWith("EXPO_PUBLIC_")) {
        add("R012", "error", `${key} would be baked into the app and readable by anyone.`);
      } else {
        add("R011", "error", `build.${name}.env.${key} looks like a secret. eas.json is committed to Git.`);
      }
    }
  }
```

Run it with `npm run release:check`. **On the starter files it is supposed to fail**, with exactly three findings (two errors and one warning): the `com.example` identifier, the all-zero project id from `eas init`, and the placeholder App Store id. A test in the suite pins that behaviour, so if you tidy a rule and change the starter output, the test tells you.


### Putting it in CI

Three GitHub Actions workflows ship with this chapter. They need one secret, `EXPO_TOKEN`, a personal access token created in your Expo account settings:

| **Workflow** | **Trigger** | **What it does** |
|---|---|---|
| `mobile-check.yml` | Pull requests touching `mobile/` | Type-check, run the 50 tests, run the release check with production variables |
| `mobile-update.yml` | Merge to `main` | Publishes a JavaScript update to the **preview** channel only |
| `mobile-release.yml` | Pushing a tag like `v1.1.0` | Checks, then starts store builds. Does **not** submit |

**.github/workflows/mobile-release.yml**

```
jobs:
  build:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: mobile
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: npm
          cache-dependency-path: mobile/package-lock.json
      - run: npm ci
      - run: npm run test:release
      - uses: expo/expo-github-action@v8
        with:
          eas-version: latest
          token: ${{ secrets.EXPO_TOKEN }}
      - run: npm run release:check
        env:
          APP_VARIANT: production
          EXPO_PUBLIC_API_URL: https://api.example.com
      - run: eas build --platform all --profile production --non-interactive --no-wait
```

Two safety choices are visible in that file. `permissions: contents: read` gives the job the least access it needs, the same principle as Chapter 17’s least-privilege database user. And the final step is `--no-wait`, which queues the build and returns, so you are not paying for CI minutes while Expo’s servers work.

Expo also offers its own workflow runner (**Expo Workflows**, files in `.eas/workflows/`), which can build and then submit on Expo’s infrastructure. If you prefer a single vendor, its documentation shows a build-then-submit file you can adopt. GitHub Actions is used here because the check and the tests belong next to your other pull-request checks.

> **Never auto-publish production updates from CI**
>
> A merge that fails a human review should not reach every installed phone. The shipped workflow publishes to `preview` only. Production updates and store submissions stay a deliberate, person-initiated step (or a workflow gated by an approval).
