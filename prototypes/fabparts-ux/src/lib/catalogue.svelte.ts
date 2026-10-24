import { copy, initialParts, ready, savePart, type Part } from "./demo";
import { storageKey } from "./app";
const KEY = storageKey("demo-catalogue.v1");
function read(): Part[] {
  try {
    const s = JSON.parse(localStorage.getItem(KEY) || "null");
    if (
      s?.format === "fabparts-ux-demo" &&
      Array.isArray(s.parts) &&
      s.parts.every(
        (p: Part) =>
          p.id?.startsWith("demo-") &&
          p.resources &&
          Array.isArray(p.libraries),
      )
    )
      return s.parts.map((p: Part) => ({
        ...p,
        sync:
          p.sync === "syncing"
            ? ready(p) === "draft"
              ? "incomplete"
              : "error"
            : p.sync,
      }));
  } catch {
    /* Demo remains usable without storage. */
  }
  return initialParts();
}
class Catalogue {
  parts = $state<Part[]>(read());
  past = $state<Part[][]>([]);
  future = $state<Part[][]>([]);
  storageFailed = $state(false);
  epoch = 0;
  requests = new Map<string, number>();
  persist() {
    try {
      localStorage.setItem(
        KEY,
        JSON.stringify({ format: "fabparts-ux-demo", parts: this.parts }),
      );
      this.storageFailed = false;
    } catch {
      this.storageFailed = true;
    }
  }
  edit(fn: (parts: Part[]) => Part[]) {
    const next = fn(copy(this.parts));
    this.past.push(copy(this.parts));
    this.future = [];
    this.parts = next;
    this.persist();
  }
  save(part: Part) {
    this.edit((parts) => savePart(parts, part));
    this.sync(part.id);
  }
  sync(id: string, fail = false) {
    const p = this.parts.find((p) => p.id === id);
    if (!p) return;
    const request = (this.requests.get(id) || 0) + 1;
    this.requests.set(id, request);
    if (ready(p) === "draft") {
      p.sync = "incomplete";
      this.persist();
      return;
    }
    p.sync = "syncing";
    const epoch = this.epoch;
    this.persist();
    setTimeout(() => {
      if (epoch !== this.epoch || this.requests.get(id) !== request) return;
      const p = this.parts.find((p) => p.id === id);
      if (p) {
        p.sync = fail ? "error" : "available";
        this.persist();
      }
    }, 1200);
  }
  undo() {
    const old = this.past.pop();
    if (!old) return;
    this.epoch++;
    this.future.push(copy(this.parts));
    this.parts = this.settle(old);
    this.persist();
  }
  redo() {
    const next = this.future.pop();
    if (!next) return;
    this.epoch++;
    this.past.push(copy(this.parts));
    this.parts = this.settle(next);
    this.persist();
  }
  settle(parts: Part[]) {
    return parts.map(
      (p) =>
        ({
          ...p,
          sync:
            p.sync === "syncing"
              ? ready(p) === "draft"
                ? "incomplete"
                : "error"
              : p.sync,
        }) as Part,
    );
  }
  reset() {
    this.epoch++;
    this.edit(() => initialParts());
  }
}
export const catalogue = new Catalogue();
