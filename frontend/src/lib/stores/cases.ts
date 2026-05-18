import { imageEndpoints } from '../api';
import { ApiError } from '../api';
import type { Case } from '../types';

type State =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'loaded'; data: Case[] }
  | { kind: 'error'; error: ApiError | Error };

type Listener = (state: State) => void;

export function createCasesStore() {
  let current: State = { kind: 'idle' };
  const listeners = new Set<Listener>();
  function emit() { for (const l of listeners) l(current); }

  return {
    get(): State { return current; },
    subscribe(l: Listener): () => void {
      listeners.add(l); l(current);
      return () => listeners.delete(l);
    },
    async load(datasetId: string): Promise<void> {
      current = { kind: 'loading' }; emit();
      try {
        current = { kind: 'loaded', data: await imageEndpoints.getCases(datasetId) };
      } catch (e) {
        current = { kind: 'error', error: e as ApiError | Error };
      }
      emit();
    },
  };
}
