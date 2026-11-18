import type { ConnectionStatus } from "@/lib/realtime/socket";
import { formatBytes, type Attachment } from "../attachments";
import type { LiveConversation } from "../chat-state";

export function TypingIndicator() {
  return (
    <div role="status" className="flex items-center gap-1 py-2 text-muted-foreground">
      <span className="sr-only">The assistant is thinking</span>
      {[0, 150, 300].map((delay) => (
        <span
          key={delay}
          aria-hidden="true"
          style={{ animationDelay: `${delay}ms` }}
          className="size-2 rounded-full bg-current motion-safe:animate-pulse"
        />
      ))}
    </div>
  );
}

export function ConnectionBanner({
  status,
  onRetry,
}: {
  status: ConnectionStatus;
  onRetry: () => void;
}) {
  if (status !== "reconnecting" && status !== "closed") return null;
  const closed = status === "closed";
  return (
    <div
      role="status"
      className={
        "flex items-center justify-between gap-3 border-b bg-amber-50 px-4 py-2 " +
        "text-sm text-amber-900 dark:bg-amber-950 dark:text-amber-100"
      }
    >
      <span>
        {closed
          ? "You are disconnected."
          : "Connection lost. Reconnecting... You can keep typing."}
      </span>
      <button type="button" onClick={onRetry} className="font-medium underline">
        {closed ? "Reconnect" : "Retry now"}
      </button>
    </div>
  );
}

export function ErrorNotice({
  error,
  onDismiss,
}: {
  error: NonNullable<LiveConversation["error"]>;
  onDismiss: () => void;
}) {
  return (
    <div
      role="alert"
      className={
        "mx-4 mb-2 flex items-start justify-between gap-3 rounded-md border " +
        "border-destructive/40 bg-destructive/10 px-3 py-2 text-sm"
      }
    >
      <span>
        {error.message}
        {error.retryAfter ? ` Try again in ${Math.ceil(error.retryAfter)} seconds.` : ""}
      </span>
      <button type="button" onClick={onDismiss} className="font-medium underline">
        Dismiss
      </button>
    </div>
  );
}

export function AttachmentTray({
  items,
  onRemove,
  onRetry,
}: {
  items: Attachment[];
  onRemove: (localId: string) => void;
  onRetry: (localId: string) => void;
}) {
  if (items.length === 0) return null;
  return (
    <ul className="flex flex-wrap gap-2 px-3 pt-3" aria-label="Attached files">
      {items.map((a) => (
        <li
          key={a.localId}
          className="flex w-52 items-center gap-2 rounded-md border bg-background p-2 text-xs"
        >
          {a.previewUrl ? (
            // eslint-disable-next-line @next/next/no-img-element -- local object URL
            <img src={a.previewUrl} alt="" className="size-9 rounded object-cover" />
          ) : (
            <span
              aria-hidden="true"
              className="grid size-9 place-items-center rounded bg-muted"
            >
              {a.name.split(".").pop()?.slice(0, 4).toUpperCase()}
            </span>
          )}
          <span className="min-w-0 flex-1">
            <span className="block truncate font-medium">{a.name}</span>
            {a.status === "uploading" ? (
              <progress
                value={a.progress}
                max={100}
                aria-label={`Uploading ${a.name}`}
                className="h-1 w-full"
              />
            ) : a.status === "error" ? (
              <span className="block truncate text-destructive" title={a.error}>
                {a.error}{" "}
                <button type="button" className="underline" onClick={() => onRetry(a.localId)}>
                  Retry
                </button>
              </span>
            ) : (
              <span className="text-muted-foreground">{formatBytes(a.size)}</span>
            )}
          </span>
          <button
            type="button"
            onClick={() => onRemove(a.localId)}
            aria-label={`Remove ${a.name}`}
            className="rounded px-1.5 py-0.5 hover:bg-muted"
          >
            x
          </button>
        </li>
      ))}
    </ul>
  );
}
