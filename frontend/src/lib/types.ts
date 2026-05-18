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
