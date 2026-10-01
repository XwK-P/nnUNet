import { endpoints, ApiError } from '../api';
import type { Model } from '../types';

type State =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'loaded'; data: Model[] }
  | { kind: 'error'; error: ApiError | Error };

type Listener = (state: State) => void;

export function createModelsStore() {
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
    async load(): Promise<void> {
      current = { kind: 'loading' };
      emit();
      try {
        const data = await endpoints.getModels();
        current = { kind: 'loaded', data };
      } catch (e) {
        current = { kind: 'error', error: e as ApiError | Error };
      }
      emit();
    },
  };
}
