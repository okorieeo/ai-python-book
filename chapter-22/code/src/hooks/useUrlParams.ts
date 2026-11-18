"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback } from "react";

/** The URL is the state of a filtered table: shareable, bookmarkable, and
 *  the Back button works. */
export function useUrlParams() {
  const router = useRouter();
  const pathname = usePathname();
  const search = useSearchParams();

  const get = useCallback(
    (key: string, fallback = "") => search.get(key) ?? fallback,
    [search],
  );

  const set = useCallback(
    (patch: Record<string, string | null>) => {
      const next = new URLSearchParams(search.toString());
      for (const [key, value] of Object.entries(patch)) {
        if (value === null || value === "") next.delete(key);
        else next.set(key, value);
      }
      if (!("page" in patch)) next.delete("page"); // a new filter means page 1
      const text = next.toString();
      router.replace(text ? `${pathname}?${text}` : pathname, {
        scroll: false,
      });
    },
    [router, pathname, search],
  );

  return { get, set };
}
