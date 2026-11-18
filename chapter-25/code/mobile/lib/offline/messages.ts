import type { OutboxItem } from './outbox';

export const SEND_MESSAGE_KIND = 'message.send';

export interface SendMessagePayload {
  content: string;
}

export interface ServerMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  created_at: string;
  client_id?: string | null;
}

export type MessageStatus = 'sent' | 'sending' | 'failed';

export interface ChatMessage {
  /** Stable React key: the client id when we have one, so a message does not remount when the server confirms it. */
  key: string;
  clientId?: string;
  role: ServerMessage['role'];
  content: string;
  createdAt: number;
  status: MessageStatus;
  error?: string;
}

function isSendPayload(value: unknown): value is SendMessagePayload {
  return typeof value === 'object' && value !== null && typeof (value as SendMessagePayload).content === 'string';
}

/**
 * What the chat screen shows: the messages the server has, plus the ones still waiting in the outbox.
 * Rules: the server's copy wins as soon as it exists (matched by client id); waiting messages sit
 * at the bottom in the order they were typed; failed ones stay visible so the user can retry.
 */
export function mergeMessages(
  server: readonly ServerMessage[],
  outbox: readonly OutboxItem[],
  conversationId: string,
): ChatMessage[] {
  const confirmed = new Set<string>();
  for (const m of server) if (m.client_id) confirmed.add(m.client_id);

  const fromServer: ChatMessage[] = server
    .map((m) => ({
      key: m.client_id ?? m.id,
      clientId: m.client_id ?? undefined,
      role: m.role,
      content: m.content,
      createdAt: Date.parse(m.created_at),
      status: 'sent' as const,
    }))
    .sort((a, b) => a.createdAt - b.createdAt);

  const local: ChatMessage[] = outbox
    .filter((i) => i.kind === SEND_MESSAGE_KIND && i.scope === conversationId && !confirmed.has(i.id) && isSendPayload(i.payload))
    .sort((a, b) => a.createdAt - b.createdAt)
    .map((i) => ({
      key: i.id,
      clientId: i.id,
      role: 'user' as const,
      content: (i.payload as SendMessagePayload).content,
      createdAt: i.createdAt,
      status: i.status === 'failed' ? ('failed' as const) : ('sending' as const),
      error: i.lastError,
    }));

  return [...fromServer, ...local];
}
