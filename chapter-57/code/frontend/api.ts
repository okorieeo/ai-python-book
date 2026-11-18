import type { DocumentItem, UsageSnapshot } from "./types";

const API = process.env.NEXT_PUBLIC_API_URL!;

export class ApiError extends Error {
  constructor(public status: number, message: string, public body?: unknown) {
    super(message);
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API}${path}`, { credentials: "include", ...init });
  if (res.status === 204) return undefined as T;
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(res.status, body.message ?? "Something went wrong.", body);
  return body as T;
}

export const listDocuments = () => request<DocumentItem[]>("/api/documents/");
export const deleteDocument = (id: number) => request<void>(`/api/documents/${id}/`, { method: "DELETE", headers: csrf() });
export const getUsage = () => request<UsageSnapshot>("/api/usage/");

export function uploadDocument(file: File): Promise<DocumentItem> {
  const form = new FormData();
  form.append("file", file);
  return request<DocumentItem>("/api/documents/", { method: "POST", body: form, headers: csrf() });
}

// Django's CSRF token for cookie-based sessions (Chapter 13 / 17): read it from the cookie
function csrf(): Record<string, string> {
  const m = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
  return m ? { "X-CSRFToken": decodeURIComponent(m[1]) } : {};
}
