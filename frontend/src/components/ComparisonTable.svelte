<script lang="ts">
  import type { RunSummary } from '../lib/types';
  import { toCsv, downloadCsv } from './csv';

  let { summaries = [] as RunSummary[] }: { summaries: RunSummary[] } = $props();

  type SortKey =
    | 'dataset_id'
    | 'configuration'
    | 'fold'
    | 'status'
    | 'foreground_mean_dice';
  let sortBy = $state<SortKey>('foreground_mean_dice');
  let sortDir = $state<'asc' | 'desc'>('desc');
  let statusFilter = $state<string>('');
  let datasetFilter = $state<string>('');

  function visible(): RunSummary[] {
    return summaries.filter((s) => {
      if (statusFilter && s.status !== statusFilter) return false;
      if (datasetFilter && !s.dataset_id.includes(datasetFilter)) return false;
      return true;
    });
  }

  function sorted(): RunSummary[] {
    const mult = sortDir === 'asc' ? 1 : -1;
    return [...visible()].sort((a, b) => {
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

  function arrow(k: SortKey): string {
    if (sortBy !== k) return '';
    return sortDir === 'asc' ? ' ▲' : ' ▼';
  }

  function exportCsv(): void {
    const cols: (keyof RunSummary)[] = [
      'run_id',
      'dataset_id',
      'plans_name',
      'trainer_name',
      'configuration',
      'fold',
      'status',
      'foreground_mean_dice',
    ];
    const csv = toCsv(
      sorted() as unknown as Record<string, unknown>[],
      cols as string[],
    );
    const ts = new Date().toISOString().replace(/[:.]/g, '-');
    downloadCsv(`nnunet-compare-${ts}.csv`, csv);
  }
</script>

<div class="bg-bg-soft border border-border-soft rounded p-3">
  <div class="flex items-center gap-2 mb-2 text-[11px]">
    <input
      class="bg-bg-panel border border-border-soft rounded px-2 py-0.5 text-slate-200"
      placeholder="filter dataset…"
      bind:value={datasetFilter}
    />
    <select
      class="bg-bg-panel border border-border-soft rounded px-2 py-0.5 text-slate-200"
      bind:value={statusFilter}
    >
      <option value="">all statuses</option>
      <option value="completed">completed</option>
      <option value="training">training</option>
      <option value="abandoned">abandoned</option>
      <option value="failed">failed</option>
      <option value="unknown">unknown</option>
    </select>
    <span class="flex-1"></span>
    <button
      type="button"
      class="text-[11px] bg-bg-panel border border-border-soft rounded px-3 py-0.5 text-slate-200 hover:bg-bg-soft disabled:opacity-50"
      onclick={exportCsv}
      disabled={summaries.length === 0}
    >
      Export CSV
    </button>
  </div>

  {#if summaries.length === 0}
    <p class="text-xs text-slate-500">No runs selected.</p>
  {:else}
    <table class="w-full text-xs">
      <thead>
        <tr class="text-slate-500 border-b border-border-soft">
          <th class="text-left py-1 px-2 cursor-pointer" onclick={() => setSort('dataset_id')}
            >Dataset{arrow('dataset_id')}</th
          >
          <th
            class="text-left py-1 px-2 cursor-pointer"
            onclick={() => setSort('configuration')}>Config{arrow('configuration')}</th
          >
          <th class="text-left py-1 px-2">Trainer</th>
          <th class="text-left py-1 px-2">Plans</th>
          <th class="text-left py-1 px-2 cursor-pointer" onclick={() => setSort('fold')}
            >Fold{arrow('fold')}</th
          >
          <th class="text-left py-1 px-2 cursor-pointer" onclick={() => setSort('status')}
            >Status{arrow('status')}</th
          >
          <th
            class="text-right py-1 px-2 cursor-pointer"
            onclick={() => setSort('foreground_mean_dice')}
            >Mean Dice{arrow('foreground_mean_dice')}</th
          >
        </tr>
      </thead>
      <tbody>
        {#each sorted() as r}
          <tr class="border-b border-border-soft">
            <td class="py-1 px-2 text-slate-300">{r.dataset_id}</td>
            <td class="py-1 px-2 text-slate-300">{r.configuration}</td>
            <td class="py-1 px-2 text-slate-400">{r.trainer_name}</td>
            <td class="py-1 px-2 text-slate-400">{r.plans_name}</td>
            <td class="py-1 px-2 text-slate-300">{r.fold}</td>
            <td class="py-1 px-2">
              <span
                class:text-ok={r.status === 'completed'}
                class:text-slate-500={r.status !== 'completed'}>{r.status}</span
              >
            </td>
            <td class="py-1 px-2 text-right text-slate-300"
              >{r.foreground_mean_dice?.toFixed(4) ?? '—'}</td
            >
          </tr>
        {/each}
      </tbody>
    </table>
  {/if}
</div>
