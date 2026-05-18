type Listener = (value: string | null) => void;

const KEY = 'nnunet-gui:workspace';

export function createWorkspaceStore() {
  let current: string | null = localStorage.getItem(KEY);
  const listeners = new Set<Listener>();

  function emit(): void {
    for (const l of listeners) l(current);
  }

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
