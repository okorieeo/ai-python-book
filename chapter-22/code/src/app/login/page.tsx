"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { ApiError, apiGet, apiPost } from "@/lib/api";
import { setAccessToken } from "@/lib/auth";
import { homeFor } from "@/lib/permissions";
import type { Me } from "@/lib/types";
import { ui } from "@/lib/ui";

// A development login. Chapter 20 replaces it with the real authentication flow.
export default function LoginPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setError(null);
    try {
      const tokens = await apiPost<{ access: string }>("/auth/login", {
        username: form.get("username"),
        password: form.get("password"),
      });
      setAccessToken(tokens.access);
      const me = await queryClient.fetchQuery({
        queryKey: ["me"],
        queryFn: () => apiGet<Me>("/me"),
      });
      router.replace(homeFor(me) ?? "/admin");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }

  const field = `${ui.field} mt-1 w-full py-2`;
  return (
    <main className={`${ui.card} mx-auto mt-24 max-w-sm p-6`}>
      <h1 className="mb-4 text-xl font-semibold">Sign in</h1>
      <form onSubmit={submit} className="space-y-3">
        <label className="block text-sm">
          Username
          <input
            name="username"
            required
            autoComplete="username"
            className={field}
          />
        </label>
        <label className="block text-sm">
          Password
          <input
            name="password"
            type="password"
            required
            autoComplete="current-password"
            className={field}
          />
        </label>
        {error && (
          <p role="alert" className="text-sm text-red-600">
            {error}
          </p>
        )}
        <button disabled={busy} className={`${ui.primary} w-full py-2`}>
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </main>
  );
}
