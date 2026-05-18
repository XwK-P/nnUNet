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
});
