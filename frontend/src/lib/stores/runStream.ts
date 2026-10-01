import { connectRunEvents } from '../sse';

const MAX_POINTS = 4000;
const MAX_LOG_LINES = 5000;

export interface RunStreamState {
  metrics: Record<string, { steps: number[]; values: number[] }>;
  log: string[];
  imageSamples: Array<{ tag: string; step: number; url?: string }>;
  connected: boolean;
}

type Listener = (s: RunStreamState) => void;

export function createRunStreamStore(runId: string) {
  let state: RunStreamState = { metrics: {}, log: [], imageSamples: [], connected: false };
  const listeners = new Set<Listener>();
  function emit() {
    for (const l of listeners) l(state);
  }

  const stream = connectRunEvents(runId);
  stream.onMetric((m) => {
    const cur = state.metrics[m.key] ?? { steps: [], values: [] };
    cur.steps.push(m.step);
    cur.values.push(m.value);
    if (cur.steps.length > MAX_POINTS) {
      cur.steps.shift();
      cur.values.shift();
    }
    state = { ...state, metrics: { ...state.metrics, [m.key]: cur } };
    emit();
  });
  stream.onLog((e) => {
    const log = [...state.log, e.line];
    if (log.length > MAX_LOG_LINES) log.splice(0, log.length - MAX_LOG_LINES);
    state = { ...state, log };
    emit();
  });
  stream.onImageSample((e) => {
    state = { ...state, imageSamples: [...state.imageSamples, e].slice(-12) };
    emit();
  });
  stream.onStatus(() => {
    state = { ...state, connected: true };
    emit();
  });

  return {
    get(): RunStreamState {
      return state;
    },
    subscribe(l: Listener): () => void {
      listeners.add(l);
      l(state);
      return () => listeners.delete(l);
    },
    close(): void {
      stream.close();
    },
  };
}
