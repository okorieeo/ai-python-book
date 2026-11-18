import { z } from "zod";

// The wire format lives in ONE file. If the backend changes, only this file changes.

const id = z.string().min(1);

const messageSchema = z.object({
  id,
  role: z.enum(["user", "assistant"]),
  content: z.string(),
  created_at: z.string(),
});

export const serverEventSchema = z.discriminatedUnion("type", [
  z.object({
    type: z.literal("message.accepted"),
    conversation_id: id,
    client_id: id,
    message: messageSchema,
  }),
  z.object({
    type: z.literal("assistant.start"),
    conversation_id: id,
    message_id: id,
    created_at: z.string().optional(),
  }),
  z.object({
    type: z.literal("assistant.delta"),
    message_id: id,
    delta: z.string(),
  }),
  z.object({
    type: z.literal("assistant.end"),
    message_id: id,
    finish_reason: z.enum(["stop", "length", "stopped", "error"]),
    usage: z
      .object({ input_tokens: z.number(), output_tokens: z.number() })
      .optional(),
  }),
  z.object({
    type: z.literal("error"),
    code: z.string(),
    message: z.string(),
    conversation_id: id.optional(),
    client_id: id.optional(),
    retry_after: z.number().optional(),
  }),
  z.object({ type: z.literal("pong") }),
]);

export type ServerEvent = z.infer<typeof serverEventSchema>;

export type ClientCommand =
  | {
      type: "message.send";
      conversation_id: string;
      client_id: string;
      content: string;
      attachment_ids?: string[];
    }
  | { type: "generation.stop"; conversation_id: string }
  | { type: "ping" };

/** Turn raw socket data into a typed event, or null if it is not one we understand. */
export function parseServerEvent(raw: unknown): ServerEvent | null {
  if (typeof raw !== "string") return null;
  let data: unknown;
  try {
    data = JSON.parse(raw);
  } catch {
    return null;
  }
  const result = serverEventSchema.safeParse(data);
  return result.success ? result.data : null;
}

export function encodeCommand(command: ClientCommand): string {
  return JSON.stringify(command);
}
