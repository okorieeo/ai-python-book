import type { Metadata } from "next";
import { notFound } from "next/navigation";
import type { components } from "@/lib/api/generated/schema";

type SharedConversation = components["schemas"]["SharedConversation"];

// AC-10: never indexed, and the link is not leaked to other sites through the Referer header.
export const metadata: Metadata = {
  title: "Shared conversation",
  robots: { index: false, follow: false },
  referrer: "no-referrer",
};

async function load(token: string): Promise<SharedConversation | null> {
  const base = process.env.API_INTERNAL_URL ?? "http://localhost:8000";
  const res = await fetch(`${base}/api/v1/public/shared/${encodeURIComponent(token)}/`, {
    cache: "no-store", // AC-10 and AC-5: a revoked link must stop working at once
  });
  if (res.status === 404) return null; // AC-6: unknown, expired and revoked look the same
  if (!res.ok) throw new Error(`Shared conversation request failed (${res.status})`);
  return res.json();
}

export default async function SharedPage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  const convo = await load(token);
  if (!convo) notFound();

  return (
    <main className="mx-auto max-w-2xl p-6">
      <h1 className="text-2xl font-bold">{convo.title}</h1>
      <p className="mt-1 text-sm text-gray-500">
        Shared {new Date(convo.shared_at).toLocaleDateString()} · read-only
      </p>
      <ol className="mt-6 space-y-4">
        {convo.messages.map((m, i) => (
          <li key={i} className={m.role === "user" ? "rounded-lg bg-gray-100 p-3" : "rounded-lg border p-3"}>
            <p className="text-xs font-semibold uppercase text-gray-500">{m.role === "user" ? "Person" : "Assistant"}</p>
            {/* Render as text, never as HTML: model output is untrusted (Chapter 17) */}
            <p className="mt-1 whitespace-pre-wrap">{m.content}</p>
          </li>
        ))}
      </ol>
    </main>
  );
}
