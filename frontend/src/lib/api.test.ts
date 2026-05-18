import { describe, it, expect, beforeEach, vi } from 'vitest';
import { api, ApiError } from './api';

describe('api client', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('GET parses JSON on success', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response('{"status":"ok"}', { status: 200 })),
    );

    const body = await api.get<{ status: string }>('/api/system/healthz');
    expect(body).toEqual({ status: 'ok' });
  });

  it('throws ApiError with envelope on 5xx', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({ kind: 'internal_error', message: 'boom', retryable: false, details: null }),
          { status: 500 },
        ),
      ),
    );

    await expect(api.get('/api/system/diag')).rejects.toMatchObject({
      kind: 'internal_error',
      message: 'boom',
      retryable: false,
    });
  });

  it('throws ApiError with a generic envelope when body is not JSON', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response('Not Found', { status: 404 })),
    );

    try {
      await api.get('/api/nope');
      throw new Error('expected throw');
    } catch (e) {
      expect(e).toBeInstanceOf(ApiError);
      expect((e as ApiError).kind).toBe('http_error');
      expect((e as ApiError).message).toContain('404');
    }
  });

  it('POST sends JSON body', async () => {
    const mock = vi.fn().mockResolvedValue(new Response('{}', { status: 200 }));
    vi.stubGlobal('fetch', mock);

    await api.post('/api/jobs', { kind: 'train' });

    expect(mock).toHaveBeenCalledWith(
      '/api/jobs',
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({ 'content-type': 'application/json' }),
        body: JSON.stringify({ kind: 'train' }),
      }),
    );
  });
});
