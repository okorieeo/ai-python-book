"use client";

import { useRouter } from "next/navigation";
import { login } from "@/lib/auth/login";
import { LoginForm } from "./LoginForm";

export function LoginScreen() {
  const router = useRouter();
  return (
    <main className="flex min-h-dvh flex-col items-center justify-center gap-6 p-6">
      <h1 className="text-2xl font-semibold">Sign in</h1>
      <LoginForm onLogin={login} onSuccess={() => router.push("/chat")} />
    </main>
  );
}
