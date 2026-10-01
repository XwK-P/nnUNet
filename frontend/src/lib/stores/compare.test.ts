import { describe, it, expect, beforeEach, vi } from 'vitest';
import { createCompareStore } from './compare';

describe('compare store', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('starts idle', () => {
    const s = createCompareStore();
    expect(s.get()).toEqual({ kind: 'idle' });
  });

  it('encodes run_ids as repeated query params', async () => {
    const mock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ metrics: [], summaries: [] }), { status: 200 })
    );
    vi.stubGlobal('fetch', mock);

    const s = createCompareStore();
    await s.load(['a/b/c', 'd/e/f']);

    const url = mock.mock.calls[0][0] as string;
    expect(url).toMatch(/run_ids=a%2Fb%2Fc/);
    expect(url).toMatch(/run_ids=d%2Fe%2Ff/);
  });

  it('transitions to loaded', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ metrics: [{ run_id: 'a/b/c', series: {} }], summaries: [] }),
      { status: 200 },
    )));

    const s = createCompareStore();
    await s.load(['a/b/c']);
    const final = s.get();
    expect(final.kind).toBe('loaded');
    if (final.kind === 'loaded') {
      expect(final.data.metrics).toHaveLength(1);
    }
  });

  it('transitions to error on 5xx', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ kind: 'internal_error', message: 'boom', retryable: false, details: null }),
      { status: 500 },
    )));

    const s = createCompareStore();
    await s.load(['x/y/z']);
    expect(s.get().kind).toBe('error');
  });
});
