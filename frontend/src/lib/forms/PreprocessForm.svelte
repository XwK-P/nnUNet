<script lang="ts">
  import { launchEndpoints } from '../api';
  import type { PreprocessLaunchResponse } from '../types';
  import CliPreview from './CliPreview.svelte';

  let { datasetIdInt }: { datasetIdInt: number } = $props();

  let planner = $state<string>('');
  let verify = $state(true);
  let cli = $state<string>('');
  let submitting = $state(false);
  let error = $state<string | null>(null);
  let jobId = $state<number | null>(null);

  $effect(() => {
    // Re-render preview on every state change.
    launchEndpoints
      .postPreprocess(
        {
          dataset_id: datasetIdInt,
          verify_dataset_integrity: verify,
          planner: planner || undefined,
        },
        true,
      )
      .then((r: PreprocessLaunchResponse) => {
        cli = r.cli ?? '';
      })
      .catch(() => {
        cli = '';
      });
  });

  async function submit() {
    submitting = true;
    error = null;
    try {
      const r: PreprocessLaunchResponse = await launchEndpoints.postPreprocess({
        dataset_id: datasetIdInt,
        verify_dataset_integrity: verify,
        planner: planner || undefined,
      });
      jobId = r.job_id ?? null;
    } catch (e: unknown) {
      error = (e as Error).message;
    } finally {
      submitting = false;
    }
  }
</script>

<div class="space-y-3">
  <label class="block text-xs text-slate-300">
    Planner
    <select
      class="bg-bg-panel border border-border-soft rounded px-1 py-0.5 ml-1"
      bind:value={planner}
    >
      <option value="">Default</option>
      <option value="nnUNetPlannerResEncM">ResEnc M (~10 GB)</option>
      <option value="nnUNetPlannerResEncL">ResEnc L (~24 GB)</option>
      <option value="nnUNetPlannerResEncXL">ResEnc XL (~40 GB)</option>
    </select>
  </label>
  <label class="block text-xs text-slate-300">
    <input type="checkbox" bind:checked={verify} /> Verify dataset integrity
  </label>
  {#if cli}<CliPreview {cli} />{/if}
  <button
    type="button"
    class="px-3 py-1 bg-accent rounded text-white text-xs disabled:opacity-50"
    disabled={submitting}
    onclick={submit}
  >
    {submitting ? 'Launching…' : 'Launch preprocess'}
  </button>
  {#if jobId}<p class="text-xs text-ok">Queued as job #{jobId}</p>{/if}
  {#if error}<p class="text-xs text-err">{error}</p>{/if}
</div>
