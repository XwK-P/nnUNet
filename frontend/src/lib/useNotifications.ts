type Status =
  | 'queued'
  | 'starting'
  | 'running'
  | 'completed'
  | 'failed'
  | 'killed'
  | 'cancelled'
  | 'unknown';

export interface JobEvent {
  jobId: number;
  kind: string;
  status: Status;
}

const TERMINAL: Set<Status> = new Set(['completed', 'failed', 'killed', 'cancelled']);

export function createNotifier() {
  const seen = new Set<number>();
  let permission: NotificationPermission | null = null;

  async function ensurePermission(): Promise<NotificationPermission> {
    if (typeof Notification === 'undefined') return 'denied';
    if (permission) return permission;
    if (Notification.permission === 'default') {
      permission = await Notification.requestPermission();
    } else {
      permission = Notification.permission;
    }
    return permission;
  }

  return {
    async fire(ev: JobEvent): Promise<void> {
      if (!TERMINAL.has(ev.status)) return;
      if (seen.has(ev.jobId)) return;
      const perm = await ensurePermission();
      if (perm !== 'granted') return;
      seen.add(ev.jobId);
      new Notification(`Job #${ev.jobId} ${ev.status}`, {
        body: `${ev.kind} job finished`,
        tag: `job-${ev.jobId}`,
      });
    },
    reset(): void {
      seen.clear();
      permission = null;
    },
  };
}

let _singleton: ReturnType<typeof createNotifier> | null = null;

export function useNotifications() {
  if (!_singleton) _singleton = createNotifier();
  return _singleton;
}
