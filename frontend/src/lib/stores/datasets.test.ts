import { describe, it, expect, beforeEach, vi } from 'vitest';
import { createDatasetsStore } from './datasets';

describe('datasets store', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('starts in idle state', () => {
    const store = createDatasetsStore();
    expect(store.get()).toEqual({ kind: 'idle' });
  });

  it('transitions to loading then loaded on success', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response(JSON.stringify([
        { id: 'Dataset001_X', dataset_id_int: 1, name: 'X', raw_path: '/r',
          preprocessed_path: null, last_scanned_at: null,
          fingerprint_json: null, case_count: 5, modality_count: 1 },
      ]), { status: 200 })),
    );

    const store = createDatasetsStore();
    const states: string[] = [];
    store.subscribe((s) => states.push(s.kind));

    await store.load();

    expect(states).toEqual(['idle', 'loading', 'loaded']);
    const final = store.get();
    expect(final.kind).toBe('loaded');
    if (final.kind === 'loaded') {
      expect(final.data).toHaveLength(1);
      expect(final.data[0].id).toBe('Dataset001_X');
    }
  });

  it('transitions to error on 5xx', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response(
        JSON.stringify({ kind: 'internal_error', message: 'boom', retryable: false, details: null }),
        { status: 500 },
      )),
    );

    const store = createDatasetsStore();
    await store.load();

    const final = store.get();
    expect(final.kind).toBe('error');
    if (final.kind === 'error') {
      expect(final.error.message).toContain('boom');
    }
  });
});
