import type { Page } from "../api/types";

/** The shape TanStack Query keeps for an infinite query. */
export type InfiniteData<T, P = unknown> = { pages: Page<T>[]; pageParams: P[] };

export function flattenPages<T, P = unknown>(data: InfiniteData<T, P> | undefined): T[] {
  return data ? data.pages.flatMap((page) => page.results) : [];
}

export function uniqueById<T extends { id: string }>(items: T[]): T[] {
  const seen = new Set<string>();
  return items.filter((item) => (seen.has(item.id) ? false : (seen.add(item.id), true)));
}

/** Optimistically show a new item at the top of the first page. Returns new objects; never mutates the cache. */
export function prependToFirstPage<T extends { id: string }, P = unknown>(data: InfiniteData<T, P> | undefined, item: T): InfiniteData<T, P> {
  if (!data || data.pages.length === 0) return { pages: [{ results: [item], next: null }], pageParams: [null as P] };
  const [first, ...rest] = data.pages;
  return { ...data, pages: [{ ...first, results: [item, ...first.results.filter((x) => x.id !== item.id)] }, ...rest] };
}

export function replaceItem<T extends { id: string }, P = unknown>(data: InfiniteData<T, P> | undefined, oldId: string, item: T): InfiniteData<T, P> | undefined {
  if (!data) return data;
  return { ...data, pages: data.pages.map((page) => ({ ...page, results: page.results.map((x) => (x.id === oldId ? item : x)) })) };
}

export function removeItem<T extends { id: string }, P = unknown>(data: InfiniteData<T, P> | undefined, id: string): InfiniteData<T, P> | undefined {
  if (!data) return data;
  return { ...data, pages: data.pages.map((page) => ({ ...page, results: page.results.filter((x) => x.id !== id) })) };
}
