<script lang="ts">
  import { endpoints } from '../lib/api';

  let inputFolder = $state<string>('');
  let outputFolder = $state<string>('');
  let ppPkl = $state<string>('');
  let plansJson = $state<string>('');
  let datasetJson = $state<string>('');
  let busy = $state(false);
  let result = $state<string | null>(null);
  let error = $state<string | null>(null);

  async function submit(): Promise<void> {
    busy = true;
    error = null;
    result = null;
    try {
      const res = await endpoints.postPostproc({
        input_folder: inputFolder,
        output_folder: outputFolder,
        pp_pkl_file: ppPkl,
        plans_json: plansJson || undefined,
        dataset_json: datasetJson || undefined,
      });
      result = `Job #${res.job_id} queued`;
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      busy = false;
    }
  }
</script>

<div class="bg-bg-soft border border-border-soft rounded p-3">
  <h4 class="text-xs uppercase tracking-wider text-slate-500 mb-2">Apply postprocessing</h4>
  <div class="grid grid-cols-[120px_1fr] gap-2 text-xs">
    <label class="text-slate-500 self-center" for="pp-input">Input folder</label>
    <input
      id="pp-input"
      class="bg-bg-panel border border-border-soft rounded px-2 py-0.5 text-slate-200"
      bind:value={inputFolder}
    />
    <label class="text-slate-500 self-center" for="pp-output">Output folder</label>
    <input
      id="pp-output"
      class="bg-bg-panel border border-border-soft rounded px-2 py-0.5 text-slate-200"
      bind:value={outputFolder}
    />
    <label class="text-slate-500 self-center" for="pp-pkl">pp.pkl</label>
    <input
      id="pp-pkl"
      class="bg-bg-panel border border-border-soft rounded px-2 py-0.5 text-slate-200"
      bind:value={ppPkl}
    />
    <label class="text-slate-500 self-center" for="pp-plans">plans.json</label>
    <input
      id="pp-plans"
      class="bg-bg-panel border border-border-soft rounded px-2 py-0.5 text-slate-200"
      bind:value={plansJson}
    />
    <label class="text-slate-500 self-center" for="pp-dataset">dataset.json</label>
    <input
      id="pp-dataset"
      class="bg-bg-panel border border-border-soft rounded px-2 py-0.5 text-slate-200"
      bind:value={datasetJson}
    />
  </div>
  <div class="mt-3 flex gap-2 items-center">
    <button
      type="button"
      class="text-xs bg-accent text-bg-base px-3 py-1 rounded"
      disabled={busy}
      onclick={submit}
    >
      {busy ? 'Queuing…' : 'Apply postprocessing'}
    </button>
    {#if result}<span class="text-[11px] text-ok">{result}</span>{/if}
    {#if error}<span class="text-[11px] text-err">{error}</span>{/if}
  </div>
</div>
