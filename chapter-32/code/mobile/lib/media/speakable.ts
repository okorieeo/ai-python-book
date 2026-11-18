/** The same rules as the server's speech_text.py. A voice should never read out punctuation or web addresses. */
export function toSpeakable(markdown: string): string {
  return markdown
    .replace(/```[\s\S]*?```/g, ' (code omitted) ')
    .replace(/`([^`]*)`/g, '$1')
    .replace(/!\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
    .replace(/https?:\/\/\S+/g, 'a link')
    .replace(/^[ \t]{0,3}#{1,6}[ \t]*/gm, '')
    .replace(/^[ \t]*[-*+][ \t]+/gm, '')
    .replace(/^[ \t]*\d+[.)][ \t]+/gm, '')
    .replace(/(\*\*|__|\*|_)(.+?)\1/g, '$2')
    .replace(/^[ \t]*>[ \t]?/gm, '')
    .replace(/\|/g, ' ')
    .replace(/[ \t]+/g, ' ')
    .replace(/\n{2,}/g, '\n\n')
    .trim();
}

/** Cut at sentence ends so every piece sounds natural and fits the speech engine's limit. */
export function splitForSpeech(text: string, maxChars: number): string[] {
  if (!text) return [];
  if (text.length <= maxChars) return [text];
  const sentences = text.split(/(?<=[.!?])\s+|\n{2,}/);
  const parts: string[] = [];
  let current = '';
  for (let sentence of sentences) {
    while (sentence.length > maxChars) {
      const space = sentence.lastIndexOf(' ', maxChars);
      const cut = space > 0 ? space : maxChars;
      if (current) {
        parts.push(current);
        current = '';
      }
      parts.push(sentence.slice(0, cut).trim());
      sentence = sentence.slice(cut).trim();
    }
    if (current && current.length + sentence.length + 1 > maxChars) {
      parts.push(current);
      current = sentence;
    } else {
      current = `${current} ${sentence}`.trim();
    }
  }
  if (current) parts.push(current);
  return parts;
}
