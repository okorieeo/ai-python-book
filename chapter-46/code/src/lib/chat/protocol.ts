import { z } from "zod";

// The WebSocket contract with the Channels consumer (Chapter 14). Every frame the
// server sends is parsed against this union before the UI sees it.
export const serverEventSchema = z.discriminatedUnion("type", [
  z.object({ type: z.literal("token"), delta: z.string() }),
  z.object({ type: z.literal("done"), message_id: z.string() }),
  z.object({ type: z.literal("error"), code: z.string(), message: z.string() }),
]);

export type ServerEvent = z.infer<typeof serverEventSchema>;

export type ClientEvent = { type: "user_message"; content: string };

export const MAX_MESSAGE_LENGTH = 4000; // keep in step with the serializer limit (17.11)

export function parseServerEvent(raw: unknown): ServerEvent | null {
  if (typeof raw !== "string") return null;
  let json: unknown;
  try {
    json = JSON.parse(raw);
  } catch {
    return null;
  }
  const parsed = serverEventSchema.safeParse(json);
  return parsed.success ? parsed.data : null;
}
