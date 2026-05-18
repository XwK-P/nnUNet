<script lang="ts">
  import { onMount } from 'svelte';
  import RunsTable from '../components/RunsTable.svelte';
  import { createWorkspaceStore } from '../lib/stores/workspace';
  import type { RunFilter } from '../lib/types';

  const ws = createWorkspaceStore();
  let workspaceId = $state<string | null>(ws.get());

  onMount(() => ws.subscribe((v) => (workspaceId = v)));

  let filter = $derived<RunFilter>(workspaceId ? { dataset_id: workspaceId } : {});
</script>

<h2 class="text-lg font-semibold text-slate-100">Monitor</h2>
<p class="text-xs text-amber-400 mt-1">Live curves + image samples + log tail land in Phase 3. Phase 1 shows the historical run list.</p>

<div class="mt-4">
  <RunsTable {filter} />
</div>
