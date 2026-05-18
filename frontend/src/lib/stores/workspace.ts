type Listener = (value: string | null) => void;

const KEY = 'nnunet-gui:workspace';

// Module-level singleton state — all calls to createWorkspaceStore() share
// the same `current` value and listener set, so a `set()` from the header
// switcher propagates to subscribers in any route component on the page.
let current: string | null = null;
const listeners = new Set<Listener>();

function emit(): void {
  for (const l of listeners) l(current);
}

export function createWorkspaceStore() {
  // Re-sync from localStorage on each factory call. This covers the initial
  // page load and keeps test isolation (the test suite clears localStorage
  // between cases and expects the next createWorkspaceStore() to reflect that).
  current = localStorage.getItem(KEY);

  return {
    get(): string | null {
      return current;
    },
    set(id: string): void {
      current = id;
      localStorage.setItem(KEY, id);
      emit();
    },
    clear(): void {
      current = null;
      localStorage.removeItem(KEY);
      emit();
    },
    subscribe(l: Listener): () => void {
      listeners.add(l);
      l(current);
      return () => listeners.delete(l);
    },
  };
}
