import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { api, ApiError, encodePathId, endpoints, getStoredToken, imageEndpoints, withToken } from './api';

const TOKEN_KEY = 'nnunet_gui_token';

describe('api client', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    window.sessionStorage.removeItem(TOKEN_KEY);
  });

  afterEach(() => {
    window.sessionStorage.removeItem(TOKEN_KEY);
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

  it('does not add Authorization header when no token is stored', async () => {
    const mock = vi.fn().mockResolvedValue(new Response('{}', { status: 200 }));
    vi.stubGlobal('fetch', mock);
    // No token -> the init must stay undefined so existing call-shape
    // assertions in other tests keep holding (regression guard for the
    // previous accidental {headers: Headers{}} mutation).
    await api.get('/api/jobs');
    expect(mock).toHaveBeenCalledWith('/api/jobs', undefined);
  });

  it('adds Bearer Authorization header when token is stored', async () => {
    window.sessionStorage.setItem(TOKEN_KEY, 'abc123');
    const mock = vi.fn().mockResolvedValue(new Response('{}', { status: 200 }));
    vi.stubGlobal('fetch', mock);
    await api.get('/api/jobs');
    const [, init] = mock.mock.calls[0];
    const headers = init.headers as Headers;
    expect(headers.get('Authorization')).toBe('Bearer abc123');
  });

  it('withToken returns URL unchanged when no token', () => {
    expect(withToken('/api/runs/r/predictions/c?axis=0')).toBe(
      '/api/runs/r/predictions/c?axis=0',
    );
  });

  it('withToken appends ?token= or &token= depending on prior params', () => {
    window.sessionStorage.setItem(TOKEN_KEY, 'sek\'r&t');
    expect(withToken('/api/sse')).toBe(`/api/sse?token=${encodeURIComponent('sek\'r&t')}`);
    expect(withToken('/api/preview?axis=0')).toBe(
      `/api/preview?axis=0&token=${encodeURIComponent('sek\'r&t')}`,
    );
  });

  it('getStoredToken reads from sessionStorage', () => {
    expect(getStoredToken()).toBeNull();
    window.sessionStorage.setItem(TOKEN_KEY, 'xyz');
    expect(getStoredToken()).toBe('xyz');
  });

  it('encodePathId preserves slash separators while encoding segments', () => {
    expect(encodePathId('Dataset027_ACDC/nnUNetPlans__nnUNetTrainer__3d_fullres/fold_0')).toBe(
      'Dataset027_ACDC/nnUNetPlans__nnUNetTrainer__3d_fullres/fold_0',
    );
    // Spaces, #, ?, % in dataset names — each segment must be encoded
    // independently so reserved chars don't truncate the URL or be
    // reinterpreted as query/fragment by the browser.
    expect(encodePathId('Dataset027_With Space/foo#bar/fold_0')).toBe(
      'Dataset027_With%20Space/foo%23bar/fold_0',
    );
    expect(encodePathId('a?b/c%d')).toBe('a%3Fb/c%25d');
  });

  it('endpoints.getRun encodes the id before interpolating', async () => {
    const mock = vi.fn().mockResolvedValue(new Response('{}', { status: 200 }));
    vi.stubGlobal('fetch', mock);
    await endpoints.getRun('Ds_With Space/foo#bar/fold_0');
    const [url] = mock.mock.calls[0];
    expect(url).toBe('/api/runs/Ds_With%20Space/foo%23bar/fold_0');
  });

  it('imageEndpoints.getPredictionPreviewUrl encodes run id and case id', () => {
    const url = imageEndpoints.getPredictionPreviewUrl(
      'Ds#X/Plans__Trainer__cfg/fold_0',
      'case 001',
      { axis: 0, slice: 4 },
    );
    expect(url).toContain('/api/runs/Ds%23X/Plans__Trainer__cfg/fold_0/predictions/');
    expect(url).toContain('case%20001');
  });
});
