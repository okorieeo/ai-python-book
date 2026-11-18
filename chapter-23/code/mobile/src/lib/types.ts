export type Role = 'user' | 'assistant';

export interface Message {
  id: number;
  role: Role;
  content: string;
  createdAt: string;
}

export interface Conversation {
  id: string;
  title: string;
  updatedAt: string;
  lastMessage: string | null;
}

export interface ConversationWithMessages extends Conversation {
  messages: Message[];
}
