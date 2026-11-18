"use client";

import { useEffect, useReducer, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { UPLOAD_URL, uploadAuth } from "../api";
import {
  attachmentsReady, attachmentsReducer, uploadedIds, uploadFile, validateBatch,
  type Attachment,
} from "../attachments";
import { AttachmentTray } from "./small-ui";

export const MAX_MESSAGE_CHARS = 8000; // keep equal to the server's limit (Chapter 17)

interface Props {
  connected: boolean;
  generating: boolean;
  onSend: (text: string, attachmentIds: string[]) => void;
  onStop: () => void;
}

export function Composer({ connected, generating, onSend, onStop }: Props) {
  const [text, setText] = useState("");
  const [items, dispatch] = useReducer(attachmentsReducer, [] as Attachment[]);
  const [problems, setProblems] = useState<string[]>([]);
  const [dragging, setDragging] = useState(false);
  const textarea = useRef<HTMLTextAreaElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const uploads = useRef(new Map<string, { file: File; abort: AbortController }>());
  const latest = useRef(items);
  latest.current = items;

  const canSend =
    connected && !generating && text.trim().length > 0 &&
    text.length <= MAX_MESSAGE_CHARS && attachmentsReady(items);

  // Grow the box with its content, up to a limit.
  useEffect(() => {
    const el = textarea.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [text]);

  // On unmount: cancel running uploads and free preview memory.
  useEffect(() => {
    const running = uploads.current;
    return () => {
      running.forEach(({ abort }) => abort.abort());
      latest.current.forEach((a) => a.previewUrl && URL.revokeObjectURL(a.previewUrl));
    };
  }, []);

  async function startUpload(localId: string, file: File) {
    const abort = new AbortController();
    uploads.current.set(localId, { file, abort });
    try {
      const auth = await uploadAuth();
      const { id } = await uploadFile(file, {
        url: UPLOAD_URL, ...auth, signal: abort.signal,
        onProgress: (progress) => dispatch({ type: "progress", localId, progress }),
      });
      dispatch({ type: "done", localId, uploadId: id });
    } catch (error) {
      const cancelled = (error as { cancelled?: boolean }).cancelled === true;
      if (!cancelled) dispatch({ type: "fail", localId, error: (error as Error).message });
    }
  }

  function addFiles(files: File[]) {
    const { accepted, rejected } = validateBatch(items.length, files);
    setProblems(rejected.map((r) => `${r.name}: ${r.reason}`));
    for (const file of accepted) {
      const localId = crypto.randomUUID();
      const previewUrl = file.type.startsWith("image/") ? URL.createObjectURL(file) : undefined;
      const { name, size, type } = file;
      dispatch({ type: "add", item: { localId, name, size, type, previewUrl } });
      void startUpload(localId, file);
    }
  }

  function removeFile(localId: string) {
    uploads.current.get(localId)?.abort.abort();
    uploads.current.delete(localId);
    const item = items.find((a) => a.localId === localId);
    if (item?.previewUrl) URL.revokeObjectURL(item.previewUrl);
    dispatch({ type: "remove", localId });
  }

  function retryFile(localId: string) {
    const entry = uploads.current.get(localId);
    if (!entry) return;
    dispatch({ type: "retry", localId });
    void startUpload(localId, entry.file);
  }

  function submit() {
    if (!canSend) return;
    onSend(text.trim(), uploadedIds(items));
    items.forEach((a) => a.previewUrl && URL.revokeObjectURL(a.previewUrl));
    uploads.current.clear();
    dispatch({ type: "clear" });
    setText("");
    setProblems([]);
    textarea.current?.focus();
  }

  return (
    <form
      onSubmit={(e) => { e.preventDefault(); submit(); }}
      onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        addFiles(Array.from(e.dataTransfer.files));
      }}
      className="mx-auto w-full max-w-3xl px-4 pb-4"
    >
      <div
        className={`rounded-2xl border bg-background ${dragging ? "ring-2 ring-primary" : ""}`}
      >
        <AttachmentTray items={items} onRemove={removeFile} onRetry={retryFile} />
        <label htmlFor="chat-input" className="sr-only">Message</label>
        <textarea
          id="chat-input"
          ref={textarea}
          rows={1}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            // Enter sends, Shift+Enter makes a new line. While an input method (Japanese,
            // Chinese, Korean...) is composing, Enter confirms the text and must NOT send.
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              submit();
            }
          }}
          onPaste={(e) => {
            const files = Array.from(e.clipboardData.files);
            if (files.length > 0) {
              e.preventDefault(); // pasted text still pastes normally
              addFiles(files);
            }
          }}
          placeholder="Message the assistant"
          className={
            "block max-h-[200px] w-full resize-none bg-transparent " +
            "px-4 py-3 outline-none"
          }
        />
        <div className="flex items-center justify-between px-2 pb-2">
          <div className="flex items-center gap-2">
            <input
              ref={fileInput}
              type="file"
              multiple
              hidden
              onChange={(e) => {
                addFiles(Array.from(e.target.files ?? []));
                e.target.value = ""; // so choosing the same file again still fires onChange
              }}
            />
            <Button
              type="button" variant="ghost" size="sm"
              onClick={() => fileInput.current?.click()}
            >
              Attach
            </Button>
            {text.length > MAX_MESSAGE_CHARS * 0.9 && (
              <span
                className={`text-xs ${
                  text.length > MAX_MESSAGE_CHARS ? "text-destructive" : "text-muted-foreground"
                }`}
              >
                {text.length} / {MAX_MESSAGE_CHARS}
              </span>
            )}
          </div>
          {generating ? (
            <Button
              type="button" variant="outline" size="sm" onClick={onStop}
              aria-label="Stop generating"
            >
              Stop
            </Button>
          ) : (
            <Button type="submit" size="sm" disabled={!canSend}>
              Send
            </Button>
          )}
        </div>
      </div>
      {problems.length > 0 && (
        <ul role="alert" className="mt-2 space-y-0.5 text-sm text-destructive">
          {problems.map((p) => <li key={p}>{p}</li>)}
        </ul>
      )}
    </form>
  );
}
