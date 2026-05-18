<script lang="ts">
  import { onMount } from 'svelte';
  import { endpoints, ApiError } from '../lib/api';
  import type { Dataset } from '../lib/types';
  import PlansViewer from './PlansViewer.svelte';
  import FingerprintViewer from './FingerprintViewer.svelte';

  let { datasetId }: { datasetId: string } = $props();

  type Tab = 'cases' | 'plans' | 'fingerprint' | 'validation';
  let tab = $state<Tab>('cases');

  let s = $state<
    | { kind: 'idle' }
    | { kind: 'loading' }
    | { kind: 'loaded'; data: Dataset }
    | { kind: 'error'; error: ApiError | Error }
  >({ kind: 'idle' });

  $effect(() => {
    s = { kind: 'loading' };
    endpoints
      .getDataset(datasetId)
      .then((data) => (s = { kind: 'loaded', data }))
      .catch((e) => (s = { kind: 'error', error: e }));
  });

  const TABS: { id: Tab; label: string }[] = [
    { id: 'cases', label: 'Cases' },
    { id: 'plans', label: 'Plans' },
    { id: 'fingerprint', label: 'Fingerprint' },
    { id: 'validation', label: 'Validation' },
  ];
</script>

{#if s.kind === 'loading' || s.kind === 'idle'}
  <p class="text-sm text-slate-400">Loading dataset…</p>
{:else if s.kind === 'error'}
  <p class="text-sm text-err">{s.error.message}</p>
{:else}
  <div class="bg-bg-soft border border-border-soft rounded p-3 mb-3">
    <div class="flex items-center gap-2">
      <strong class="text-sm text-slate-100">{s.data.id}</strong>
      <span class="text-xs bg-bg-panel px-2 py-0.5 rounded text-slate-400">{s.data.case_count ?? '?'} cases</span>
      <span class="text-xs bg-bg-panel px-2 py-0.5 rounded text-slate-400">{s.data.modality_count ?? '?'} modality(s)</span>
      {#if s.data.preprocessed_path}
        <span class="text-xs bg-emerald-900 text-emerald-200 px-2 py-0.5 rounded">✓ preprocessed</span>
      {:else}
        <span class="text-xs bg-bg-panel text-slate-500 px-2 py-0.5 rounded">raw only</span>
      {/if}
    </div>
  </div>

  <div class="bg-bg-soft border border-border-soft rounded p-3">
    <div class="flex gap-1 border-b border-border-soft pb-2 mb-3">
      {#each TABS as t}
        <button
          class="px-3 py-1 text-xs rounded"
          class:bg-bg-panel={tab === t.id}
          class:text-slate-100={tab === t.id}
          class:text-slate-500={tab !== t.id}
          onclick={() => (tab = t.id)}
        >
          {t.label}
        </button>
      {/each}
    </div>

    {#if tab === 'cases'}
      <p class="text-sm text-slate-400">Case browser + NiiVue viewer land in Phase 2.</p>
    {:else if tab === 'plans'}
      <PlansViewer datasetId={s.data.id} />
    {:else if tab === 'fingerprint'}
      <FingerprintViewer datasetId={s.data.id} />
    {:else if tab === 'validation'}
      <p class="text-sm text-slate-400">Dataset-integrity check lands later in Phase 1+.</p>
    {/if}
  </div>
{/if}
