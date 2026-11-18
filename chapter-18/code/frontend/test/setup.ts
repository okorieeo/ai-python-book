import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, beforeEach } from "vitest";

// Files marked `@vitest-environment node` have no `window`, so guard for it.
const inBrowserLikeEnvironment = typeof window !== "undefined";

beforeEach(() => {
  if (!inBrowserLikeEnvironment) return;
  // jsdom does not implement scrollIntoView, so give components a harmless stand-in.
  window.HTMLElement.prototype.scrollIntoView = () => {};
  window.localStorage.clear();
});
afterEach(() => {
  if (inBrowserLikeEnvironment) cleanup();
});
