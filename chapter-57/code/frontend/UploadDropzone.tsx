"use client";
import { useRef, useState } from "react";
import { ApiError, uploadDocument } from "./api";

const MAX_MB = 10;   // show the user's plan limit here; the server enforces the real one

export function UploadDropzone({ onUploaded }: { onUploaded: () => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleFiles(files: FileList | null) {
    if (!files?.length) return;
    setError(null);
    setBusy(true);
    try {
      for (const file of Array.from(files)) {
        if (file.size > MAX_MB * 1024 * 1024) throw new Error(`${file.name} is larger than ${MAX_MB} MB.`);
        await uploadDocument(file);
      }
      onUploaded();
    } catch (e) {
      setError(e instanceof ApiError || e instanceof Error ? e.message : "Upload failed.");
    } finally {
      setBusy(false);
      if (input.current) input.current.value = "";
    }
  }

  return (
    <div
      onDragOver={(e) => e.preventDefault()}
      onDrop={(e) => { e.preventDefault(); handleFiles(e.dataTransfer.files); }}
      className="rounded-lg border-2 border-dashed p-6 text-center"
    >
      <p>Drop PDF, Word, .txt or .md files here, or</p>
      <button type="button" disabled={busy} onClick={() => input.current?.click()} className="mt-2 rounded bg-blue-600 px-4 py-2 text-white disabled:opacity-50">
        {busy ? "Uploading..." : "Choose files"}
      </button>
      <input ref={input} type="file" hidden multiple accept=".pdf,.docx,.txt,.md" onChange={(e) => handleFiles(e.target.files)} />
      {error && <p role="alert" className="mt-2 text-red-600">{error}</p>}
    </div>
  );
}
