<script lang="ts">
  import { onMount } from 'svelte';
  import { createDatasetsStore } from '../lib/stores/datasets';
  import { createWorkspaceStore } from '../lib/stores/workspace';
  import { imageEndpoints } from '../lib/api';
  import PredictForm from '../lib/forms/PredictForm.svelte';
  import PredictPaneViewer from '../components/PredictPaneViewer.svelte';
  import PerCaseMetricsTable from '../components/PerCaseMetricsTable.svelte';

  const ws = createWorkspaceStore();
  const ds = createDatasetsStore();
  let workspaceId = $state<string | null>(ws.get());
  let dsState = $state(ds.get());

  let predictionFolder = $state<string>('');
  let selectedCase = $state<string | null>(null);
  let axis = $state(0);
  let slice = $state(0);

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

  // URLs for the 3-pane viewer. The Predict page works against an
  // arbitrary predictionFolder (not a managed Run), so prediction URLs
  // go through the folder-scoped endpoint; the input/label panes reuse
  // the dataset-scoped endpoints because the case_id matches.
  const inputUrl = $derived(
    workspaceId && selectedCase
      ? imageEndpoints.getCasePreviewUrl(workspaceId, selectedCase, { axis, slice, channel: 0 })
      : null,
  );
  const labelUrl = $derived(
    workspaceId && selectedCase
      ? imageEndpoints.getCaseLabelsUrl(workspaceId, selectedCase, { axis, slice })
      : null,
  );
  const predictionUrl = $derived(
    predictionFolder && selectedCase
      ? imageEndpoints.getPredictPreviewByFolderUrl(predictionFolder, selectedCase, { axis, slice })
      : null,
  );
</script>

<h2 class="text-lg font-semibold text-slate-100">Predict</h2>
{#if !workspaceId}
  <p class="text-xs text-slate-400 mt-2">Pick a dataset in the header first.</p>
{:else if dsState.kind !== 'loaded'}
  <p class="text-xs text-slate-500 mt-2">Loading dataset…</p>
{:else if datasetIntFor === null}
  <p class="text-xs text-amber-400 mt-2">
    Dataset has no numeric id (dataset_id_int) so it can't be used by nnUNetv2_predict.
  </p>
{:else}
  <div class="mt-4 grid grid-cols-1 xl:grid-cols-[1fr_1fr] gap-4">
    <PredictForm datasetIdInt={datasetIntFor} />

    <div class="space-y-3">
      <div class="bg-bg-soft border border-border-soft rounded p-3">
        <h4 class="text-xs uppercase tracking-wider text-slate-500 mb-2">Review predictions</h4>
        <label class="block text-xs text-slate-500 mb-1" for="predict-folder">Prediction folder</label>
        <input
          id="predict-folder"
          class="w-full bg-bg-panel border border-border-soft rounded px-2 py-1 text-sm text-slate-100"
          bind:value={predictionFolder}
          placeholder="/abs/path/predictions"
        />
      </div>

      {#if predictionFolder}
        <PredictPaneViewer
          {inputUrl}
          {labelUrl}
          {predictionUrl}
          bind:axis
          bind:slice
        />
        <PerCaseMetricsTable
          {predictionFolder}
          {selectedCase}
          onSelectCase={(c) => (selectedCase = c)}
        />
      {/if}
    </div>
  </div>
{/if}
