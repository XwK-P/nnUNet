<script lang="ts">
  import { onMount } from 'svelte';
  import { createDatasetsStore } from '../lib/stores/datasets';
  import type { Dataset } from '../lib/types';

  let { selectedId, onSelect }: { selectedId: string | null; onSelect: (d: Dataset) => void } = $props();

  const datasets = createDatasetsStore();
  let state = $state(datasets.get());

  onMount(() => {
    const unsub = datasets.subscribe((s) => (state = s));
    datasets.load();
    return unsub;
  });
</script>

<div class="bg-bg-soft border border-border-soft rounded p-2">
  <h3 class="text-xs uppercase tracking-wider text-slate-500 px-2 py-1">All datasets</h3>
  {#if state.kind === 'loading' || state.kind === 'idle'}
    <p class="px-2 py-1 text-xs text-slate-500">Loading…</p>
  {:else if state.kind === 'error'}
    <p class="px-2 py-1 text-xs text-err">{state.error.message}</p>
  {:else if state.data.length === 0}
    <p class="px-2 py-1 text-xs text-slate-500">No datasets in nnUNet_raw</p>
  {:else}
    <ul class="text-xs">
      {#each state.data as d}
        <li>
          <button
            class="block w-full text-left px-2 py-1 rounded hover:bg-bg-panel"
            class:text-accent={d.id === selectedId}
            class:text-slate-300={d.id !== selectedId}
            onclick={() => onSelect(d)}
          >
            {d.id}
            {#if d.preprocessed_path}
              <span class="text-ok ml-1" title="preprocessed">✓</span>
            {:else}
              <span class="text-slate-600 ml-1" title="raw only">◯</span>
            {/if}
          </button>
        </li>
      {/each}
    </ul>
  {/if}
</div>
