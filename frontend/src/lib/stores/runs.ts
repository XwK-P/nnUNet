import { endpoints, ApiError } from '../api';
import type { Run, RunFilter } from '../types';

type State =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'loaded'; data: Run[] }
  | { kind: 'error'; error: ApiError | Error };

type Listener = (state: State) => void;

export function createRunsStore() {
  let current: State = { kind: 'idle' };
  const listeners = new Set<Listener>();

  function emit() {
    for (const l of listeners) l(current);
  }

  return {
    get(): State {
      return current;
    },
    subscribe(l: Listener): () => void {
      listeners.add(l);
      l(current);
      return () => listeners.delete(l);
    },
    async load(filter: RunFilter = {}): Promise<void> {
      current = { kind: 'loading' };
      emit();
      try {
        const data = await endpoints.getRuns(filter);
        current = { kind: 'loaded', data };
      } catch (e) {
        current = { kind: 'error', error: e as ApiError | Error };
      }
      emit();
    },
  };
}
