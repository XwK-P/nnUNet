<script lang="ts">
  import { onMount } from 'svelte';
  import RunsTable from '../components/RunsTable.svelte';
  import RunDetail from '../components/RunDetail.svelte';
  import { createWorkspaceStore } from '../lib/stores/workspace';
  import type { Run, RunFilter } from '../lib/types';

  const ws = createWorkspaceStore();
  let workspaceId = $state<string | null>(ws.get());
  onMount(() => ws.subscribe((v) => (workspaceId = v)));
  let filter = $derived<RunFilter>(workspaceId ? { dataset_id: workspaceId } : {});

  let selected = $state<Run | null>(null);
</script>

<h2 class="text-lg font-semibold text-slate-100">Monitor</h2>
<p class="text-xs text-amber-400 mt-1">Live curves + log tail land in Phase 3. Phase 2 adds prediction review for completed runs.</p>

<div class="mt-4 grid grid-cols-12 gap-3">
  <div class="col-span-7 min-w-0">
    <RunsTable {filter} onSelect={(r) => (selected = r)} />
  </div>
  <div class="col-span-5 min-w-0">
    {#if selected}
      <RunDetail run={selected} />
    {:else}
      <p class="text-xs text-slate-500">Pick a run on the left to inspect predictions.</p>
    {/if}
  </div>
</div>
