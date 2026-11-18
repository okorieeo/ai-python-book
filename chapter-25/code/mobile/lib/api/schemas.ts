import { z } from 'zod';
import type { ServerMessage } from '../offline/messages';

/**
 * Check data where it enters the app. A missing field then becomes one clear, catchable error at the
 * boundary, instead of "undefined is not an object" three screens away.
 */
export const MessageSchema = z.object({
  id: z.string(),
  role: z.enum(['user', 'assistant', 'system']),
  content: z.string(),
  created_at: z.string(),
  client_id: z.string().nullish(),
});

/** Adapt to the response shape of your Chapter 12 endpoint (here: DRF pagination with "results"). */
export const MessagePageSchema = z.object({
  results: z.array(MessageSchema),
  next: z.string().nullish(),
});

export function parseMessagePage(data: unknown): { messages: ServerMessage[]; next: string | null } {
  const page = MessagePageSchema.parse(data);
  return { messages: page.results, next: page.next ?? null };
}
