<script lang="ts">
  import NiiVueViewer from '../lib/viewer/NiiVueViewer.svelte';

  let {
    inputUrl,
    labelUrl,
    predictionUrl,
  }: {
    inputUrl: string;
    labelUrl: string | null;
    predictionUrl: string | null;
  } = $props();

  let overlay = $state(true);
  let opacity = $state(0.5);
</script>

<div class="bg-bg-soft border border-border-soft rounded p-3">
  <div class="flex items-center gap-2 mb-2 text-[11px]">
    <label class="text-slate-300 flex items-center gap-1">
      <input type="checkbox" bind:checked={overlay} /> Overlay prediction
    </label>
    {#if overlay}
      <label class="text-slate-500 flex items-center gap-1">
        opacity
        <input type="range" min="0" max="1" step="0.05" bind:value={opacity} />
      </label>
      <span class="text-slate-400">{opacity.toFixed(2)}</span>
    {/if}
  </div>

  <div class="grid grid-cols-3 gap-2">
    <div>
      <h5 class="text-[11px] text-slate-500 mb-1">Input</h5>
      <NiiVueViewer
        volumeUrl={inputUrl}
        overlayUrl={overlay && predictionUrl ? predictionUrl : undefined}
        overlayOpacity={opacity}
      />
    </div>
    <div>
      <h5 class="text-[11px] text-slate-500 mb-1">Ground truth</h5>
      {#if labelUrl}
        <NiiVueViewer volumeUrl={labelUrl} />
      {:else}
        <p class="text-xs text-slate-500 py-8 text-center">no GT label for this case</p>
      {/if}
    </div>
    <div>
      <h5 class="text-[11px] text-slate-500 mb-1">Prediction</h5>
      {#if predictionUrl}
        <NiiVueViewer volumeUrl={predictionUrl} />
      {:else}
        <p class="text-xs text-slate-500 py-8 text-center">no prediction available</p>
      {/if}
    </div>
  </div>
</div>
