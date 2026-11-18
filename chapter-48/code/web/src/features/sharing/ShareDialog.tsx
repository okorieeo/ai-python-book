"use client";

import { useEffect, useState } from "react";
import {
  createShareLink,
  listShareLinks,
  revokeShareLink,
  type ExpiresIn,
  type ShareLink,
} from "@/lib/api/sharing";

const LIFETIMES: { value: ExpiresIn; label: string }[] = [
  { value: "1d", label: "1 day" },
  { value: "7d", label: "7 days" },
  { value: "30d", label: "30 days" },
  { value: "never", label: "Never expires" },
];

export function ShareDialog({ conversationId, onClose }: { conversationId: string; onClose: () => void }) {
  const [expiresIn, setExpiresIn] = useState<ExpiresIn>("7d");
  const [links, setLinks] = useState<ShareLink[]>([]);
  const [newUrl, setNewUrl] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    listShareLinks(conversationId).then(setLinks).catch(() => setError("Could not load your links."));
  }, [conversationId]);

  async function create() {
    setBusy(true);
    setError(null);
    try {
      const created = await createShareLink(conversationId, expiresIn);
      setNewUrl(created.url); // AC-2: this is the only time the url exists
      setCopied(false);
      setLinks(await listShareLinks(conversationId));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not create the link.");
    } finally {
      setBusy(false);
    }
  }

  async function copy() {
    if (!newUrl) return;
    await navigator.clipboard.writeText(newUrl);
    setCopied(true);
  }

  async function revoke(id: string) {
    await revokeShareLink(conversationId, id);
    setLinks(await listShareLinks(conversationId));
  }

  return (
    <div role="dialog" aria-modal="true" aria-labelledby="share-title" className="rounded-xl bg-white p-6 shadow-xl">
      <h2 id="share-title" className="text-lg font-semibold">Share this conversation</h2>
      <p className="mt-1 text-sm text-gray-600">
        Anyone with the link can read this conversation up to now. They cannot see anything you write later.
      </p>

      <label className="mt-4 block text-sm font-medium" htmlFor="lifetime">Link works for</label>
      <select id="lifetime" value={expiresIn} onChange={(e) => setExpiresIn(e.target.value as ExpiresIn)}
              className="mt-1 w-full rounded border p-2">
        {LIFETIMES.map((l) => <option key={l.value} value={l.value}>{l.label}</option>)}
      </select>

      <button onClick={create} disabled={busy} className="mt-4 rounded bg-blue-700 px-4 py-2 text-white disabled:opacity-50">
        {busy ? "Creating…" : "Create link"}
      </button>

      {error && <p role="alert" className="mt-3 text-sm text-red-700">{error}</p>}

      {newUrl && (
        <div className="mt-4 rounded border border-green-200 bg-green-50 p-3">
          <input readOnly aria-label="Share link" value={newUrl} className="w-full rounded border p-2 text-sm" />
          <button onClick={copy} className="mt-2 rounded border px-3 py-1 text-sm">{copied ? "Copied" : "Copy link"}</button>
          <p className="mt-2 text-xs text-gray-600">Copy it now. For safety, this link is not shown again.</p>
        </div>
      )}

      <h3 className="mt-6 text-sm font-semibold">Your links</h3>
      <ul className="mt-2 space-y-2">
        {links.length === 0 && <li className="text-sm text-gray-500">No links yet.</li>}
        {links.map((l) => (
          <li key={l.id} className="flex items-center justify-between rounded border p-2 text-sm">
            <span>
              {l.state} · {l.view_count} {l.view_count === 1 ? "view" : "views"}
              {l.expires_at ? ` · until ${new Date(l.expires_at).toLocaleDateString()}` : " · no expiry"}
            </span>
            {l.state === "active" && (
              <button onClick={() => revoke(l.id)} className="text-red-700 underline">Revoke</button>
            )}
          </li>
        ))}
      </ul>

      <button onClick={onClose} className="mt-6 text-sm underline">Close</button>
    </div>
  );
}
