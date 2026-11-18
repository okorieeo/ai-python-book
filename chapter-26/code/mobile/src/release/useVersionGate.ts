import * as Application from "expo-application";
import Constants from "expo-constants";
import { useEffect, useState } from "react";
import { Platform } from "react-native";

import { evaluateGate, type AppConfigResponse, type GateState } from "./versionGate";

const API_URL = process.env.EXPO_PUBLIC_API_URL ?? "";

/** Ask the server whether this installed version may run. Fails open on any error. */
export function useVersionGate(): { state: GateState; checked: boolean } {
  const [state, setState] = useState<GateState>({ kind: "ok" });
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    // nativeApplicationVersion is null in some dev setups; fall back to the config value.
    const installed = Application.nativeApplicationVersion ?? Constants.expoConfig?.version ?? "0.0.0";
    const platform = Platform.OS === "ios" ? "ios" : "android";

    (async () => {
      try {
        const res = await fetch(`${API_URL}/api/v1/app-config/?platform=${platform}`, {
          signal: controller.signal,
        });
        if (!res.ok) throw new Error(`app-config ${res.status}`);
        const body = (await res.json()) as AppConfigResponse;
        setState(evaluateGate(body, installed));
      } catch {
        setState({ kind: "ok" }); // unreachable or malformed: never lock people out
      } finally {
        setChecked(true);
      }
    })();

    return () => controller.abort();
  }, []);

  return { state, checked };
}
