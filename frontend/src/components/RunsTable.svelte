<script lang="ts">
  import { onMount } from 'svelte';
  import { createRunsStore } from '../lib/stores/runs';
  import type { Run, RunFilter } from '../lib/types';

  let { filter = {} as RunFilter }: { filter?: RunFilter } = $props();

  const runs = createRunsStore();
  let result = $state(runs.get());

  type SortKey = 'dataset_id' | 'configuration' | 'fold' | 'status' | 'last_seen_at';
  let sortBy = $state<SortKey>('last_seen_at');
  let sortDir = $state<'asc' | 'desc'>('desc');

  onMount(() => {
    const unsub = runs.subscribe((s) => (result = s));
    runs.load(filter);
    return unsub;
  });

  function sorted(data: Run[]): Run[] {
    const mult = sortDir === 'asc' ? 1 : -1;
    return [...data].sort((a, b) => {
      const av = (a as unknown as Record<string, unknown>)[sortBy] ?? '';
      const bv = (b as unknown as Record<string, unknown>)[sortBy] ?? '';
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
</script>

{#if result.kind === 'loading' || result.kind === 'idle'}
  <p class="text-sm text-slate-400">Loading runs…</p>
{:else if result.kind === 'error'}
  <p class="text-sm text-err">{result.error.message}</p>
{:else if result.data.length === 0}
  <p class="text-sm text-slate-400">No runs found.</p>
{:else}
  <table class="w-full text-xs">
    <thead>
      <tr class="text-slate-500 border-b border-border-soft">
        <th class="text-left py-1 px-2 cursor-pointer" onclick={() => setSort('dataset_id')}>Dataset{arrow('dataset_id')}</th>
        <th class="text-left py-1 px-2 cursor-pointer" onclick={() => setSort('configuration')}>Config{arrow('configuration')}</th>
        <th class="text-left py-1 px-2">Trainer</th>
        <th class="text-left py-1 px-2">Plans</th>
        <th class="text-left py-1 px-2 cursor-pointer" onclick={() => setSort('fold')}>Fold{arrow('fold')}</th>
        <th class="text-left py-1 px-2 cursor-pointer" onclick={() => setSort('status')}>Status{arrow('status')}</th>
        <th class="text-left py-1 px-2 cursor-pointer" onclick={() => setSort('last_seen_at')}>Last seen{arrow('last_seen_at')}</th>
      </tr>
    </thead>
    <tbody>
      {#each sorted(result.data) as r}
        <tr class="border-b border-border-soft">
          <td class="py-1 px-2 text-slate-300">{r.dataset_id}</td>
          <td class="py-1 px-2 text-slate-300">{r.configuration}</td>
          <td class="py-1 px-2 text-slate-400">{r.trainer_name}</td>
          <td class="py-1 px-2 text-slate-400">{r.plans_name}</td>
          <td class="py-1 px-2 text-slate-300">{r.fold}</td>
          <td class="py-1 px-2">
            <span class:text-ok={r.status === 'completed'} class:text-slate-500={r.status !== 'completed'}>{r.status}</span>
          </td>
          <td class="py-1 px-2 text-slate-500">{r.last_seen_at ?? '—'}</td>
        </tr>
      {/each}
    </tbody>
  </table>
{/if}
