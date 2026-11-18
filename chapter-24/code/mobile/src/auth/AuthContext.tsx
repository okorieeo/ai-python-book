import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { api, client, deviceRegistrar, onSignedOut, store } from "../api";
import { NetworkError } from "../api/errors";
import type { User } from "../api/types";

type AuthState =
  | { status: "loading" } // reading the Keychain: keep the splash screen up
  | { status: "signedOut" }
  | { status: "offline" } // we have a session but could not reach the server
  | { status: "signedIn"; user: User };

interface AuthValue {
  state: AuthState;
  signIn(email: string, password: string): Promise<void>;
  signUp(email: string, name: string, password: string): Promise<void>;
  signOut(): Promise<void>;
  setUser(user: User): void;
  retry(): void;
}

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({ status: "loading" });

  const restore = useCallback(async () => {
    setState({ status: "loading" });
    try {
      if (!(await client.restoreSession())) return setState({ status: "signedOut" });
      setState({ status: "signedIn", user: await api.me() });
    } catch (e) {
      // Offline at launch is not the same as signed out.
      setState(e instanceof NetworkError ? { status: "offline" } : { status: "signedOut" });
    }
  }, []);

  useEffect(() => {
    onSignedOut(() => setState({ status: "signedOut" })); // the client reports a dead session
    void restore();
  }, [restore]);

  const value = useMemo<AuthValue>(
    () => ({
      state,
      retry: () => void restore(),
      setUser: (user) => setState({ status: "signedIn", user }),
      async signIn(email, password) {
        const user = await api.login(email.trim().toLowerCase(), password);
        setState({ status: "signedIn", user });
      },
      async signUp(email, name, password) {
        await api.register(email.trim().toLowerCase(), name.trim(), password);
        const user = await api.login(email.trim().toLowerCase(), password);
        setState({ status: "signedIn", user });
      },
      async signOut() {
        // Order matters: stop pushes while our token still works, then revoke it.
        await deviceRegistrar.unregister().catch(() => {});
        await api.logout().catch(() => {});
        await store.clear();
        setState({ status: "signedOut" });
      },
    }),
    [state, restore],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside <AuthProvider>");
  return value;
}

/** For screens that only exist while signed in. */
export function useUser(): User {
  const { state } = useAuth();
  if (state.status !== "signedIn") throw new Error("useUser called while signed out");
  return state.user;
}
