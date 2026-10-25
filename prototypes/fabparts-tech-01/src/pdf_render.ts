/** PDF.js display rendering uses animation frames, which WebKit pauses when hidden. */
export function visibleTimeout(
  callback: () => void,
  milliseconds: number,
  visibility: Pick<Document, 'hidden' | 'addEventListener' | 'removeEventListener'> = document,
): () => void {
  let remaining = milliseconds;
  let started: number | null = null;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let stopped = false;
  function stop() {
    stopped = true;
    clearTimeout(timer);
    visibility.removeEventListener('visibilitychange', update);
  }
  function update() {
    if (stopped) return;
    if (started !== null) remaining -= Date.now() - started;
    clearTimeout(timer);
    started = null;
    if (!visibility.hidden) {
      started = Date.now();
      timer = setTimeout(() => { stop(); callback(); }, Math.max(0, remaining));
    }
  }
  visibility.addEventListener('visibilitychange', update);
  update();
  return stop;
}
