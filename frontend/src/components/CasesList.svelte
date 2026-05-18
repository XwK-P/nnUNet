<script lang="ts">
  import { onMount } from 'svelte';
  import { createCasesStore } from '../lib/stores/cases';
  import type { Case } from '../lib/types';

  let { datasetId, selectedId, onSelect }: {
    datasetId: string;
    selectedId: string | null;
    onSelect: (c: Case) => void;
  } = $props();

  const cases = createCasesStore();
  let result = $state(cases.get());

  onMount(() => {
    const unsub = cases.subscribe((s) => (result = s));
    cases.load(datasetId);
    return unsub;
  });

  $effect(() => { cases.load(datasetId); });
</script>

<div class="bg-bg-soft border border-border-soft rounded p-2">
  <h4 class="text-xs uppercase tracking-wider text-slate-500 px-2 py-1">Cases</h4>
  {#if result.kind === 'loading' || result.kind === 'idle'}
    <p class="px-2 py-1 text-xs text-slate-500">Loading…</p>
  {:else if result.kind === 'error'}
    <p class="px-2 py-1 text-xs text-err">{result.error.message}</p>
  {:else if result.data.length === 0}
    <p class="px-2 py-1 text-xs text-slate-500">No cases (imagesTr/ empty)</p>
  {:else}
    <ul class="text-xs max-h-80 overflow-auto">
      {#each result.data as c}
        <li>
          <button
            class="block w-full text-left px-2 py-1 rounded hover:bg-bg-panel"
            class:text-accent={c.id === selectedId}
            class:text-slate-300={c.id !== selectedId}
            onclick={() => onSelect(c)}
          >
            {c.id} <span class="text-slate-500">· {Object.keys(c.channels).length}ch{c.label_path ? ' · GT' : ''}</span>
          </button>
        </li>
      {/each}
    </ul>
  {/if}
</div>
