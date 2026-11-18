import type { User } from "./types";
import { errorFromResponse } from "./errors";
import type { LoginValues } from "../forms/schemas";

/** Browser-side calls to OUR Next.js auth handlers. The browser never sees a token. */
export async function loginRequest(values: LoginValues, fetchFn: typeof fetch = (i, n) => fetch(i, n)): Promise<User> {
  const response = await fetchFn("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(values),
    credentials: "same-origin",
  });
  if (!response.ok) throw await errorFromResponse(response);
  return ((await response.json()) as { user: User }).user;
}

export async function logoutRequest(fetchFn: typeof fetch = (i, n) => fetch(i, n)): Promise<void> {
  await fetchFn("/api/auth/logout", { method: "POST", credentials: "same-origin" });
}
