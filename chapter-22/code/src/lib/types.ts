// Written by hand here; Chapter 20 generates these from the OpenAPI file.
export type Role = "member" | "support" | "admin";
export type Permission = "view_users" | "export_users" | "view_analytics";

export interface Me {
  id: string;
  username: string;
  email: string;
  role: Role;
  permissions: Permission[];
  date_joined: string;
}

export interface Page<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface AdminUser {
  id: string;
  username: string;
  email: string;
  role: Role;
  is_active: boolean;
  date_joined: string;
  last_login: string | null;
  conversation_count: number;
  tokens_30d: number;
}

export interface Overview {
  users_total: number;
  users_new_7d: number;
  tokens_today: number;
  messages_today: number;
  documents_total: number;
}

export interface UsagePoint {
  date: string; // "2026-11-03", a calendar day, not a moment
  input_tokens: number;
  output_tokens: number;
  calls: number;
}

export interface UsageSeries {
  days: number;
  series: UsagePoint[];
}

export interface TopUser {
  username: string;
  tokens: number;
}

export interface StatusCount {
  status: string;
  count: number;
}
