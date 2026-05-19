<script lang="ts">
  import PredictionList from './PredictionList.svelte';
  import CurvesPanel from './CurvesPanel.svelte';
  import LogPanel from './LogPanel.svelte';
  import ImageSamplesPanel from './ImageSamplesPanel.svelte';
  import type { Run } from '../lib/types';

  let { run }: { run: Run } = $props();

  type Tab = 'curves' | 'log' | 'samples' | 'predictions';
  let manualTab = $state<Tab | null>(null);
  let tab = $derived<Tab>(
    manualTab ?? (run.status === 'completed' ? 'predictions' : 'curves'),
  );

  const TABS: { id: Tab; label: string }[] = [
    { id: 'curves', label: 'Curves' },
    { id: 'log', label: 'Log' },
    { id: 'samples', label: 'Image samples' },
    { id: 'predictions', label: 'Predictions' },
  ];
</script>

<div class="bg-bg-soft border border-border-soft rounded p-3 mb-3">
  <div class="flex items-center gap-2 text-xs">
    <strong class="text-slate-100">{run.dataset_id}</strong>
    <span class="text-slate-500">·</span>
    <span class="text-slate-300">{run.plans_name} · {run.trainer_name} · {run.configuration}</span>
    <span class="text-slate-500">·</span>
    <span class="text-slate-300">fold_{run.fold}</span>
    <span
      class="ml-auto text-xs"
      class:text-ok={run.status === 'completed'}
      class:text-slate-500={run.status !== 'completed'}
    >
      {run.status}
    </span>
  </div>
</div>

<div class="bg-bg-soft border border-border-soft rounded p-3">
  <div class="flex gap-1 border-b border-border-soft pb-2 mb-3">
    {#each TABS as t}
      <button
        type="button"
        class="px-3 py-1 text-xs rounded transition-colors"
        class:bg-bg-panel={tab === t.id}
        class:text-slate-100={tab === t.id}
        class:text-slate-500={tab !== t.id}
        onclick={() => (manualTab = t.id)}
      >
        {t.label}
      </button>
    {/each}
  </div>

  {#if tab === 'curves'}
    <CurvesPanel runId={run.id} />
  {:else if tab === 'log'}
    <LogPanel runId={run.id} />
  {:else if tab === 'samples'}
    <ImageSamplesPanel runId={run.id} />
  {:else if tab === 'predictions'}
    <PredictionList runId={run.id} />
  {/if}
</div>
