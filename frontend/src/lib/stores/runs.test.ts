import { describe, it, expect, beforeEach, vi } from 'vitest';
import { createRunsStore } from './runs';

describe('runs store', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('passes filter as query string', async () => {
    const mock = vi.fn().mockResolvedValue(new Response('[]', { status: 200 }));
    vi.stubGlobal('fetch', mock);

    const store = createRunsStore();
    await store.load({ dataset_id: 'Dataset027_ACDC', status: 'completed' });

    expect(mock).toHaveBeenCalledWith(
      expect.stringMatching(/^\/api\/runs\?.*dataset_id=Dataset027_ACDC.*status=completed/),
      undefined,
    );
  });

  it('omits empty filter values from query string', async () => {
    const mock = vi.fn().mockResolvedValue(new Response('[]', { status: 200 }));
    vi.stubGlobal('fetch', mock);

    const store = createRunsStore();
    await store.load({});

    expect(mock).toHaveBeenCalledWith('/api/runs', undefined);
  });
});
