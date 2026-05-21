<script lang="ts">
  import { imageEndpoints } from '../lib/api';
  import Canvas2DViewer from '../lib/viewer/Canvas2DViewer.svelte';
  import type { Prediction } from '../lib/types';

  let { runId }: { runId: string } = $props();
  let preds = $state<Prediction[]>([]);
  let selected = $state<Prediction | null>(null);
  let axis = $state(0);
  let slice = $state(0);
  let loading = $state(false);
  let error = $state<string | null>(null);
  let shape = $state<[number, number, number] | null>(null);

  async function load(id: string) {
    loading = true; error = null;
    try {
      preds = await imageEndpoints.getPredictions(id);
    } catch (e: unknown) {
      error = (e as Error).message;
    } finally {
      loading = false;
    }
  }

  // Single source of truth: $effect runs on mount AND whenever runId
  // changes. The previous code also called load() from onMount, so the
  // predictions endpoint fired twice on first render — wasted backend
  // load plus a flicker if the two requests resolved in reverse order.
  $effect(() => {
    if (runId) load(runId);
  });

  // Reset the shape + slice when the user picks a new case, then fetch
  // the actual volume dimensions so the slider's max is dataset-aware
  // rather than capped at 255.
  $effect(() => {
    const sel = selected;
    if (!sel || !runId) {
      shape = null;
      return;
    }
    shape = null;
    slice = 0;
    imageEndpoints
      .getPredictionShape(runId, sel.case_id)
      .then((res) => {
        shape = res.shape;
      })
      .catch(() => {
        shape = null;
      });
  });

  // Derived slider bound. While shape is unknown (initial fetch in
  // flight or the format doesn't expose shape), keep the slider
  // disabled by collapsing max to 0 so the user doesn't pick an index
  // that gets silently clamped server-side.
  const sliceMax = $derived(shape ? Math.max(0, shape[axis] - 1) : 0);

  const previewUrl = $derived(
    selected ? imageEndpoints.getPredictionPreviewUrl(runId, selected.case_id, { axis, slice }) : null
  );
</script>

<div class="space-y-2">
  <h4 class="text-xs uppercase tracking-wider text-slate-500">Predictions</h4>
  {#if loading}
    <p class="text-xs text-slate-500">Loading…</p>
  {:else if error}
    <p class="text-xs text-err">{error}</p>
  {:else if preds.length === 0}
    <p class="text-xs text-slate-500">No predictions on disk for this run yet. (Phase 4 will let you launch predict from the GUI.)</p>
  {:else}
    <div class="flex gap-3">
      <ul class="text-xs w-48">
        {#each preds as p}
          <li>
            <button
              class="block w-full text-left px-2 py-1 rounded hover:bg-bg-panel"
              class:text-accent={selected?.case_id === p.case_id}
              class:text-slate-300={selected?.case_id !== p.case_id}
              onclick={() => (selected = p)}
            >
              {p.case_id}
            </button>
          </li>
        {/each}
      </ul>
      <div class="flex-1 min-w-0">
        {#if selected && previewUrl}
          <div class="flex gap-2 text-xs items-center mb-2">
            <label>Axis <select class="bg-bg-panel border border-border-soft rounded px-1 py-0.5" bind:value={axis}>
              <option value={0}>Z</option><option value={1}>Y</option><option value={2}>X</option>
            </select></label>
            <label class="flex-1 flex items-center gap-2">Slice
              <input
                type="range"
                min="0"
                max={sliceMax}
                bind:value={slice}
                disabled={shape === null}
                class="flex-1"
              />
              <span class="w-12 text-right">{shape ? `${slice}/${sliceMax}` : '…'}</span>
            </label>
          </div>
          <Canvas2DViewer src={previewUrl} alt={selected.case_id} />
        {:else}
          <p class="text-xs text-slate-500">Pick a case to preview.</p>
        {/if}
      </div>
    </div>
  {/if}
</div>
