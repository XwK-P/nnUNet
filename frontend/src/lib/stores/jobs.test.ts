import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { createJobsStore } from './jobs';

describe('jobs store', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('loads jobs via /api/jobs', async () => {
    const sample = [{ id: 1, kind: 'train', status: 'running' }];
    const mock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify(sample), { status: 200 }));
    vi.stubGlobal('fetch', mock);

    const store = createJobsStore();
    await store.load();
    const s = store.get();

    expect(mock).toHaveBeenCalledWith('/api/jobs', undefined);
    expect(s.kind).toBe('loaded');
    if (s.kind === 'loaded') expect(s.data[0].id).toBe(1);
  });

  it('re-emits each subscribe with current state', async () => {
    const mock = vi.fn().mockResolvedValue(new Response('[]', { status: 200 }));
    vi.stubGlobal('fetch', mock);

    const store = createJobsStore();
    const seen: string[] = [];
    const unsub = store.subscribe((s) => seen.push(s.kind));
    expect(seen).toEqual(['idle']);
    unsub();
  });

  it('captures error state on rejection', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ kind: 'server_error', message: 'boom' }), {
          status: 500,
        }),
      ),
    );

    const store = createJobsStore();
    await store.load();
    const s = store.get();
    expect(s.kind).toBe('error');
    if (s.kind === 'error') expect(s.error.message).toBe('boom');
  });

  it('startPolling triggers periodic loads', async () => {
    const mock = vi.fn().mockResolvedValue(new Response('[]', { status: 200 }));
    vi.stubGlobal('fetch', mock);

    const store = createJobsStore();
    store.startPolling(1000);
    await vi.advanceTimersByTimeAsync(0);
    expect(mock).toHaveBeenCalledTimes(1);

    await vi.advanceTimersByTimeAsync(1000);
    expect(mock).toHaveBeenCalledTimes(2);

    await vi.advanceTimersByTimeAsync(1000);
    expect(mock).toHaveBeenCalledTimes(3);

    store.stopPolling();
    await vi.advanceTimersByTimeAsync(2000);
    expect(mock).toHaveBeenCalledTimes(3);
  });
});
