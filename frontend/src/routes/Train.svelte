<script lang="ts">
  import { onMount } from 'svelte';
  import { createDatasetsStore } from '../lib/stores/datasets';
  import { createWorkspaceStore } from '../lib/stores/workspace';
  import TrainForm from '../lib/forms/TrainForm.svelte';

  const ws = createWorkspaceStore();
  const ds = createDatasetsStore();
  let workspaceId = $state<string | null>(ws.get());
  let dsState = $state(ds.get());

  onMount(() => {
    const u1 = ws.subscribe((v) => (workspaceId = v));
    const u2 = ds.subscribe((s) => (dsState = s));
    ds.load();
    return () => {
      u1();
      u2();
    };
  });

  const datasetIntFor = $derived.by(() => {
    if (!workspaceId || dsState.kind !== 'loaded') return null;
    const m = dsState.data.find((d) => d.id === workspaceId);
    return m?.dataset_id_int ?? null;
  });
</script>

<h2 class="text-lg font-semibold text-slate-100">Train</h2>
{#if !workspaceId}
  <p class="text-xs text-slate-400 mt-2">Pick a dataset in the header first.</p>
{:else if dsState.kind !== 'loaded'}
  <p class="text-xs text-slate-500 mt-2">Loading dataset…</p>
{:else if datasetIntFor === null}
  <p class="text-xs text-amber-400 mt-2">
    Dataset has no numeric id (dataset_id_int) so it can't be used by nnUNetv2_train.
  </p>
{:else}
  <div class="mt-4 max-w-2xl">
    <TrainForm datasetIdInt={datasetIntFor} />
  </div>
{/if}
