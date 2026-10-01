<script lang="ts">
  import { endpoints } from '../lib/api';

  let datasetId = $state<number>(27);
  let configurations = $state<string>('2d 3d_fullres 3d_lowres');
  let disableEnsembling = $state(false);
  let busy = $state(false);
  let result = $state<string | null>(null);
  let error = $state<string | null>(null);

  async function submit(): Promise<void> {
    busy = true;
    error = null;
    result = null;
    try {
      const res = await endpoints.postFindBest({
        dataset_id: datasetId,
        configurations: configurations.split(/\s+/).filter(Boolean),
        disable_ensembling: disableEnsembling,
      });
      result = `Job #${res.job_id} queued — see Jobs page`;
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      busy = false;
    }
  }
</script>

<div class="bg-bg-soft border border-border-soft rounded p-3">
  <h4 class="text-xs uppercase tracking-wider text-slate-500 mb-2">find_best_configuration</h4>
  <div class="grid grid-cols-[120px_1fr] gap-2 text-xs">
    <label class="text-slate-500 self-center" for="fb-dataset-id">Dataset ID</label>
    <input
      id="fb-dataset-id"
      class="bg-bg-panel border border-border-soft rounded px-2 py-0.5 text-slate-200"
      type="number"
      bind:value={datasetId}
    />
    <label class="text-slate-500 self-center" for="fb-configs">Configurations</label>
    <input
      id="fb-configs"
      class="bg-bg-panel border border-border-soft rounded px-2 py-0.5 text-slate-200"
      bind:value={configurations}
      placeholder="2d 3d_fullres"
    />
    <span></span>
    <label class="text-slate-300 flex items-center gap-1">
      <input type="checkbox" bind:checked={disableEnsembling} /> --disable_ensembling
    </label>
  </div>
  <div class="mt-3 flex gap-2 items-center">
    <button
      type="button"
      class="text-xs bg-accent text-bg-base px-3 py-1 rounded"
      disabled={busy}
      onclick={submit}
    >
      {busy ? 'Queuing…' : 'Run find_best_configuration'}
    </button>
    {#if result}<span class="text-[11px] text-ok">{result}</span>{/if}
    {#if error}<span class="text-[11px] text-err">{error}</span>{/if}
  </div>
</div>
