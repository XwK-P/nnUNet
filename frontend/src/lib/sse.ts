import { encodePathId, withToken } from './api';
import type { RunEvent } from './types';

export interface RunEventStream {
  onMetric(cb: (e: Extract<RunEvent, { kind: 'metric' }>) => void): void;
  onLog(cb: (e: Extract<RunEvent, { kind: 'log' }>) => void): void;
  onImageSample(cb: (e: Extract<RunEvent, { kind: 'image_sample' }>) => void): void;
  onStatus(cb: (e: Extract<RunEvent, { kind: 'status' }>) => void): void;
  close(): void;
}

export function connectRunEvents(runId: string): RunEventStream {
  // EventSource can't attach Authorization headers, so we hand the
  // token to the backend via ?token=<value>; the auth middleware
  // accepts both forms. The run id is a composite path
  // (dataset/plans__trainer__cfg/fold_N) — encode each segment so
  // reserved chars in user-chosen dataset names don't break routing.
  const es = new EventSource(withToken(`/sse/runs/${encodePathId(runId)}/events`));
  const metric: Array<(e: any) => void> = [];
  const log: Array<(e: any) => void> = [];
  const img: Array<(e: any) => void> = [];
  const status: Array<(e: any) => void> = [];

  function bind(type: string, arr: Array<(e: any) => void>): void {
    es.addEventListener(type, (m: MessageEvent) => {
      try {
        const d = JSON.parse(m.data);
        for (const cb of arr) cb({ kind: type, ...d });
      } catch {
        /* noop */
      }
    });
  }
  bind('metric', metric);
  bind('log', log);
  bind('image_sample', img);
  bind('status', status);

  return {
    onMetric(cb) {
      metric.push(cb);
    },
    onLog(cb) {
      log.push(cb);
    },
    onImageSample(cb) {
      img.push(cb);
    },
    onStatus(cb) {
      status.push(cb);
    },
    close() {
      es.close();
    },
  };
}
