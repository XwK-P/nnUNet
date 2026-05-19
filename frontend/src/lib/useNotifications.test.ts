import { describe, it, expect, beforeEach, vi } from 'vitest';
import { createNotifier } from './useNotifications';

describe('createNotifier', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('requests permission once on first event', async () => {
    const requestPermission = vi.fn().mockResolvedValue('granted');
    (globalThis as any).Notification = vi.fn();
    (globalThis as any).Notification.permission = 'default';
    (globalThis as any).Notification.requestPermission = requestPermission;

    const n = createNotifier();
    await n.fire({ jobId: 1, kind: 'train', status: 'completed' });

    expect(requestPermission).toHaveBeenCalledTimes(1);
    expect((globalThis as any).Notification).toHaveBeenCalledTimes(1);
  });

  it('does not re-fire for same job_id', async () => {
    (globalThis as any).Notification = vi.fn();
    (globalThis as any).Notification.permission = 'granted';
    (globalThis as any).Notification.requestPermission = vi.fn();

    const n = createNotifier();
    await n.fire({ jobId: 1, kind: 'train', status: 'completed' });
    await n.fire({ jobId: 1, kind: 'train', status: 'completed' });

    expect((globalThis as any).Notification).toHaveBeenCalledTimes(1);
  });

  it('does nothing when permission denied', async () => {
    const requestPermission = vi.fn().mockResolvedValue('denied');
    (globalThis as any).Notification = vi.fn();
    (globalThis as any).Notification.permission = 'default';
    (globalThis as any).Notification.requestPermission = requestPermission;

    const n = createNotifier();
    await n.fire({ jobId: 1, kind: 'train', status: 'completed' });

    expect((globalThis as any).Notification).not.toHaveBeenCalled();
  });

  it('only fires for terminal statuses', async () => {
    (globalThis as any).Notification = vi.fn();
    (globalThis as any).Notification.permission = 'granted';
    (globalThis as any).Notification.requestPermission = vi.fn();

    const n = createNotifier();
    await n.fire({ jobId: 1, kind: 'train', status: 'running' });
    await n.fire({ jobId: 1, kind: 'train', status: 'starting' });
    await n.fire({ jobId: 1, kind: 'train', status: 'queued' });

    expect((globalThis as any).Notification).not.toHaveBeenCalled();
  });
});
