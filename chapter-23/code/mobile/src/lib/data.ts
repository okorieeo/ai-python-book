import type { Conversation, ConversationWithMessages, Message } from './types';

/*
 * A stand-in for the Django API, like lib/data.ts in the web app. In Chapter 24
 * these functions call the real backend and nothing that uses them changes.
 */

let latencyMs = 250; // pretend the network is not instant
export function setLatency(ms: number) {
  latencyMs = ms;
}
const wait = () => new Promise<void>((resolve) => setTimeout(resolve, latencyMs));

let nextMessageId = 100;
const store = new Map<string, ConversationWithMessages>();

function seed() {
  store.clear();
  nextMessageId = 100;
  const now = new Date().toISOString();
  const add = (id: string, title: string, lines: [Message['role'], string][]) => {
    const messages = lines.map(([role, content], i) => ({ id: i + 1, role, content, createdAt: now }));
    store.set(id, { id, title, updatedAt: now, lastMessage: messages.at(-1)?.content ?? null, messages });
  };
  add('welcome', 'Welcome', [
    ['user', 'What can you help me with?'],
    ['assistant', 'I can summarize documents, answer questions and draft text.'],
  ]);
  add('invoices', 'Invoice questions', [
    ['user', "How do I download last month's invoice?"],
    ['assistant', 'Open Billing, choose the month, then select Download PDF.'],
  ]);
}
seed();

/** Put the data back to how it started (used by tests). */
export function resetData() {
  seed();
}

const summary = ({ id, title, updatedAt, lastMessage }: ConversationWithMessages): Conversation => ({
  id,
  title,
  updatedAt,
  lastMessage,
});

export async function listConversations(): Promise<Conversation[]> {
  await wait();
  return [...store.values()].map(summary).sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
}

export async function getConversation(id: string): Promise<ConversationWithMessages | null> {
  await wait();
  return store.get(id) ?? null;
}

export async function createConversation(): Promise<Conversation> {
  await wait();
  const id = Math.random().toString(36).slice(2, 10);
  const now = new Date().toISOString();
  const conversation = { id, title: 'New conversation', updatedAt: now, lastMessage: null, messages: [] };
  store.set(id, conversation);
  return summary(conversation);
}

export async function sendMessage(
  conversationId: string,
  content: string,
): Promise<{ userMessage: Message; assistantMessage: Message }> {
  await wait();
  const conversation = store.get(conversationId);
  if (!conversation) throw new Error('Conversation not found');
  const make = (role: Message['role'], text: string): Message => ({
    id: nextMessageId++,
    role,
    content: text,
    createdAt: new Date().toISOString(),
  });
  const userMessage = make('user', content);
  const assistantMessage = make('assistant', `Echo: ${content}`); // the "AI"
  conversation.messages.push(userMessage, assistantMessage);
  conversation.lastMessage = assistantMessage.content;
  conversation.updatedAt = assistantMessage.createdAt;
  return { userMessage, assistantMessage };
}
