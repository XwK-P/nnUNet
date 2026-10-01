import { describe, it, expect, vi, beforeEach } from 'vitest';

// Use vi.hoisted to allow these variables to be available during the hoisted vi.mock call.
const { loadVolumes, setOpacity, NiivueMock } = vi.hoisted(() => {
  const loadVolumes = vi.fn(async () => undefined);
  const setOpacity = vi.fn();
  const NiivueMock = vi.fn().mockImplementation(() => ({
    attachToCanvas: vi.fn(),
    loadVolumes,
    setOpacity,
    setSliceType: vi.fn(),
    setVolume: vi.fn(),
  }));
  return { loadVolumes, setOpacity, NiivueMock };
});

vi.mock('@niivue/niivue', () => ({ Niivue: NiivueMock }));

import { render } from '@testing-library/svelte';
import NiiVueViewer from './NiiVueViewer.svelte';

describe('NiiVueViewer', () => {
  beforeEach(() => {
    NiivueMock.mockClear();
    loadVolumes.mockClear();
  });

  it('instantiates Niivue and loads the volume URL', async () => {
    render(NiiVueViewer, { props: { volumeUrl: '/api/volume.nii.gz' } });
    // Wait one tick for onMount
    await new Promise((r) => setTimeout(r, 0));
    expect(NiivueMock).toHaveBeenCalledTimes(1);
    expect(loadVolumes).toHaveBeenCalledWith([
      expect.objectContaining({ url: '/api/volume.nii.gz' }),
    ]);
  });

  it('also loads overlay when provided', async () => {
    render(NiiVueViewer, {
      props: { volumeUrl: '/api/v.nii.gz', overlayUrl: '/api/o.nii.gz' },
    });
    await new Promise((r) => setTimeout(r, 0));
    expect(loadVolumes).toHaveBeenCalledWith([
      expect.objectContaining({ url: '/api/v.nii.gz' }),
      expect.objectContaining({ url: '/api/o.nii.gz' }),
    ]);
  });
});
