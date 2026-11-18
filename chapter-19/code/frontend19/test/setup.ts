import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, beforeEach } from "vitest";

// Files marked `@vitest-environment node` have no `window`, so guard for it.
const inBrowserLikeEnvironment = typeof window !== "undefined";

beforeEach(() => {
  if (!inBrowserLikeEnvironment) return;
  window.localStorage.clear();
  document.documentElement.className = "";

  // jsdom lacks several browser features that Radix UI and next-themes use.
  // Give them harmless stand-ins.
  const proto = window.HTMLElement.prototype;
  proto.scrollIntoView = () => {};
  proto.hasPointerCapture = () => false;
  proto.setPointerCapture = () => {};
  proto.releasePointerCapture = () => {};
  window.ResizeObserver ??= class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
  window.matchMedia ??= ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
});

afterEach(() => {
  if (inBrowserLikeEnvironment) cleanup();
});
