function first<T>(items: T[]): T | undefined {
  return items[0];
}

const n = first([1, 2, 3]);          // TS knows n is number | undefined
const s = first(["a", "b"]);         // string | undefined

interface ApiResponse<T> {
  data: T;
  error?: string;
}

const res: ApiResponse<User[]> = { data: [] };
