<div role="log" aria-live="polite" aria-relevant="additions">
  <article aria-busy={isStreaming}>
    {isStreaming ? <span className="sr-only">Assistant is typing</span> : null}
    <Markdown>{message.text}</Markdown>
  </article>
</div>
