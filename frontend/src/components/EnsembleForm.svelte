<script lang="ts">
  import { endpoints } from '../lib/api';

  let inputs = $state<string>('');
  let output = $state<string>('');
  let saveNpz = $state(false);
  let busy = $state(false);
  let result = $state<string | null>(null);
  let error = $state<string | null>(null);

  async function submit(): Promise<void> {
    busy = true;
    error = null;
    result = null;
    try {
      const res = await endpoints.postEnsemble({
        input_folders: inputs.split(/\s+/).filter(Boolean),
        output_folder: output,
        save_npz: saveNpz,
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
  <h4 class="text-xs uppercase tracking-wider text-slate-500 mb-2">Ensemble prediction folders</h4>
  <div class="grid grid-cols-[120px_1fr] gap-2 text-xs">
    <label class="text-slate-500 self-center" for="ens-inputs">Input folders</label>
    <input
      id="ens-inputs"
      class="bg-bg-panel border border-border-soft rounded px-2 py-0.5 text-slate-200"
      bind:value={inputs}
      placeholder="/preds_3d /preds_2d (space-separated)"
    />
    <label class="text-slate-500 self-center" for="ens-output">Output folder</label>
    <input
      id="ens-output"
      class="bg-bg-panel border border-border-soft rounded px-2 py-0.5 text-slate-200"
      bind:value={output}
      placeholder="/preds_ensemble"
    />
    <span></span>
    <label class="text-slate-300 flex items-center gap-1">
      <input type="checkbox" bind:checked={saveNpz} /> --save_npz
    </label>
  </div>
  <div class="mt-3 flex gap-2 items-center">
    <button
      type="button"
      class="text-xs bg-accent text-bg-base px-3 py-1 rounded"
      disabled={busy}
      onclick={submit}
    >
      {busy ? 'Queuing…' : 'Run nnUNetv2_ensemble'}
    </button>
    {#if result}<span class="text-[11px] text-ok">{result}</span>{/if}
    {#if error}<span class="text-[11px] text-err">{error}</span>{/if}
  </div>
</div>
