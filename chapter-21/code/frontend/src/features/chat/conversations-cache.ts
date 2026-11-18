// Pure helpers for optimistic updates of the conversation list in the query cache.
export interface ConversationSummary {
  id: string;
  title: string;
}

export function renameInList<T extends ConversationSummary>(
  list: T[],
  id: string,
  title: string,
): T[] {
  return list.map((c) => (c.id === id ? { ...c, title } : c));
}

export function removeFromList<T extends ConversationSummary>(list: T[], id: string): T[] {
  return list.filter((c) => c.id !== id);
}
