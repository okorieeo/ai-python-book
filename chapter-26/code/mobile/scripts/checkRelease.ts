/**
 * Release configuration checks. Pure functions: give them the parsed eas.json,
 * the resolved app config for each variant and (optionally) the environment,
 * and they return a list of findings. The CLI wrapper is release-check.ts.
 *
 * Like `manage.py check --deploy` in Chapter 17, this turns "I forgot" into
 * a failed pipeline instead of a rejected build or a broken release.
 */

export type Severity = "error" | "warn";

export interface Finding {
  id: string;
  severity: Severity;
  message: string;
}

/** Only the parts of eas.json we look at, loosely typed on purpose. */
export interface EasJson {
  cli?: { appVersionSource?: string; version?: string };
  build?: Record<string, BuildProfile>;
  submit?: Record<string, { ios?: { ascAppId?: string }; android?: { track?: string } }>;
}
export interface BuildProfile {
  extends?: string;
  developmentClient?: boolean;
  distribution?: string;
  channel?: string;
  environment?: string;
  autoIncrement?: boolean | string;
  env?: Record<string, string>;
  android?: { buildType?: string };
}

/** The parts of the resolved Expo config we look at. */
export interface AppConfigLike {
  version?: string;
  runtimeVersion?: unknown;
  updates?: { url?: string };
  ios?: { bundleIdentifier?: string; infoPlist?: Record<string, unknown> };
  android?: { package?: string };
  extra?: { eas?: { projectId?: string } };
}

export interface CheckInput {
  eas: EasJson;
  /** Resolved app config per variant name: development, preview, production. */
  appConfigs: Record<string, AppConfigLike>;
  /** process.env, or a stand-in. Only EXPO_PUBLIC_API_URL is read from it. */
  env?: Record<string, string | undefined>;
}

const SECRET_NAME = /(SECRET|TOKEN|PASSWORD|PRIVATE|API_?KEY|CREDENTIAL)/i;
const SEMVER = /^\d+\.\d+\.\d+$/;
const ZERO_UUID = "00000000-0000-0000-0000-000000000000";

/** Follow `extends` so a profile that inherits settings is judged on its real values. */
export function resolveProfile(
  build: Record<string, BuildProfile>,
  name: string,
  seen: string[] = [],
): BuildProfile {
  const profile = build[name];
  if (!profile) return {};
  if (seen.includes(name)) return profile; // circular: stop (EAS rejects it anyway)
  const parent = profile.extends ? resolveProfile(build, profile.extends, [...seen, name]) : {};
  return { ...parent, ...profile, android: { ...parent.android, ...profile.android } };
}

export function checkRelease(input: CheckInput): Finding[] {
  const out: Finding[] = [];
  const add = (id: string, severity: Severity, message: string) =>
    out.push({ id, severity, message });

  const { eas, appConfigs } = input;
  const env = input.env ?? {};
  const build = eas.build ?? {};

  // ---- eas.json: versions --------------------------------------------------
  if (eas.cli?.appVersionSource !== "remote") {
    add("R001", "error", 'cli.appVersionSource should be "remote" so build numbers never collide.');
  }
  if (!build.production) {
    add("R002", "error", 'There is no "production" build profile.');
    return out; // nothing more to say about production
  }
  const production = resolveProfile(build, "production");
  if (!production.autoIncrement) {
    add("R003", "error", "production.autoIncrement is off: the stores reject a repeated build number.");
  }

  // ---- eas.json: what production must not be ---------------------------------
  if (production.developmentClient) {
    add("R004", "error", "production builds must not use developmentClient.");
  }
  if (production.distribution === "internal") {
    add("R005", "error", 'production distribution is "internal": that cannot go to the stores.');
  }
  if (production.android?.buildType === "apk") {
    add("R006", "error", "production builds an APK; Google Play needs an app bundle (aab).");
  }
  if (production.environment !== "production") {
    add("R007", "error", 'production.environment should be "production" so it uses production variables.');
  }

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

  // ---- app config: identity --------------------------------------------------
  const prod = appConfigs.production;
  if (!prod) {
    add("R013", "error", "Could not resolve the production app config.");
  } else {
    const ios = prod.ios?.bundleIdentifier;
    const android = prod.android?.package;
    if (!ios || !android) {
      add("R014", "error", "The production config needs ios.bundleIdentifier and android.package.");
    } else if (ios !== android) {
      add("R015", "warn", `iOS (${ios}) and Android (${android}) identifiers differ. Allowed, but easy to mix up.`);
    }
    for (const id of new Set([ios, android])) {
      if (id && id.startsWith("com.example")) {
        add("R016", "error", `Identifier "${id}" is a placeholder. Choose your own; it cannot change after release.`);
      }
    }
    if (!prod.version || !SEMVER.test(prod.version)) {
      add("R017", "error", `version "${prod.version}" must look like 1.0.0 (three numbers).`);
    }
    if (!prod.runtimeVersion) {
      add("R018", "error", "runtimeVersion is missing: updates cannot be matched to compatible builds.");
    }
    const url = prod.updates?.url ?? "";
    if (!url.startsWith("https://u.expo.dev/")) {
      add("R019", "error", "updates.url is missing or does not point at https://u.expo.dev/<project id>.");
    }
    const projectId = prod.extra?.eas?.projectId;
    if (!projectId || projectId === ZERO_UUID) {
      add("R020", "error", "extra.eas.projectId is a placeholder. Run `eas init` to create the project.");
    }
    if (typeof prod.ios?.infoPlist?.ITSAppUsesNonExemptEncryption !== "boolean") {
      add("R021", "warn", "ITSAppUsesNonExemptEncryption is not set: App Store Connect will ask on every upload.");
    }
  }

  // ---- app config: variants must not collide ---------------------------------
  const seen = new Map<string, string>();
  for (const [name, config] of Object.entries(appConfigs)) {
    for (const id of [config.ios?.bundleIdentifier, config.android?.package]) {
      if (!id) continue;
      const other = seen.get(id);
      if (other && other !== name) {
        add("R022", "error", `Variants "${other}" and "${name}" share identifier ${id}; they cannot be installed side by side.`);
      }
      seen.set(id, name);
    }
  }

  // ---- submit ----------------------------------------------------------------
  const ascAppId = eas.submit?.production?.ios?.ascAppId ?? "";
  if (!/^\d{6,}$/.test(ascAppId)) {
    add("R023", "warn", "submit.production.ios.ascAppId is not a number yet. Fill it in after creating the app in App Store Connect.");
  }

  // ---- environment -----------------------------------------------------------
  const apiUrl = env.EXPO_PUBLIC_API_URL;
  if (apiUrl !== undefined && apiUrl !== "") {
    if (!apiUrl.startsWith("https://")) {
      add("R024", "error", "EXPO_PUBLIC_API_URL must use https for a release build.");
    } else if (/\/\/(localhost|127\.|10\.|192\.168\.)/.test(apiUrl)) {
      add("R025", "error", "EXPO_PUBLIC_API_URL points at your own machine or network.");
    }
  }

  return out;
}

export function hasErrors(findings: Finding[]): boolean {
  return findings.some((f) => f.severity === "error");
}
