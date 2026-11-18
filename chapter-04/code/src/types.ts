export type Priority = "low" | "medium" | "high";

export interface Task {
  id: number;
  title: string;
  priority: Priority;
  done: boolean;
  createdAt: string;
}

// Shape of the data returned by the public demo API we call below
export interface Todo {
  userId: number;
  id: number;
  title: string;
  completed: boolean;
}
