import { api, ApiError } from '../api';
import type { Job } from '../types';

type State =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'loaded'; data: Job[] }
  | { kind: 'error'; error: ApiError | Error };

type Listener = (s: State) => void;

export function createJobsStore() {
  let current: State = { kind: 'idle' };
  const listeners = new Set<Listener>();
  function emit() {
    for (const l of listeners) l(current);
  }

  let timer: ReturnType<typeof setInterval> | undefined;

  async function load(): Promise<void> {
    if (current.kind !== 'loaded') {
      current = { kind: 'loading' };
      emit();
    }
    try {
      const data = await api.get<Job[]>('/api/jobs');
      current = { kind: 'loaded', data };
    } catch (e) {
      current = { kind: 'error', error: e as ApiError | Error };
    }
    emit();
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
    load,
    startPolling(intervalMs = 5000): void {
      load();
      if (timer !== undefined) clearInterval(timer);
      timer = setInterval(load, intervalMs);
    },
    stopPolling(): void {
      if (timer !== undefined) {
        clearInterval(timer);
        timer = undefined;
      }
    },
  };
}
