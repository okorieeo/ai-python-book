export type Role = "user" | "assistant";

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
}

export interface ConversationWithMessages extends Conversation {
  messages: Message[];
}

export interface Plan {
  code: string;
  name: string;
  priceCents: number; // per month, in the smallest currency unit
  monthlyTokenLimit: number;
  features: string[];
  popular?: boolean;
}
