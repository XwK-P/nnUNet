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

// Bearer token plumbing. The backend gates /api/* whenever the server
// was started with --token. The SPA captures the token from the
// initial URL (?token=xxx), persists it in sessionStorage, and strips
// it from the location bar so it doesn't linger in browser history or
// reload as a query-string artifact. fetch() requests carry it as
// Authorization: Bearer; URL-loaded resources (<img src>, EventSource)
// fall back to ?token= via `withToken()` because browsers can't
// attach custom headers to those.
const TOKEN_KEY = 'nnunet_gui_token';

function captureTokenFromUrl(): void {
  if (typeof window === 'undefined' || !window.location) return;
  const url = new URL(window.location.href);
  const t = url.searchParams.get('token');
  if (!t) return;
  try {
    window.sessionStorage.setItem(TOKEN_KEY, t);
  } catch {
    /* sessionStorage unavailable; we'll still use the in-URL token below */
  }
  url.searchParams.delete('token');
  window.history.replaceState({}, '', url.toString());
}

if (typeof window !== 'undefined') captureTokenFromUrl();

export function getStoredToken(): string | null {
  if (typeof window === 'undefined') return null;
  try {
    return window.sessionStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

// Append a token query param to a URL meant for <img>/EventSource. Skips
// the no-op case so URLs stay clean when no token is configured.
export function withToken(url: string): string {
  const t = getStoredToken();
  if (!t) return url;
  const sep = url.includes('?') ? '&' : '?';
  return `${url}${sep}token=${encodeURIComponent(t)}`;
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const token = getStoredToken();
  // Only rewrite init when we actually have a token to add. This keeps
  // the no-token call shape identical to fetch(url, init) so callers
  // and tests that assert on `init === undefined` still hold.
  let finalInit: RequestInit | undefined = init;
  if (token) {
    const headers = new Headers(init?.headers ?? {});
    if (!headers.has('Authorization')) {
      headers.set('Authorization', `Bearer ${token}`);
    }
    finalInit = { ...init, headers };
  }
  const res = await fetch(url, finalInit);
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
  put<T>(url: string, body: unknown): Promise<T> {
    return request<T>(url, {
      method: 'PUT',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body),
    });
  },
};

import type {
  Case,
  CompareResponse,
  Dataset,
  EnsembleRequest,
  EnvVarsResponse,
  ExportModelRequest,
  FindBestConfigRequest,
  GpuInfo,
  ImportModelRequest,
  Job,
  LogLevel,
  Model,
  PerCaseMetricsResponse,
  PostprocRequest,
  Prediction,
  PredictLaunchResponse,
  PredictRequest,
  PreprocessLaunchResponse,
  PreprocessRequest,
  Run,
  RunFilter,
  RunUpdateRequest,
  DashboardData,
  TrainBatchRequest,
  TrainLaunchResponse,
} from './types';

function qs(params: Record<string, string | undefined>): string {
  const usp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') usp.set(k, v);
  }
  const s = usp.toString();
  return s ? `?${s}` : '';
}

// Percent-encode a composite path id (run id, model id) while
// preserving the '/' separators. Raw interpolation breaks whenever a
// dataset name contains reserved URL chars (#, ?, %, space): the
// browser will truncate at # (fragment), reinterpret ? as the start of
// the query string, etc., and the request never reaches the right
// route on the server. encodeURIComponent on the whole id would also
// be wrong because it escapes the separator slashes — backend routes
// expect literal '/' to split run_id into dataset/plans/configuration/
// fold segments. Split + encode + join handles both correctly.
export function encodePathId(id: string): string {
  return id.split('/').map(encodeURIComponent).join('/');
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
  getRun: (id: string) => api.get<Run>(`/api/runs/${encodePathId(id)}`),
  getDashboard: () => api.get<DashboardData>('/api/dashboard'),
  getCompare: (runIds: string[], metricKeys?: string[]) => {
    const params = new URLSearchParams();
    for (const r of runIds) params.append('run_ids', r);
    if (metricKeys) for (const k of metricKeys) params.append('metric_keys', k);
    const q = params.toString();
    return api.get<CompareResponse>(`/api/compare${q ? `?${q}` : ''}`);
  },
  getModels: (): Promise<Model[]> => api.get<Model[]>('/api/models'),
  getModel: (id: string): Promise<Model> => api.get<Model>(`/api/models/${encodePathId(id)}`),
  getPerCaseMetrics: (predictionFolder: string): Promise<PerCaseMetricsResponse> =>
    api.get<PerCaseMetricsResponse>(
      `/api/predict/per_case_metrics?prediction_folder=${encodeURIComponent(predictionFolder)}`,
    ),
  postExportModel: (req: ExportModelRequest): Promise<{ job_id: number }> =>
    api.post<{ job_id: number }>('/api/models/export', req),
  postImportModel: (req: ImportModelRequest): Promise<{ job_id: number }> =>
    api.post<{ job_id: number }>('/api/models/import', req),
  postFindBest: (req: FindBestConfigRequest): Promise<{ job_id: number }> =>
    api.post<{ job_id: number }>('/api/models/find_best', req),
  postEnsemble: (req: EnsembleRequest): Promise<{ job_id: number }> =>
    api.post<{ job_id: number }>('/api/models/ensemble', req),
  postPostproc: (req: PostprocRequest): Promise<{ job_id: number }> =>
    api.post<{ job_id: number }>('/api/postproc/apply', req),
  getEnvVars: (): Promise<EnvVarsResponse> => api.get<EnvVarsResponse>('/api/system/env'),
  getLogLevel: (): Promise<{ level: LogLevel }> =>
    api.get<{ level: LogLevel }>('/api/system/log_level'),
  putLogLevel: (level: LogLevel): Promise<{ level: LogLevel }> =>
    api.put<{ level: LogLevel }>('/api/system/log_level', { level }),
  updateRun: (id: string, body: RunUpdateRequest): Promise<Run> =>
    api.put<Run>(`/api/runs/${encodePathId(id)}`, body),
  getJobs: (): Promise<Job[]> => api.get<Job[]>('/api/jobs'),
};

export const imageEndpoints = {
  getCases: (datasetId: string): Promise<Case[]> =>
    api.get<Case[]>(`/api/datasets/${encodeURIComponent(datasetId)}/cases`),

  getCaseShape: (
    datasetId: string,
    caseId: string,
  ): Promise<{ shape: [number, number, number] }> =>
    api.get<{ shape: [number, number, number] }>(
      `/api/datasets/${encodeURIComponent(datasetId)}/cases/${encodeURIComponent(caseId)}/shape`,
    ),

  getCasePreviewUrl: (
    datasetId: string, caseId: string,
    opts: { axis: number; slice: number; channel: number; window?: [number, number] },
  ): string => {
    const q = new URLSearchParams({
      axis: String(opts.axis),
      slice: String(opts.slice),
      channel: String(opts.channel),
    });
    if (opts.window) {
      q.set('window_lo', String(opts.window[0]));
      q.set('window_hi', String(opts.window[1]));
    }
    return withToken(
      `/api/datasets/${encodeURIComponent(datasetId)}/cases/${encodeURIComponent(caseId)}/preview?${q}`,
    );
  },

  getCaseLabelsUrl: (
    datasetId: string, caseId: string,
    opts: { axis: number; slice: number },
  ): string => {
    const q = new URLSearchParams({ axis: String(opts.axis), slice: String(opts.slice) });
    return withToken(
      `/api/datasets/${encodeURIComponent(datasetId)}/cases/${encodeURIComponent(caseId)}/labels?${q}`,
    );
  },

  getPredictions: (runId: string): Promise<Prediction[]> =>
    api.get<Prediction[]>(`/api/runs/${encodePathId(runId)}/predictions`),

  getPredictionPreviewUrl: (
    runId: string, caseId: string,
    opts: { axis: number; slice: number },
  ): string => {
    const q = new URLSearchParams({ axis: String(opts.axis), slice: String(opts.slice) });
    return withToken(`/api/runs/${encodePathId(runId)}/predictions/${encodeURIComponent(caseId)}?${q}`);
  },

  // Folder-scoped preview for the Predict page, where the user pastes
  // an arbitrary predictions/ folder rather than navigating from a Run.
  getPredictPreviewByFolderUrl: (
    folder: string, caseId: string,
    opts: { axis: number; slice: number },
  ): string => {
    const q = new URLSearchParams({
      prediction_folder: folder,
      case_id: caseId,
      axis: String(opts.axis),
      slice: String(opts.slice),
    });
    return withToken(`/api/predict/preview?${q}`);
  },
};

export const launchEndpoints = {
  postPreprocess: (req: PreprocessRequest, dryRun = false): Promise<PreprocessLaunchResponse> =>
    api.post<PreprocessLaunchResponse>(
      `/api/preprocess${dryRun ? '?dry_run=true' : ''}`,
      req,
    ),
  postTrain: (req: TrainBatchRequest, dryRun = false): Promise<TrainLaunchResponse> =>
    api.post<TrainLaunchResponse>(
      `/api/train${dryRun ? '?dry_run=true' : ''}`,
      req,
    ),
  postPredict: (req: PredictRequest, dryRun = false): Promise<PredictLaunchResponse> =>
    api.post<PredictLaunchResponse>(
      `/api/predict${dryRun ? '?dry_run=true' : ''}`,
      req,
    ),
  stopJob: (id: number): Promise<{ ok: boolean; status: string }> =>
    api.post(`/api/jobs/${id}/stop`, {}),
  cancelJob: (id: number): Promise<{ ok: boolean; status: string }> =>
    api.post(`/api/jobs/${id}/cancel`, {}),
  restartJob: (id: number): Promise<{ new_job_id: number }> =>
    api.post(`/api/jobs/${id}/restart`, {}),
  getGpuInfo: (): Promise<GpuInfo[]> => api.get<GpuInfo[]>('/api/system/gpu'),
};
