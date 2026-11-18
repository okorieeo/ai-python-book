export type DocStatus = "uploaded" | "processing" | "ready" | "failed";

export interface DocumentItem {
  id: number;
  title: string;
  original_filename: string;
  size_bytes: number;
  status: DocStatus;
  error_message: string;
  page_count: number;
  chunk_count: number;
  created_at: string;
}

export interface Citation {
  marker: number;
  chunk_id: number;
  document_id: number;
  title: string;          // "Handbook, p. 3"
  page_start: number | null;
  page_end: number | null;
  quotes: string[];       // the exact passages the answer relied on
}

export interface UsageSnapshot {
  plan: string;
  resets_at: string;
  questions: { used: number; limit: number };
  pages: { used: number; limit: number };
}

export type ServerEvent =
  | { type: "token"; text: string }
  | { type: "done"; conversation_id: number; answer: string; citations: Citation[]; grounded: boolean }
  | { type: "error"; code: "limit_exceeded" | "busy" | "failed"; message: string };
