"use client";

import { useState } from "react";
import { useAssistant } from "@app/shared/useAssistant";
import { ChatView } from "./ChatView";

export function AssistantPanel({ socketUrl }: { socketUrl: string }) {
  const { state, connected, sendMessage, decide } = useAssistant(socketUrl);
  const [text, setText] = useState("");
  const waitingForAnswer = state.pending.length > 0;   // the server refuses new messages until the question is answered
  const canSend = connected && !state.busy && !waitingForAnswer && text.trim().length > 0;

  return (
    <section aria-label="Assistant" className="flex h-full flex-col gap-4">
      <div className="flex-1 overflow-y-auto"><ChatView state={state} onDecide={decide} /></div>
      <div className="flex gap-2">
        <input value={text} onChange={(e) => setText(e.target.value)} maxLength={4000} aria-label="Message"
          placeholder={waitingForAnswer ? "Answer the question above first" : "Ask me to plan, add, move or find something"}
          disabled={waitingForAnswer}
          onKeyDown={(e) => { if (e.key === "Enter" && canSend) { sendMessage(text.trim()); setText(""); } }}
          className="flex-1 rounded border px-3 py-2" />
        <button type="button" disabled={!canSend} onClick={() => { sendMessage(text.trim()); setText(""); }}
          className="rounded bg-blue-600 px-4 py-2 text-white disabled:opacity-50">
          Send
        </button>
      </div>
      {!connected && <p className="text-xs text-gray-500">Reconnecting…</p>}
    </section>
  );
}
