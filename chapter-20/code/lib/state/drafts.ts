export type Draft = { text: string; updatedAt: number };
export type Drafts = Record<string, Draft>;

const MAX_DRAFTS = 20;
const MAX_CHARS = 8000;

/** Save (or delete, when empty) the unsent message for a conversation. Keeps only the most recent drafts. */
export function setDraft(drafts: Drafts, conversationId: string, text: string, now: number, maxDrafts = MAX_DRAFTS): Drafts {
  const next: Drafts = { ...drafts };
  if (text.trim() === "") {
    delete next[conversationId];
    return next;
  }
  next[conversationId] = { text: text.slice(0, MAX_CHARS), updatedAt: now };
  const keep = Object.entries(next).sort((a, b) => b[1].updatedAt - a[1].updatedAt).slice(0, maxDrafts);
  return Object.fromEntries(keep);
}

export function getDraft(drafts: Drafts, conversationId: string): string {
  return drafts[conversationId]?.text ?? "";
}

export function clearDraft(drafts: Drafts, conversationId: string): Drafts {
  const next = { ...drafts };
  delete next[conversationId];
  return next;
}
