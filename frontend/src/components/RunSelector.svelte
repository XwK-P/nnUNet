<script lang="ts">
  import { onMount } from 'svelte';
  import { createRunsStore } from '../lib/stores/runs';
  import type { Run } from '../lib/types';

  let { value = [] as string[], onChange }: { value: string[]; onChange: (ids: string[]) => void } = $props();

  const runs = createRunsStore();
  let result = $state(runs.get());

  // Filter chips: dataset, configuration, status
  let datasetFilter = $state<string>('');
  let configFilter = $state<string>('');

  onMount(() => {
    const unsub = runs.subscribe((s) => (result = s));
    runs.load({});
    return unsub;
  });

  function toggle(id: string): void {
    onChange(value.includes(id) ? value.filter((v) => v !== id) : [...value, id]);
  }

  function clearAll(): void {
    onChange([]);
  }

  function visible(items: Run[]): Run[] {
    return items.filter((r) => {
      if (datasetFilter && !r.dataset_id.includes(datasetFilter)) return false;
      if (configFilter && r.configuration !== configFilter) return false;
      return true;
    });
  }

  function groupByDataset(items: Run[]): Record<string, Run[]> {
    const groups: Record<string, Run[]> = {};
    for (const r of items) (groups[r.dataset_id] ??= []).push(r);
    return groups;
  }

  function uniqConfigs(items: Run[]): string[] {
    return [...new Set(items.map((r) => r.configuration))].sort();
  }
</script>

<div class="bg-bg-soft border border-border-soft rounded p-3">
  <div class="flex items-center gap-2 mb-2">
    <h3 class="text-xs uppercase tracking-wider text-slate-500">Pick runs</h3>
    <span class="text-[10px] text-slate-500">({value.length} selected)</span>
    {#if value.length > 0}
      <button class="text-[10px] text-slate-400 hover:text-slate-200" onclick={clearAll}>clear</button>
    {/if}
  </div>

  {#if result.kind === 'loading' || result.kind === 'idle'}
    <p class="text-xs text-slate-500">Loading runs…</p>
  {:else if result.kind === 'error'}
    <p class="text-xs text-err">{result.error.message}</p>
  {:else if result.data.length === 0}
    <p class="text-xs text-slate-500">No runs yet — train something first.</p>
  {:else}
    <div class="flex gap-2 mb-2 text-[11px]">
      <input class="bg-bg-panel border border-border-soft rounded px-2 py-0.5 text-slate-200"
             placeholder="filter by dataset…" bind:value={datasetFilter} />
      <select class="bg-bg-panel border border-border-soft rounded px-2 py-0.5 text-slate-200"
              bind:value={configFilter}>
        <option value="">all configs</option>
        {#each uniqConfigs(result.data) as c}
          <option value={c}>{c}</option>
        {/each}
      </select>
    </div>

    <div class="max-h-80 overflow-auto text-xs">
      {#each Object.entries(groupByDataset(visible(result.data))) as [ds, items]}
        <div class="mt-2">
          <h4 class="text-[11px] text-slate-500 mb-1">{ds}</h4>
          <ul class="space-y-0.5">
            {#each items as r}
              <li>
                <label class="flex items-center gap-2 px-1 py-0.5 hover:bg-bg-panel rounded">
                  <input type="checkbox" checked={value.includes(r.id)} onchange={() => toggle(r.id)} />
                  <span class="text-slate-300">{r.configuration} · fold_{r.fold}</span>
                  <span class="text-slate-500">·</span>
                  <span class="text-slate-500">{r.trainer_name}/{r.plans_name}</span>
                  <span class="text-slate-500">·</span>
                  <span class:text-ok={r.status === 'completed'}
                        class:text-slate-500={r.status !== 'completed'}>{r.status}</span>
                </label>
              </li>
            {/each}
          </ul>
        </div>
      {/each}
    </div>
  {/if}
</div>
