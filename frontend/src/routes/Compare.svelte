<script lang="ts">
  import { onMount } from 'svelte';
  import RunSelector from '../components/RunSelector.svelte';
  import OverlayChart from '../components/OverlayChart.svelte';
  import ComparisonTable from '../components/ComparisonTable.svelte';
  import { createCompareStore } from '../lib/stores/compare';

  const cmp = createCompareStore();
  let s = $state(cmp.get());
  let selected = $state<string[]>([]);

  onMount(() => cmp.subscribe((next) => (s = next)));

  function setSelected(ids: string[]): void {
    selected = ids;
    if (ids.length === 0) return;
    cmp.load(ids);
  }
</script>

<h2 class="text-lg font-semibold text-slate-100">Compare</h2>
<p class="text-xs text-slate-500 mt-1">
  Aggregate metric history + summary stats across runs. Reads each run's
  <code class="text-slate-400">tensorboard/</code> events on demand.
</p>

<div class="mt-4 grid grid-cols-1 xl:grid-cols-[280px_1fr] gap-4">
  <RunSelector value={selected} onChange={setSelected} />

  <div class="space-y-4 min-w-0">
    {#if s.kind === 'loading'}
      <p class="text-sm text-slate-400">Loading metrics…</p>
    {:else if s.kind === 'error'}
      <p class="text-sm text-err">{s.error.message}</p>
    {:else if s.kind === 'loaded'}
      <OverlayChart metrics={s.data.metrics} />
      <ComparisonTable summaries={s.data.summaries} />
    {:else if selected.length === 0}
      <p class="text-sm text-slate-400">Pick runs on the left to compare them.</p>
    {/if}
  </div>
</div>
