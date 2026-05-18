<script lang="ts">
  import { onMount } from 'svelte';
  import { createDatasetsStore } from '../lib/stores/datasets';
  import { createWorkspaceStore } from '../lib/stores/workspace';
  import type { Dataset } from '../lib/types';

  const datasets = createDatasetsStore();
  const workspace = createWorkspaceStore();

  let ds = $state(datasets.get());
  let current = $state<string | null>(workspace.get());
  let open = $state(false);

  onMount(() => {
    const unsubDatasets = datasets.subscribe((s) => (ds = s));
    const unsubWorkspace = workspace.subscribe((v) => (current = v));
    datasets.load();
    return () => {
      unsubDatasets();
      unsubWorkspace();
    };
  });

  function select(d: Dataset): void {
    workspace.set(d.id);
    open = false;
  }

  function clear(): void {
    workspace.clear();
    open = false;
  }

  function options(): Dataset[] {
    if (ds.kind === 'loaded') return ds.data;
    return [];
  }
</script>

<div class="relative inline-block">
  <button
    class="bg-bg-soft px-2 py-0.5 rounded text-slate-400 hover:bg-bg-panel"
    onclick={() => (open = !open)}
  >
    Workspace: {current ?? '(none — pick a dataset)'} ▾
  </button>

  {#if open}
    <div class="absolute z-10 mt-1 min-w-[220px] bg-bg-panel border border-border-soft rounded shadow-lg text-xs">
      {#if ds.kind === 'loading'}
        <div class="px-3 py-2 text-slate-500">Loading…</div>
      {:else if ds.kind === 'error'}
        <div class="px-3 py-2 text-err">Failed to load datasets</div>
      {:else if options().length === 0}
        <div class="px-3 py-2 text-slate-500">No datasets found</div>
      {:else}
        {#each options() as d}
          <button
            class="block w-full text-left px-3 py-1.5 hover:bg-bg-soft"
            class:text-accent={current === d.id}
            onclick={() => select(d)}
          >
            {d.id}
            {#if d.preprocessed_path}<span class="text-ok ml-1">✓</span>{/if}
          </button>
        {/each}
      {/if}
      {#if current}
        <button class="block w-full text-left px-3 py-1.5 border-t border-border-soft text-slate-500 hover:bg-bg-soft" onclick={clear}>
          Clear workspace
        </button>
      {/if}
    </div>
  {/if}
</div>
