import { endpoints, ApiError } from '../api';
import type { CompareResponse } from '../types';

type State =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'loaded'; data: CompareResponse }
  | { kind: 'error'; error: ApiError | Error };

type Listener = (state: State) => void;

export function createCompareStore() {
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
    async load(runIds: string[], metricKeys?: string[]): Promise<void> {
      current = { kind: 'loading' };
      emit();
      try {
        const data = await endpoints.getCompare(runIds, metricKeys);
        current = { kind: 'loaded', data };
      } catch (e) {
        current = { kind: 'error', error: e as ApiError | Error };
      }
      emit();
    },
  };
}
