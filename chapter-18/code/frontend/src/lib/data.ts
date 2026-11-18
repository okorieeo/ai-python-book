import "server-only"; // importing this file from a Client Component fails the build

import type { Conversation, ConversationWithMessages, Message } from "./types";

/*
 * A stand-in for the Django API. In Chapter 20 these four functions are
 * replaced by calls to the real backend; nothing that uses them changes.
 */

interface Store {
  conversations: Map<string, ConversationWithMessages>;
  nextMessageId: number;
}

// Keep one store across hot reloads in development.
const globalStore = globalThis as unknown as { __chatStore?: Store };

function createStore(): Store {
  const now = new Date().toISOString();
  const seed = (
    id: string,
    title: string,
    lines: [Message["role"], string][],
  ) => ({
    id,
    title,
    updatedAt: now,
    messages: lines.map(([role, content], i) => ({
      id: i + 1,
      role,
      content,
      createdAt: now,
    })),
  });
  return {
    nextMessageId: 100,
    conversations: new Map([
      [
        "welcome",
        seed("welcome", "Welcome", [
          ["user", "What can you help me with?"],
          [
            "assistant",
            "I can summarize documents, answer questions and draft text.",
          ],
        ]),
      ],
      [
        "invoices",
        seed("invoices", "Invoice questions", [
          ["user", "How do I download last month's invoice?"],
          [
            "assistant",
            "Open Billing, choose the month, then select Download PDF.",
          ],
        ]),
      ],
    ]),
  };
}

const store = (globalStore.__chatStore ??= createStore());

export async function listConversations(): Promise<Conversation[]> {
  return [...store.conversations.values()]
    .map(({ id, title, updatedAt }) => ({ id, title, updatedAt }))
    .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
}

export async function getConversation(
  id: string,
): Promise<ConversationWithMessages | null> {
  return store.conversations.get(id) ?? null;
}

export async function createConversation(
  title?: string,
): Promise<Conversation> {
  const id = crypto.randomUUID();
  const now = new Date().toISOString();
  const conversation = {
    id,
    title: title?.trim() || "New conversation",
    updatedAt: now,
    messages: [],
  };
  store.conversations.set(id, conversation);
  return { id, title: conversation.title, updatedAt: now };
}

export async function addMessage(
  conversationId: string,
  content: string,
): Promise<{ userMessage: Message; assistantMessage: Message } | null> {
  const conversation = store.conversations.get(conversationId);
  if (!conversation) return null;
  const make = (role: Message["role"], text: string): Message => ({
    id: store.nextMessageId++,
    role,
    content: text,
    createdAt: new Date().toISOString(),
  });
  const userMessage = make("user", content);
  const assistantMessage = make("assistant", `Echo: ${content}`); // the "AI"
  conversation.messages.push(userMessage, assistantMessage);
  conversation.updatedAt = assistantMessage.createdAt;
  return { userMessage, assistantMessage };
}
