import { describe, it, expect, beforeEach, vi } from 'vitest';

class MockEventSource {
  static instances: MockEventSource[] = [];
  url: string;
  listeners: Record<string, Array<(m: MessageEvent) => void>> = {};
  closed = false;
  constructor(url: string) {
    this.url = url;
    MockEventSource.instances.push(this);
  }
  addEventListener(type: string, cb: (m: MessageEvent) => void): void {
    (this.listeners[type] ??= []).push(cb);
  }
  emit(type: string, data: unknown): void {
    const evt = { data: JSON.stringify(data) } as MessageEvent;
    for (const cb of this.listeners[type] ?? []) cb(evt);
  }
  close(): void {
    this.closed = true;
  }
}

describe('runStream store', () => {
  beforeEach(() => {
    MockEventSource.instances = [];
    vi.stubGlobal('EventSource', MockEventSource as unknown as typeof EventSource);
  });

  it('appends metric points and emits to subscribers', async () => {
    const { createRunStreamStore } = await import('./runStream');
    const store = createRunStreamStore('run/x');
    const es = MockEventSource.instances[0]!;

    const seen: number[] = [];
    store.subscribe((s) => {
      seen.push(s.metrics['train_loss']?.values.length ?? 0);
    });

    es.emit('metric', { key: 'train_loss', step: 0, value: 1.0, wall_time: 0 });
    es.emit('metric', { key: 'train_loss', step: 1, value: 0.5, wall_time: 1 });

    const cur = store.get().metrics['train_loss'];
    expect(cur.steps).toEqual([0, 1]);
    expect(cur.values).toEqual([1.0, 0.5]);
    expect(seen[seen.length - 1]).toBe(2);

    store.close();
    expect(es.closed).toBe(true);
  });

  it('caps the log buffer', async () => {
    const { createRunStreamStore } = await import('./runStream');
    const store = createRunStreamStore('run/x');
    const es = MockEventSource.instances[0]!;
    for (let i = 0; i < 5; i++) es.emit('log', { line: `L${i}`, ts: i });
    expect(store.get().log).toEqual(['L0', 'L1', 'L2', 'L3', 'L4']);
    store.close();
  });

  it('keeps last 12 image samples', async () => {
    const { createRunStreamStore } = await import('./runStream');
    const store = createRunStreamStore('run/x');
    const es = MockEventSource.instances[0]!;
    for (let i = 0; i < 20; i++) es.emit('image_sample', { tag: 't', step: i });
    expect(store.get().imageSamples.length).toBe(12);
    expect(store.get().imageSamples[0]!.step).toBe(8);
    store.close();
  });

  it('flips connected on status', async () => {
    const { createRunStreamStore } = await import('./runStream');
    const store = createRunStreamStore('run/x');
    const es = MockEventSource.instances[0]!;
    expect(store.get().connected).toBe(false);
    es.emit('status', { phase: 'replay_start' });
    expect(store.get().connected).toBe(true);
    store.close();
  });
});
