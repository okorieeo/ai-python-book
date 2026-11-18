/** One place that defines every cache key, so invalidating "all conversations" can never miss one. */
export const queryKeys = {
  me: ["me"] as const,
  conversations: {
    all: ["conversations"] as const,
    list: (limit: number) => ["conversations", "list", { limit }] as const,
    detail: (id: string) => ["conversations", "detail", id] as const,
  },
};
