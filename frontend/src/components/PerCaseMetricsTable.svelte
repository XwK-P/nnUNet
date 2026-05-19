<script lang="ts">
  import { endpoints, ApiError } from '../lib/api';
  import type { PerCaseMetricsResponse, PerCaseMetric } from '../lib/types';

  let { predictionFolder }: { predictionFolder: string } = $props();

  type MetricsState =
    | { kind: 'idle' }
    | { kind: 'loading' }
    | { kind: 'loaded'; data: PerCaseMetricsResponse }
    | { kind: 'error'; error: ApiError | Error };

  let metricsState: MetricsState = $state({ kind: 'idle' });

  $effect(() => {
    if (!predictionFolder) return;
    metricsState = { kind: 'loading' };
    endpoints
      .getPerCaseMetrics(predictionFolder)
      .then((data) => (metricsState = { kind: 'loaded', data }))
      .catch((e) => (metricsState = { kind: 'error', error: e }));
  });

  type SortKey = 'case_id' | 'dice';
  let sortBy: SortKey = $state('dice');
  let sortDir: 'asc' | 'desc' = $state('desc');

  function sorted(cases: PerCaseMetric[]): PerCaseMetric[] {
    const mult = sortDir === 'asc' ? 1 : -1;
    return [...cases].sort((a, b) => {
      const av = (a as unknown as Record<string, unknown>)[sortBy];
      const bv = (b as unknown as Record<string, unknown>)[sortBy];
      if (av === null || av === undefined) return 1;
      if (bv === null || bv === undefined) return -1;
      if (av < bv) return -1 * mult;
      if (av > bv) return 1 * mult;
      return 0;
    });
  }

  function setSort(k: SortKey): void {
    if (sortBy === k) sortDir = sortDir === 'asc' ? 'desc' : 'asc';
    else {
      sortBy = k;
      sortDir = 'desc';
    }
  }
</script>

{#if metricsState.kind === 'idle' || metricsState.kind === 'loading'}
  <p class="text-xs text-slate-500">Loading per-case metrics…</p>
{:else if metricsState.kind === 'error'}
  <p class="text-xs text-slate-500">
    {metricsState.error instanceof ApiError && metricsState.error.status === 404
      ? 'No summary.json next to predictions — likely no GT was available.'
      : `Failed to load: ${metricsState.error.message}`}
  </p>
{:else}
  <div class="bg-bg-soft border border-border-soft rounded p-3">
    <div class="text-xs text-slate-300 mb-2">
      Mean Dice across cases:
      <span class="text-slate-100">{metricsState.data.foreground_mean_dice?.toFixed(4) ?? '—'}</span>
    </div>
    <table class="w-full text-xs">
      <thead>
        <tr class="text-slate-500 border-b border-border-soft">
          <th class="text-left py-1 px-2">
            <button type="button" class="text-slate-500 hover:text-slate-300" onclick={() => setSort('case_id')}>Case</button>
          </th>
          <th class="text-right py-1 px-2">
            <button type="button" class="text-slate-500 hover:text-slate-300" onclick={() => setSort('dice')}>Dice</button>
          </th>
        </tr>
      </thead>
      <tbody>
        {#each sorted(metricsState.data.cases) as c}
          <tr class="border-b border-border-soft">
            <td class="py-1 px-2 text-slate-300">{c.case_id}</td>
            <td class="py-1 px-2 text-right text-slate-200">{c.dice?.toFixed(4) ?? '—'}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
{/if}
