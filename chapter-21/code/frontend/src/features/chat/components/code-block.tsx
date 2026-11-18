"use client";

import { useEffect, useState } from "react";
import { highlight } from "../highlight";

export function CodeBlock({ code, language }: { code: string; language?: string }) {
  const [html, setHtml] = useState<string | null>(null);
  const [copy, setCopy] = useState<"idle" | "copied" | "failed">("idle");

  // Highlight shortly after the text stops changing, so a streaming block is not
  // re-highlighted on every frame. A stale result is discarded.
  useEffect(() => {
    let cancelled = false;
    const timer = setTimeout(() => {
      highlight(code, language)
        .then((result) => !cancelled && setHtml(result))
        .catch(() => undefined); // on failure we simply keep the plain text
    }, 150);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [code, language]);

  useEffect(() => {
    if (copy === "idle") return;
    const timer = setTimeout(() => setCopy("idle"), 2000);
    return () => clearTimeout(timer);
  }, [copy]);

  async function copyCode() {
    try {
      await navigator.clipboard.writeText(code); // needs https or localhost
      setCopy("copied");
    } catch {
      setCopy("failed");
    }
  }

  return (
    <div className="my-3 overflow-hidden rounded-lg border bg-muted/40">
      <div className="flex items-center justify-between border-b px-3 py-1.5 text-xs">
        <span className="font-mono text-muted-foreground">{language ?? "text"}</span>
        <button
          type="button"
          onClick={copyCode}
          className="rounded px-2 py-0.5 hover:bg-muted focus-visible:ring-2"
        >
          {copy === "copied" ? "Copied" : copy === "failed" ? "Copy failed" : "Copy"}
          <span className="sr-only"> code</span>
        </button>
      </div>
      {html ? (
        // Safe: Shiki HTML-escapes the code it highlights. We never pass it model text as HTML.
        <div
          className="overflow-x-auto p-3 text-sm [&_pre]:bg-transparent!"
          dangerouslySetInnerHTML={{ __html: html }}
        />
      ) : (
        <pre className="overflow-x-auto p-3 text-sm">
          <code>{code}</code>
        </pre>
      )}
    </div>
  );
}
