// Client-side checks are for the USER's benefit (fast feedback). They are not security:
// the server must repeat every check (Chapter 17), because anyone can bypass this code.

export interface FileRules {
  maxBytes: number;
  maxFiles: number;
  types: string[]; // MIME types the browser reports (a hint, easily wrong or empty)
  extensions: string[]; // lower-case, without the dot
}

export const DEFAULT_RULES: FileRules = {
  maxBytes: 10 * 1024 * 1024,
  maxFiles: 5,
  types: [
    "image/png", "image/jpeg", "image/webp", "image/gif",
    "application/pdf", "text/plain", "text/markdown",
  ],
  extensions: ["png", "jpg", "jpeg", "webp", "gif", "pdf", "txt", "md"],
};

export interface FileLike {
  name: string;
  size: number;
  type: string;
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1).replace(/\.0$/, "")} MB`;
}

/** Returns a message for the user, or null when the file is acceptable. */
export function validateFile(file: FileLike, rules: FileRules = DEFAULT_RULES): string | null {
  const dot = file.name.lastIndexOf(".");
  const extension = dot >= 0 ? file.name.slice(dot + 1).toLowerCase() : "";
  if (!rules.extensions.includes(extension)) return "This file type is not supported.";
  if (file.type !== "" && !rules.types.includes(file.type)) {
    return "This file type is not supported.";
  }
  if (file.size === 0) return "This file is empty.";
  if (file.size > rules.maxBytes) {
    return `This file is larger than ${formatBytes(rules.maxBytes)}.`;
  }
  return null;
}

export function validateBatch<T extends FileLike>(
  alreadyAttached: number,
  files: T[],
  rules: FileRules = DEFAULT_RULES,
): { accepted: T[]; rejected: { name: string; reason: string }[] } {
  const accepted: T[] = [];
  const rejected: { name: string; reason: string }[] = [];
  for (const file of files) {
    const problem = validateFile(file, rules);
    if (problem) rejected.push({ name: file.name, reason: problem });
    else if (alreadyAttached + accepted.length >= rules.maxFiles) {
      const reason = `You can attach up to ${rules.maxFiles} files.`;
      rejected.push({ name: file.name, reason });
    } else accepted.push(file);
  }
  return { accepted, rejected };
}

// ------------------------------------------------------------------ state

export interface Attachment {
  localId: string;
  name: string;
  size: number;
  type: string;
  status: "uploading" | "done" | "error";
  progress: number; // 0 to 100
  uploadId?: string; // the server's id, once uploaded
  error?: string;
  previewUrl?: string; // an object URL for images: revoke it when the item is removed
}

export type AttachmentAction =
  | { type: "add"; item: Pick<Attachment, "localId" | "name" | "size" | "type" | "previewUrl"> }
  | { type: "progress"; localId: string; progress: number }
  | { type: "done"; localId: string; uploadId: string }
  | { type: "fail"; localId: string; error: string }
  | { type: "retry"; localId: string }
  | { type: "remove"; localId: string }
  | { type: "clear" };

export function attachmentsReducer(
  state: Attachment[],
  action: AttachmentAction,
): Attachment[] {
  const change = (id: string, patch: Partial<Attachment>) =>
    state.map((a) => (a.localId === id ? { ...a, ...patch } : a));
  switch (action.type) {
    case "add":
      return [...state, { ...action.item, status: "uploading", progress: 0 }];
    case "progress":
      return change(action.localId, { progress: Math.max(0, Math.min(100, action.progress)) });
    case "done":
      return change(action.localId, {
        status: "done", progress: 100, uploadId: action.uploadId, error: undefined,
      });
    case "fail":
      return change(action.localId, { status: "error", error: action.error });
    case "retry":
      return change(action.localId, { status: "uploading", progress: 0, error: undefined });
    case "remove":
      return state.filter((a) => a.localId !== action.localId);
    case "clear":
      return [];
  }
}

export const uploadedIds = (items: Attachment[]): string[] =>
  items.flatMap((a) => (a.status === "done" && a.uploadId ? [a.uploadId] : []));

/** The message may be sent only when nothing is still uploading or failed. */
export const attachmentsReady = (items: Attachment[]): boolean =>
  items.every((a) => a.status === "done");

// ------------------------------------------------------------------ upload

export class UploadError extends Error {
  constructor(message: string, readonly status = 0, readonly cancelled = false) {
    super(message);
  }
}

interface ProgressLike {
  lengthComputable: boolean;
  loaded: number;
  total: number;
}

/** The part of XMLHttpRequest we use. Tests supply a fake. */
export interface XhrLike {
  open(method: string, url: string): void;
  setRequestHeader(name: string, value: string): void;
  send(body: FormData): void;
  abort(): void;
  withCredentials: boolean;
  status: number;
  responseText: string;
  upload: { onprogress: ((e: ProgressLike) => void) | null };
  onload: (() => void) | null;
  onerror: (() => void) | null;
  onabort: (() => void) | null;
}

export interface UploadOptions {
  url: string;
  headers?: Record<string, string>; // for example Authorization (never Content-Type)
  withCredentials?: boolean; // true when authentication uses cookies
  onProgress?: (percent: number) => void;
  signal?: AbortSignal;
}

/** Pull a readable message out of the usual error shapes (DRF "detail", {error:{message}}). */
export function messageFromResponse(text: string): string | null {
  try {
    const body = JSON.parse(text) as {
      error?: { message?: unknown };
      detail?: unknown;
      message?: unknown;
    };
    for (const candidate of [body.error?.message, body.detail, body.message]) {
      if (typeof candidate === "string" && candidate) return candidate;
    }
  } catch {
    /* not JSON */
  }
  return null;
}

/** fetch() cannot report upload progress, so uploads use XMLHttpRequest. */
export function uploadFile(
  file: Blob & { name: string },
  options: UploadOptions,
  createXhr: () => XhrLike = () => new XMLHttpRequest() as unknown as XhrLike,
): Promise<{ id: string }> {
  return new Promise((resolve, reject) => {
    const xhr = createXhr();
    xhr.open("POST", options.url);
    xhr.withCredentials = options.withCredentials ?? false;
    for (const [name, value] of Object.entries(options.headers ?? {})) {
      xhr.setRequestHeader(name, value);
    }

    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) options.onProgress?.(Math.round((e.loaded / e.total) * 100));
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          const body = JSON.parse(xhr.responseText) as { id?: unknown };
          if (typeof body.id === "string" && body.id) return resolve({ id: body.id });
        } catch {
          /* fall through */
        }
        return reject(new UploadError("The server sent an unexpected response.", xhr.status));
      }
      const fallback =
        xhr.status === 413 ? "The file is too large." : `Upload failed (${xhr.status}).`;
      reject(new UploadError(messageFromResponse(xhr.responseText) ?? fallback, xhr.status));
    };
    xhr.onerror = () =>
      reject(new UploadError("Network error. Check your connection and try again."));
    xhr.onabort = () => reject(new UploadError("Upload cancelled.", 0, true));

    if (options.signal) {
      if (options.signal.aborted) return reject(new UploadError("Upload cancelled.", 0, true));
      options.signal.addEventListener("abort", () => xhr.abort(), { once: true });
    }
    const form = new FormData();
    // no Content-Type header: the browser adds the multipart boundary itself
    form.append("file", file, file.name);
    xhr.send(form);
  });
}
