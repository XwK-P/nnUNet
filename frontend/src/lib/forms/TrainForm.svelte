<script lang="ts">
  import { launchEndpoints } from '../api';
  import type { GpuInfo, TrainLaunchResponse } from '../types';
  import CliPreview from './CliPreview.svelte';

  let { datasetIdInt }: { datasetIdInt: number } = $props();

  let configuration = $state('3d_fullres');
  let folds = $state<string[]>(['0']);
  let trainer = $state('');
  let plans = $state('');
  let num_gpus = $state(1);
  let npz = $state(false);
  let cont = $state(false);
  let lines = $state<{ cli: string; fold: string }[]>([]);
  let gpu = $state<GpuInfo[]>([]);
  let jobIds = $state<number[]>([]);
  let submitting = $state(false);
  let error = $state<string | null>(null);

  const CONFIGS = ['2d', '3d_fullres', '3d_lowres', '3d_cascade_fullres'];
  const ALL_FOLDS = ['0', '1', '2', '3', '4', 'all'];

  function toggleFold(f: string) {
    folds = folds.includes(f) ? folds.filter((x) => x !== f) : [...folds, f];
  }

  function selectConfig(c: string) {
    configuration = c;
  }

  $effect(() => {
    launchEndpoints
      .postTrain(
        {
          dataset_id: datasetIdInt,
          configuration,
          folds,
          trainer: trainer || undefined,
          plans: plans || undefined,
          num_gpus,
          npz,
          continue_training: cont,
        },
        true,
      )
      .then((r: TrainLaunchResponse) => {
        lines = r.jobs.map((j, i) => ({ cli: j.cli, fold: folds[i] }));
      })
      .catch(() => {
        lines = [];
      });
  });

  // Pull GPU info once
  $effect(() => {
    launchEndpoints
      .getGpuInfo()
      .then((g) => {
        gpu = g;
      })
      .catch(() => {
        gpu = [];
      });
  });

  // Rough projection: nnUNetTrainer default ~11 GB / GPU.
  const projectedMb = $derived(num_gpus * 11000);
  const freeMb = $derived(
    gpu.reduce((s, g) => s + Math.max(0, g.memory_total_mb - g.memory_used_mb), 0),
  );
  const gpuWarn = $derived(gpu.length > 0 && projectedMb > freeMb);

  async function submit() {
    submitting = true;
    error = null;
    try {
      const r: TrainLaunchResponse = await launchEndpoints.postTrain({
        dataset_id: datasetIdInt,
        configuration,
        folds,
        trainer: trainer || undefined,
        plans: plans || undefined,
        num_gpus,
        npz,
        continue_training: cont,
      });
      jobIds = r.job_ids ?? [];
    } catch (e: unknown) {
      error = (e as Error).message;
    } finally {
      submitting = false;
    }
  }
</script>

<div class="space-y-3 text-xs">
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
      >Trainer
      <input
        class="bg-bg-panel border border-border-soft rounded px-1 py-0.5 ml-1"
        bind:value={trainer}
        placeholder="nnUNetTrainer"
      />
    </label>
    <label
      >Plans
      <input
        class="bg-bg-panel border border-border-soft rounded px-1 py-0.5 ml-1"
        bind:value={plans}
        placeholder="nnUNetPlans"
      />
    </label>
    <label
      >num_gpus
      <input
        type="number"
        min="1"
        class="bg-bg-panel border border-border-soft rounded px-1 py-0.5 ml-1 w-12"
        bind:value={num_gpus}
      />
    </label>
  </div>

  <div class="text-slate-300">
    <label class="mr-3"><input type="checkbox" bind:checked={npz} /> --npz</label>
    <label><input type="checkbox" bind:checked={cont} /> continue (--c)</label>
  </div>

  {#if gpuWarn}
    <p class="text-amber-400">
      GPU warning: projected ~{projectedMb} MB &gt; free ~{freeMb} MB
    </p>
  {/if}

  <div class="space-y-1">
    {#each lines as l}
      <CliPreview cli={l.cli} />
    {/each}
  </div>

  <button
    type="button"
    class="px-3 py-1 bg-accent rounded text-white disabled:opacity-50"
    disabled={submitting || folds.length === 0}
    onclick={submit}
  >
    {submitting ? 'Queueing…' : `Launch ${folds.length} fold${folds.length > 1 ? 's' : ''}`}
  </button>
  {#if jobIds.length}<p class="text-ok">Queued jobs: {jobIds.join(', ')}</p>{/if}
  {#if error}<p class="text-err">{error}</p>{/if}
</div>
