/**
 * Models can emit dozens of tokens per second. Re-rendering a Markdown message for
 * each one wastes work, and the eye cannot see more than one update per frame anyway.
 * The batcher collects deltas and hands them over once per animation frame, in order.
 */
export interface DeltaBatcher {
  push(messageId: string, delta: string): void;
  flush(): void; // hand over everything now (call before processing any other event)
  cancel(): void; // drop everything (call when the socket is torn down)
}

export function createDeltaBatcher(
  emit: (messageId: string, text: string) => void,
  schedule: (run: () => void) => unknown = (run) => requestAnimationFrame(run),
  cancelSchedule: (handle: unknown) => void = (h) => cancelAnimationFrame(h as number),
): DeltaBatcher {
  let queue: [string, string][] = [];
  let handle: unknown = null;

  const flush = () => {
    if (handle !== null) {
      cancelSchedule(handle);
      handle = null;
    }
    const pending = queue;
    queue = [];
    for (const [id, text] of pending) emit(id, text);
  };

  return {
    push(messageId, delta) {
      const last = queue[queue.length - 1];
      if (last && last[0] === messageId) last[1] += delta;
      else queue.push([messageId, delta]);
      if (handle === null) {
        handle = schedule(() => {
          handle = null;
          flush();
        });
      }
    },
    flush,
    cancel() {
      if (handle !== null) cancelSchedule(handle);
      handle = null;
      queue = [];
    },
  };
}
