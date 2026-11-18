import { describeTool, type ChatItem, type ChatState, type PendingView } from "@app/shared/assistant-protocol";

type DecideFn = (actionId: string, approve: boolean) => void;

export function ConfirmationCard({ item, onDecide }: { item: PendingView; onDecide: DecideFn }) {
  return (
    <div role="group" aria-label="Confirm action" className="rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm dark:border-amber-700 dark:bg-amber-950">
      <p className="font-medium">Please confirm</p>
      {/* item.summary was written by our server from validated arguments, not by the model. */}
      <p className="mt-1">{item.summary}</p>
      <div className="mt-3 flex gap-2">
        <button type="button" disabled={item.sending} onClick={() => onDecide(item.action_id, true)}
          className="rounded bg-red-600 px-3 py-1.5 text-white disabled:opacity-50">
          Yes, do it
        </button>
        <button type="button" disabled={item.sending} onClick={() => onDecide(item.action_id, false)}
          className="rounded border px-3 py-1.5 disabled:opacity-50">
          No, keep it
        </button>
      </div>
    </div>
  );
}

function Bubble({ item }: { item: ChatItem }) {
  const mine = item.role === "user";
  return (
    <li className={mine ? "flex justify-end" : "flex justify-start"}>
      <div className={`max-w-[85%] rounded-2xl px-4 py-2 text-sm ${mine ? "bg-blue-600 text-white" : "bg-gray-100 dark:bg-gray-800"}`}>
        {item.tools.length > 0 && (
          <ul className="mb-1 flex flex-wrap gap-1 text-xs opacity-70" aria-label="What the assistant is doing">
            {item.tools.map((t, n) => (
              <li key={n}>
                {describeTool(t.tool)}
                {t.state === "running" ? "…" : t.state === "failed" ? " (failed)" : " ✓"}
              </li>
            ))}
          </ul>
        )}
        {/* Plain text only: never dangerouslySetInnerHTML for model output (Chapter 17). */}
        <p className="whitespace-pre-wrap">{item.text}{item.streaming && item.text === "" ? "…" : ""}</p>
      </div>
    </li>
  );
}

export function ChatView({ state, onDecide }: { state: ChatState; onDecide: DecideFn }) {
  return (
    <div className="flex flex-col gap-3">
      <ol role="log" aria-live="polite" aria-label="Conversation" className="flex flex-col gap-2">
        {state.items.map((item) => <Bubble key={item.id} item={item} />)}
      </ol>
      {state.pending.map((p) => <ConfirmationCard key={p.action_id} item={p} onDecide={onDecide} />)}
      {state.error && <p role="alert" className="text-sm text-red-600">{state.error}</p>}
    </div>
  );
}
