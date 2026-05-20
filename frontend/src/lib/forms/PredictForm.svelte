<script lang="ts">
  import { launchEndpoints } from '../api';
  import type { PredictLaunchResponse } from '../types';
  import CliPreview from './CliPreview.svelte';

  let { datasetIdInt }: { datasetIdInt: number } = $props();

  let configuration = $state('3d_fullres');
  let inputFolder = $state('');
  let outputFolder = $state('');
  // Default to the 5-fold CV ensemble — matches nnUNet's documented
  // default when -f is not passed. Selecting 'all' instead would render
  // `-f all`, which means "load fold_all" specifically (and fails for
  // models that only have fold_0..fold_4 on disk).
  let folds = $state<string[]>(['0', '1', '2', '3', '4']);
  let checkpoint = $state<'checkpoint_final' | 'checkpoint_best'>('checkpoint_final');
  let stepSize = $state(0.5);
  let disableTta = $state(false);
  let saveProbabilities = $state(false);
  let device = $state<'cuda' | 'cpu' | 'mps'>('cuda');
  let cli = $state<string>('');
  let submitting = $state(false);
  let error = $state<string | null>(null);
  let jobId = $state<number | null>(null);

  const CONFIGS = ['2d', '3d_fullres', '3d_lowres', '3d_cascade_fullres'];
  const ALL_FOLDS = ['0', '1', '2', '3', '4', 'all'];

  function toggleFold(f: string) {
    folds = folds.includes(f) ? folds.filter((x) => x !== f) : [...folds, f];
  }

  function selectConfig(c: string) {
    configuration = c;
  }

  $effect(() => {
    // Need both folders for a meaningful preview.
    if (!inputFolder || !outputFolder) {
      cli = '';
      return;
    }
    launchEndpoints
      .postPredict(
        {
          dataset_id: datasetIdInt,
          configuration,
          input_folder: inputFolder,
          output_folder: outputFolder,
          folds,
          checkpoint,
          step_size: stepSize,
          disable_tta: disableTta,
          save_probabilities: saveProbabilities,
          device,
        },
        true,
      )
      .then((r: PredictLaunchResponse) => {
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
      const r: PredictLaunchResponse = await launchEndpoints.postPredict({
        dataset_id: datasetIdInt,
        configuration,
        input_folder: inputFolder,
        output_folder: outputFolder,
        folds,
        checkpoint,
        step_size: stepSize,
        disable_tta: disableTta,
        save_probabilities: saveProbabilities,
        device,
      });
      jobId = r.job_id ?? null;
    } catch (e: unknown) {
      error = (e as Error).message;
    } finally {
      submitting = false;
    }
  }
</script>

<div class="space-y-3 text-xs">
  <div class="grid grid-cols-1 gap-2">
    <label class="block text-slate-300"
      >Input folder
      <input
        class="bg-bg-panel border border-border-soft rounded px-1 py-0.5 ml-1 w-full max-w-md font-mono"
        bind:value={inputFolder}
        placeholder="/path/to/input"
      />
    </label>
    <label class="block text-slate-300"
      >Output folder
      <input
        class="bg-bg-panel border border-border-soft rounded px-1 py-0.5 ml-1 w-full max-w-md font-mono"
        bind:value={outputFolder}
        placeholder="/path/to/output"
      />
    </label>
  </div>

  <div class="flex flex-wrap gap-1 items-center">
    <span class="text-slate-400 mr-1">Configuration:</span>
    {#each CONFIGS as c}
      <button
        type="button"
        class="px-2 py-0.5 rounded"
        class:bg-accent={configuration === c}
        class:text-white={configuration === c}
        class:bg-bg-panel={configuration !== c}
        class:text-slate-300={configuration !== c}
        onclick={() => selectConfig(c)}>{c}</button
      >
    {/each}
  </div>

  <div class="flex flex-wrap gap-1 items-center">
    <span class="text-slate-400 mr-1">Folds:</span>
    {#each ALL_FOLDS as f}
      <button
        type="button"
        class="px-2 py-0.5 rounded"
        class:bg-accent={folds.includes(f)}
        class:text-white={folds.includes(f)}
        class:bg-bg-panel={!folds.includes(f)}
        class:text-slate-300={!folds.includes(f)}
        onclick={() => toggleFold(f)}>{f}</button
      >
    {/each}
  </div>

  <div class="flex flex-wrap gap-3 text-slate-300">
    <label
      >Checkpoint
      <select
        class="bg-bg-panel border border-border-soft rounded px-1 py-0.5 ml-1"
        bind:value={checkpoint}
      >
        <option value="checkpoint_final">final</option>
        <option value="checkpoint_best">best</option>
      </select>
    </label>
    <label
      >Step size
      <input
        type="number"
        min="0.01"
        max="1"
        step="0.05"
        class="bg-bg-panel border border-border-soft rounded px-1 py-0.5 ml-1 w-16"
        bind:value={stepSize}
      />
    </label>
    <label
      >Device
      <select
        class="bg-bg-panel border border-border-soft rounded px-1 py-0.5 ml-1"
        bind:value={device}
      >
        <option value="cuda">cuda</option>
        <option value="cpu">cpu</option>
        <option value="mps">mps</option>
      </select>
    </label>
  </div>

  <div class="text-slate-300">
    <label class="mr-3"
      ><input type="checkbox" bind:checked={disableTta} /> --disable_tta</label
    >
    <label
      ><input type="checkbox" bind:checked={saveProbabilities} /> --save_probabilities</label
    >
  </div>

  {#if cli}
    <CliPreview {cli} />
  {:else}
    <p class="text-slate-500 italic">Enter input and output folders to preview the CLI.</p>
  {/if}

  <button
    type="button"
    class="px-3 py-1 bg-accent rounded text-white disabled:opacity-50"
    disabled={submitting || !inputFolder || !outputFolder || folds.length === 0}
    onclick={submit}
  >
    {submitting ? 'Queueing…' : 'Launch predict'}
  </button>
  {#if jobId}<p class="text-ok">Queued as job #{jobId}</p>{/if}
  {#if error}<p class="text-err">{error}</p>{/if}
</div>
