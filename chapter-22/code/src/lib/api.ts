import { getAccessToken } from "./auth";

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public fields?: Record<string, string[]>,
  ) {
    super(message);
  }
}

export type Params = Record<
  string,
  string | number | boolean | null | undefined
>;

/** ?a=1&b=x, leaving out anything empty so URLs stay clean. */
export function buildQuery(params: Params = {}): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

async function request(path: string, init: RequestInit, params?: Params) {
  const token = getAccessToken();
  const response = await fetch(
    `${API_URL}/api/v1${path}${buildQuery(params)}`,
    {
      ...init,
      headers: {
        Accept: "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...init.headers,
      },
    },
  );
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const error = body?.error;
    throw new ApiError(
      response.status,
      error?.code ?? "error",
      error?.message ?? response.statusText,
      error?.fields,
    );
  }
  return response;
}

export async function apiGet<T>(path: string, params?: Params): Promise<T> {
  return (await request(path, {}, params)).json();
}

export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const response = await request(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return response.json();
}

/** Fetch a file with the auth header, then hand it to the browser. */
export async function apiDownload(
  path: string,
  params: Params,
  filename: string,
) {
  const blob = await (await request(path, {}, params)).blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}
