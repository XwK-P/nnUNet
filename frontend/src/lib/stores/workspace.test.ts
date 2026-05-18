import { describe, it, expect, beforeEach } from 'vitest';
import { createWorkspaceStore } from './workspace';

describe('workspace store', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('defaults to null (no workspace)', () => {
    const ws = createWorkspaceStore();
    expect(ws.get()).toBeNull();
  });

  it('stores the selected dataset id', () => {
    const ws = createWorkspaceStore();
    ws.set('Dataset027_ACDC');
    expect(ws.get()).toBe('Dataset027_ACDC');
  });

  it('clears with clear()', () => {
    const ws = createWorkspaceStore();
    ws.set('Dataset027_ACDC');
    ws.clear();
    expect(ws.get()).toBeNull();
  });

  it('persists across restarts', () => {
    const ws = createWorkspaceStore();
    ws.set('Dataset042_BraTS18');
    const ws2 = createWorkspaceStore();
    expect(ws2.get()).toBe('Dataset042_BraTS18');
  });

  it('notifies subscribers on change', () => {
    const ws = createWorkspaceStore();
    const calls: (string | null)[] = [];
    const unsub = ws.subscribe((v) => calls.push(v));
    ws.set('Dataset027_ACDC');
    ws.clear();
    unsub();
    ws.set('should-not-be-recorded');
    expect(calls).toEqual([null, 'Dataset027_ACDC', null]);
  });

  it('propagates updates across independent factory calls', () => {
    // Mimics the real layout: WorkspaceSwitcher in the header and a route
    // component both call createWorkspaceStore() in their own scripts.
    // A set() from one must reach subscribers in the other.
    const fromHeader = createWorkspaceStore();
    const fromRoute = createWorkspaceStore();

    const routeCalls: (string | null)[] = [];
    const unsub = fromRoute.subscribe((v) => routeCalls.push(v));

    fromHeader.set('Dataset027_ACDC');
    expect(fromRoute.get()).toBe('Dataset027_ACDC');
    expect(routeCalls).toEqual([null, 'Dataset027_ACDC']);

    fromHeader.clear();
    expect(routeCalls).toEqual([null, 'Dataset027_ACDC', null]);

    unsub();
  });
});
