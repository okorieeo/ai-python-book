import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import { api, onSessionExpired, tokenStore } from "./api";

type Status = "loading" | "signedIn" | "signedOut";
interface AuthValue {
  status: Status;
  signIn(email: string, password: string): Promise<void>;
  signOut(): Promise<void>;
}

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<Status>("loading");

  useEffect(() => {
    void tokenStore.get().then((tokens) => setStatus(tokens ? "signedIn" : "signedOut"));
    return onSessionExpired(() => setStatus("signedOut")); // a refused refresh token signs the user out
  }, []);

  const signIn = useCallback(async (email: string, password: string) => {
    // Adapt the path and the response to your Chapter 13 endpoints.
    const data = await api.post<{ access: string; refresh: string; expires_in?: number }>(
      "/api/v1/auth/login/",
      { email, password },
      { auth: false },
    );
    await tokenStore.set({
      access: data.access,
      refresh: data.refresh,
      accessExpiresAt: data.expires_in ? Date.now() + data.expires_in * 1000 : undefined,
    });
    setStatus("signedIn");
  }, []);

  const signOut = useCallback(async () => {
    await tokenStore.clear();
    setStatus("signedOut");
  }, []);

  const value = useMemo(() => ({ status, signIn, signOut }), [status, signIn, signOut]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}
