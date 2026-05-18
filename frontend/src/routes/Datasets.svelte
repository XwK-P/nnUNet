<script lang="ts">
  import { onMount } from 'svelte';
  import DatasetList from '../components/DatasetList.svelte';
  import DatasetDetail from '../components/DatasetDetail.svelte';
  import { createWorkspaceStore } from '../lib/stores/workspace';
  import type { Dataset } from '../lib/types';

  const ws = createWorkspaceStore();
  let selectedId = $state<string | null>(ws.get());

  onMount(() => ws.subscribe((v) => (selectedId = v)));

  function onSelect(d: Dataset): void {
    ws.set(d.id);
  }
</script>

<h2 class="text-lg font-semibold text-slate-100">Datasets</h2>
<div class="mt-4 flex gap-3">
  <div class="w-56 flex-shrink-0">
    <DatasetList {selectedId} {onSelect} />
  </div>
  <div class="flex-1 min-w-0">
    {#if selectedId}
      <DatasetDetail datasetId={selectedId} />
    {:else}
      <p class="text-sm text-slate-400">Pick a dataset on the left, or pick one from the Workspace switcher in the header.</p>
    {/if}
  </div>
</div>
