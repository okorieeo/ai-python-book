import ReactMarkdown from "react-markdown";

// react-markdown does not render raw HTML and strips javascript: links by default.
// That is the property we rely on (17.7): never add rehype-raw to this component.
export default function Markdown({ children }: { children: string }) {
  return (
    <ReactMarkdown
      components={{
        a: ({ href, children: label }) => (
          <a href={href} target="_blank" rel="noopener noreferrer" className="text-primary underline">
            {label}
          </a>
        ),
        pre: ({ children: code }) => (
          <pre className="my-2 max-w-full overflow-x-auto rounded-md bg-muted p-3 text-sm" tabIndex={0}>
            {code}
          </pre>
        ),
      }}
    >
      {children}
    </ReactMarkdown>
  );
}
