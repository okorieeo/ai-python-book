"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { isNearBottom } from "./stick-to-bottom";

/**
 * Keeps a scrolling list pinned to the newest text, but lets go the moment the reader
 * scrolls up, and offers a "jump to latest" button instead of yanking them back.
 */
export function useStickToBottom() {
  const scrollRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const stuck = useRef(true);
  const [showJump, setShowJump] = useState(false);

  const scrollToBottom = useCallback((smooth = false) => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior: smooth ? "smooth" : "auto" });
    stuck.current = true;
    setShowJump(false);
  }, []);

  const onScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    const near = isNearBottom(el);
    stuck.current = near;
    setShowJump(!near);
  }, []);

  // The content grows as tokens arrive, images load and code blocks highlight.
  // Watching its SIZE catches every kind of growth, not just new messages.
  useEffect(() => {
    const el = scrollRef.current;
    const content = contentRef.current;
    if (!el || !content) return;
    const observer = new ResizeObserver(() => {
      if (stuck.current) el.scrollTop = el.scrollHeight;
    });
    observer.observe(content);
    return () => observer.disconnect();
  }, []);

  return { scrollRef, contentRef, onScroll, showJump, scrollToBottom };
}
