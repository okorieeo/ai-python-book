/**
 * Streaming Markdown is rendered again and again as text grows. Splitting the text into
 * top-level blocks lets finished blocks be memoized: only the last block re-renders.
 * Blank lines inside a fenced code block do NOT end the block.
 */
const FENCE = /^ {0,3}(`{3,}|~{3,})(.*)$/;

interface Fence {
  char: string;
  length: number;
}

/** Returns the new fence state after reading one line. */
function nextFence(fence: Fence | null, line: string): Fence | null {
  const match = FENCE.exec(line);
  if (!match) return fence;
  const marker = match[1] as string;
  const rest = match[2] as string;
  if (fence) {
    const closes =
      marker[0] === fence.char && marker.length >= fence.length && rest.trim() === "";
    return closes ? null : fence;
  }
  if (marker[0] === "`" && rest.includes("`")) return null; // inline code, not a fence
  return { char: marker[0] as string, length: marker.length };
}

export function splitMarkdownBlocks(text: string): string[] {
  const blocks: string[] = [];
  let current: string[] = [];
  let fence: Fence | null = null;
  const finish = () => {
    if (current.length > 0) blocks.push(current.join("\n"));
    current = [];
  };
  for (const line of text.split("\n")) {
    if (fence === null && line.trim() === "") {
      finish();
      continue;
    }
    current.push(line);
    fence = nextFence(fence, line);
  }
  finish();
  return blocks;
}

/** If the text ends inside an unfinished code fence, close it so it renders as code. */
export function closeOpenFence(block: string): string {
  let fence: Fence | null = null;
  for (const line of block.split("\n")) fence = nextFence(fence, line);
  return fence ? `${block}\n${fence.char.repeat(fence.length)}` : block;
}
