type Props = {
  content: string;
  aiGenerated: boolean;
  model?: string;
  sources?: { id: number; title: string }[];
};

export function AssistantMessage({ content, aiGenerated, model, sources = [] }: Props) {
  return (
    <article aria-label="Assistant message">
      {aiGenerated && (
        <p className="text-xs text-muted-foreground">
          AI-generated{model ? ` · ${model}` : ""}. Check important information.
        </p>
      )}
      <div className="prose">{content}</div>
      {sources.length > 0 && (
        <ul className="mt-2 text-xs">
          {sources.map((s) => (
            <li key={s.id}>[{s.id}] {s.title}</li>
          ))}
        </ul>
      )}
    </article>
  );
}
