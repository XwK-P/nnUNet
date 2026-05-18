export class ApiError extends Error {
  readonly kind: string;
  readonly retryable: boolean;
  readonly details: unknown;
  readonly status: number;

  constructor(opts: {
    kind: string;
    message: string;
    retryable: boolean;
    details: unknown;
    status: number;
  }) {
    super(opts.message);
    this.name = 'ApiError';
    this.kind = opts.kind;
    this.retryable = opts.retryable;
    this.details = opts.details;
    this.status = opts.status;
  }
}

async function envelope(res: Response): Promise<never> {
  let body: unknown;
  try {
    body = await res.json();
  } catch {
    throw new ApiError({
      kind: 'http_error',
      message: `HTTP ${res.status} ${res.statusText}`,
      retryable: res.status >= 500,
      details: null,
      status: res.status,
    });
  }
  const env = body as {
    kind?: string;
    message?: string;
    retryable?: boolean;
    details?: unknown;
  };
  throw new ApiError({
    kind: env.kind ?? 'http_error',
    message: env.message ?? `HTTP ${res.status}`,
    retryable: env.retryable ?? res.status >= 500,
    details: env.details ?? null,
    status: res.status,
  });
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) {
    await envelope(res);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  get<T>(url: string): Promise<T> {
    return request<T>(url);
  },
  post<T>(url: string, body: unknown): Promise<T> {
    return request<T>(url, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body),
    });
  },
};

import type { Dataset, Run, RunFilter, DashboardData } from './types';

function qs(params: Record<string, string | undefined>): string {
  const usp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') usp.set(k, v);
  }
  const s = usp.toString();
  return s ? `?${s}` : '';
}

export const endpoints = {
  getDatasets: () => api.get<Dataset[]>('/api/datasets'),
  getDataset: (id: string) => api.get<Dataset>(`/api/datasets/${encodeURIComponent(id)}`),
  getDatasetPlans: (id: string) =>
    api.get<Record<string, unknown>>(`/api/datasets/${encodeURIComponent(id)}/plans`),
  getDatasetFingerprint: (id: string) =>
    api.get<Record<string, unknown>>(`/api/datasets/${encodeURIComponent(id)}/fingerprint`),
  getRuns: (filter: RunFilter = {}) =>
    api.get<Run[]>(`/api/runs${qs(filter as Record<string, string | undefined>)}`),
  getRun: (id: string) => api.get<Run>(`/api/runs/${id}`),
  getDashboard: () => api.get<DashboardData>('/api/dashboard'),
};
