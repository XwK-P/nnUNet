<script lang="ts">
  import { imageEndpoints } from '../lib/api';
  import Canvas2DViewer from '../lib/viewer/Canvas2DViewer.svelte';
  import NiiVueViewer from '../lib/viewer/NiiVueViewer.svelte';
  import type { Case } from '../lib/types';

  let { datasetId, case: caseObj }: { datasetId: string; case: Case } = $props();

  let axis = $state(0);
  let slice = $state(0);
  let channel = $state(0);
  let overlayOn = $state(false);
  let opacity = $state(0.5);
  // Phase 2 uses 2D PNG previews (fast). NiiVue full-volume rendering is wired
  // but defaults off — the server doesn't expose raw NIfTI URLs yet (Phase 6).
  let mode = $state<'png' | 'niivue'>('png');

  const channels = $derived(Object.keys(caseObj.channels).sort());

  const previewUrl = $derived(
    imageEndpoints.getCasePreviewUrl(datasetId, caseObj.id, {
      axis, slice, channel: Number(channels[channel] ?? 0),
    })
  );

  const labelUrl = $derived(
    caseObj.label_path && overlayOn
      ? imageEndpoints.getCaseLabelsUrl(datasetId, caseObj.id, { axis, slice })
      : null
  );
</script>

<div class="space-y-2">
  <div class="flex gap-2 text-xs items-center">
    <label class="text-slate-500">Axis
      <select class="bg-bg-panel border border-border-soft rounded px-1 py-0.5 ml-1" bind:value={axis}>
        <option value={0}>Z (axial)</option>
        <option value={1}>Y (coronal)</option>
        <option value={2}>X (sagittal)</option>
      </select>
    </label>
    <label class="text-slate-500">Channel
      <select class="bg-bg-panel border border-border-soft rounded px-1 py-0.5 ml-1" bind:value={channel}>
        {#each channels as ch, i}<option value={i}>{ch}</option>{/each}
      </select>
    </label>
    <label class="text-slate-500 flex-1 flex items-center gap-2">Slice
      <input type="range" min="0" max="255" bind:value={slice} class="flex-1" />
      <span class="w-8 text-right text-slate-400">{slice}</span>
    </label>
    {#if caseObj.label_path}
      <label class="text-slate-500 flex items-center gap-1">
        <input type="checkbox" bind:checked={overlayOn} /> Overlay
      </label>
      {#if overlayOn}
        <label class="text-slate-500 flex items-center gap-1">Opacity
          <input type="range" min="0" max="1" step="0.05" bind:value={opacity} />
        </label>
      {/if}
    {/if}
  </div>

  {#if mode === 'png'}
    <Canvas2DViewer src={previewUrl} alt={caseObj.id} />
    {#if labelUrl}
      <p class="text-[10px] text-slate-500">Overlay PNG: <code>{labelUrl}</code></p>
    {/if}
  {:else}
    <NiiVueViewer volumeUrl={previewUrl} overlayUrl={labelUrl ?? undefined} overlayOpacity={opacity} {axis} {slice} />
  {/if}
</div>
