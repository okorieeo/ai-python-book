"use client";
import { useEffect, useRef, useState } from "react";
import type { Citation, ServerEvent } from "./types";

const WS_URL = process.env.NEXT_PUBLIC_WS_URL!;   // wss://api.example.com (baked in at build time: Chapter 54)

type Turn = { question: string; answer: string; citations: Citation[]; grounded: boolean; done: boolean; error?: string };

export function AskPanel({ documentIds }: { documentIds?: number[] }) {
  const socket = useRef<WebSocket | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [question, setQuestion] = useState("");
  const [conversationId, setConversationId] = useState<number | null>(null);
  const [open, setOpen] = useState<Citation | null>(null);

  useEffect(() => {
    const ws = new WebSocket(`${WS_URL}/ws/ask/`);          // the session cookie authenticates the socket
    socket.current = ws;
    ws.onmessage = (msg) => {
      const ev: ServerEvent = JSON.parse(msg.data);
      if (ev.type === "done") setConversationId(ev.conversation_id);
      setTurns((prev) => {
        if (prev.length === 0) return prev;
        const turns = [...prev];
        const last = { ...turns[turns.length - 1] };
        if (ev.type === "token") last.answer += ev.text;
        if (ev.type === "done") Object.assign(last, { answer: ev.answer, citations: ev.citations, grounded: ev.grounded, done: true });
        if (ev.type === "error") Object.assign(last, { error: ev.message, done: true });
        turns[turns.length - 1] = last;
        return turns;
      });
    };
    return () => ws.close();
  }, []);

  function ask() {
    const q = question.trim();
    if (q.length < 3 || socket.current?.readyState !== WebSocket.OPEN) return;
    setTurns((t) => [...t, { question: q, answer: "", citations: [], grounded: false, done: false }]);
    socket.current.send(JSON.stringify({ type: "ask", question: q, conversation_id: conversationId, document_ids: documentIds }));
    setQuestion("");
  }

  const streaming = turns.length > 0 && !turns[turns.length - 1].done;

  return (
    <section>
      {turns.map((t, i) => (
        <article key={i} className="mb-6">
          <p className="font-semibold">{t.question}</p>
          {/* React escapes text: never render the answer with dangerouslySetInnerHTML */}
          <p className="whitespace-pre-wrap">{t.answer || (t.done ? "" : "Searching your documents...")}</p>
          {t.error && <p role="alert" className="text-red-600">{t.error}</p>}
          {t.done && !t.error && !t.grounded && !t.answer.startsWith("I couldn't find") && (
            <p className="text-amber-700">No supporting passage was found for this answer. Treat it with caution.</p>
          )}
          <div className="mt-2 flex flex-wrap gap-2">
            {t.citations.map((c) => (
              <button key={c.marker} onClick={() => setOpen(c)} className="rounded-full border px-3 py-1 text-sm">
                [{c.marker}] {c.title}
              </button>
            ))}
          </div>
        </article>
      ))}
      {open && (
        <aside role="dialog" aria-label="Source passage" className="rounded border bg-gray-50 p-4">
          <h3 className="font-semibold">{open.title}</h3>
          {open.quotes.map((q, i) => <blockquote key={i} className="my-2 border-l-4 pl-3">{q}</blockquote>)}
          <button onClick={() => setOpen(null)}>Close</button>
        </aside>
      )}
      <form onSubmit={(e) => { e.preventDefault(); ask(); }} className="mt-4 flex gap-2">
        <input value={question} onChange={(e) => setQuestion(e.target.value)} maxLength={2000} placeholder="Ask about your documents" className="flex-1 rounded border px-3 py-2" />
        {streaming
          ? <button type="button" onClick={() => socket.current?.send(JSON.stringify({ type: "stop" }))}>Stop</button>
          : <button type="submit" className="rounded bg-blue-600 px-4 py-2 text-white">Ask</button>}
      </form>
    </section>
  );
}
