// A minimal fetch helper. Replace it with the typed client you built in Chapter 20 if you have one.
export async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`/api/v1${path}`, { credentials: "include" });
  if (!response.ok) throw new Error(`Request failed: ${response.status}`);
  return (await response.json()) as T;
}
