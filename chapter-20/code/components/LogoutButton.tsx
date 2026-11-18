"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { logoutRequest } from "@/lib/api/auth";
import { resetUiStore } from "@/lib/state/ui-store";

export function LogoutButton() {
  const queryClient = useQueryClient();
  const [pending, setPending] = useState(false);

  async function onClick() {
    setPending(true);
    await logoutRequest();                 // clears the HttpOnly cookies and revokes the session
    queryClient.clear();                   // forget every cached answer that belonged to this user
    resetUiStore();                        // and their unsent drafts
    window.location.assign("/login");      // a full page load guarantees no stale in-memory state survives
  }

  return <button onClick={onClick} disabled={pending}>{pending ? "Logging out..." : "Log out"}</button>;
}
