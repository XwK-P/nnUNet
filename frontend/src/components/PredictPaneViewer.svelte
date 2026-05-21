<script lang="ts">
  import Canvas2DViewer from '../lib/viewer/Canvas2DViewer.svelte';

  // 3-pane side-by-side review for a selected prediction case.
  //
  // The Predict page passes already-built URLs (each pointing to a PNG
  // slice endpoint) plus the axis/slice the user picked. We deliberately
  // use Canvas2DViewer (a plain <img>) rather than NiiVue here because
  // the backend exposes PNG slices, not raw NIfTI downloads; the full
  // 3-D viewer can land in a later phase.
  let {
    inputUrl,
    labelUrl,
    predictionUrl,
    axis = $bindable(0),
    slice = $bindable(0),
    sliceMax = 255,
  }: {
    inputUrl: string | null;
    labelUrl: string | null;
    predictionUrl: string | null;
    axis?: number;
    slice?: number;
    sliceMax?: number;
  } = $props();
</script>

<div class="bg-bg-soft border border-border-soft rounded p-3">
  <div class="flex items-center gap-3 mb-2 text-[11px] text-slate-300">
    <label class="flex items-center gap-1">
      Axis
      <select class="bg-bg-panel border border-border-soft rounded px-1 py-0.5" bind:value={axis}>
        <option value={0}>Z</option><option value={1}>Y</option><option value={2}>X</option>
      </select>
    </label>
    <label class="flex-1 flex items-center gap-2">
      Slice
      <input type="range" min="0" max={sliceMax} bind:value={slice} class="flex-1" />
      <span class="w-10 text-right">{slice}</span>
    </label>
  </div>

  <div class="grid grid-cols-3 gap-2">
    <div>
      <h5 class="text-[11px] text-slate-500 mb-1">Input</h5>
      {#if inputUrl}
        <Canvas2DViewer src={inputUrl} alt="input" />
      {:else}
        <p class="text-xs text-slate-500 py-8 text-center">pick a case</p>
      {/if}
    </div>
    <div>
      <h5 class="text-[11px] text-slate-500 mb-1">Ground truth</h5>
      {#if labelUrl}
        <Canvas2DViewer src={labelUrl} alt="label" />
      {:else}
        <p class="text-xs text-slate-500 py-8 text-center">no GT label for this case</p>
      {/if}
    </div>
    <div>
      <h5 class="text-[11px] text-slate-500 mb-1">Prediction</h5>
      {#if predictionUrl}
        <Canvas2DViewer src={predictionUrl} alt="prediction" />
      {:else}
        <p class="text-xs text-slate-500 py-8 text-center">pick a case</p>
      {/if}
    </div>
  </div>
</div>
