export interface Dataset {
  id: string;
  dataset_id_int: number | null;
  name: string | null;
  raw_path: string | null;
  preprocessed_path: string | null;
  last_scanned_at: string | null;
  fingerprint_json: string | null;
  case_count: number | null;
  modality_count: number | null;
}

export interface Run {
  id: string;
  dataset_id: string;
  plans_name: string;
  trainer_name: string;
  configuration: string;
  fold: string;
  output_folder: string;
  status: string;
  source: string;
  created_at: string | null;
  last_seen_at: string | null;
  tags_json: string | null;
  notes: string | null;
}

export interface RunFilter {
  dataset_id?: string;
  plans_name?: string;
  trainer_name?: string;
  configuration?: string;
  fold?: string;
  status?: string;
}

export interface DiskUsage {
  path: string;
  total: number | null;
  free: number | null;
}

export interface DashboardData {
  counts: {
    datasets: number;
    preprocessed_datasets: number;
    runs: number;
    completed_runs: number;
  };
  recent_runs: Run[];
  active_jobs: unknown[];
  system: {
    disk: {
      raw: DiskUsage;
      preprocessed: DiskUsage;
      results: DiskUsage;
    };
  };
}

export interface Case {
  id: string;
  dataset_id: string;
  channels: Record<string, string>;
  label_path: string | null;
}

export interface Prediction {
  case_id: string;
  path: string;
}

export interface MetricEvent {
  kind: 'metric';
  key: string;
  step: number;
  value: number;
  wall_time: number;
}

export interface LogEvent {
  kind: 'log';
  line: string;
  ts: number;
}

export interface ImageSampleEvent {
  kind: 'image_sample';
  tag: string;
  step: number;
  url?: string;
}

export interface RunStatusEvent {
  kind: 'status';
  phase: string;
  message?: string;
}

export type RunEvent = MetricEvent | LogEvent | ImageSampleEvent | RunStatusEvent;

export interface Job {
  id: number;
  kind: string;
  args_json: string;
  pid: number | null;
  pgid: number | null;
  status: string;
  started_at: string | null;
  ended_at: string | null;
  exit_code: number | null;
  log_path: string | null;
  output_run_id: string | null;
  created_by: string | null;
  error_message: string | null;
}
