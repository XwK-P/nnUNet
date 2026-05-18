<script lang="ts">
  import { onMount } from 'svelte';
  import { createDashboardStore } from '../lib/stores/dashboard';

  const dash = createDashboardStore();
  let state = $state(dash.get());

  onMount(() => {
    const unsub = dash.subscribe((s) => (state = s));
    dash.load();
    return unsub;
  });

  function gb(n: number | null): string {
    if (n === null) return '—';
    return (n / 1024 / 1024 / 1024).toFixed(1) + ' GB';
  }
</script>

{#if state.kind === 'loading' || state.kind === 'idle'}
  <p class="text-sm text-slate-400">Loading dashboard…</p>
{:else if state.kind === 'error'}
  <p class="text-sm text-err">Failed to load dashboard: {state.error.message}</p>
{:else}
  <div class="grid grid-cols-2 gap-3">
    <section class="bg-bg-soft border border-border-soft rounded p-3">
      <h3 class="text-xs uppercase tracking-wider text-slate-500 mb-2">Active jobs</h3>
      <p class="text-sm text-slate-400">{state.data.active_jobs.length === 0 ? 'No jobs running. Live tracking lands in Phase 3.' : ''}</p>
    </section>

    <section class="bg-bg-soft border border-border-soft rounded p-3">
      <h3 class="text-xs uppercase tracking-wider text-slate-500 mb-2">Recent runs</h3>
      {#if state.data.recent_runs.length === 0}
        <p class="text-sm text-slate-400">No runs yet.</p>
      {:else}
        <ul class="space-y-1">
          {#each state.data.recent_runs as run}
            <li class="text-xs">
              <span class="text-slate-200">{run.dataset_id}</span>
              <span class="text-slate-500">·</span>
              <span class="text-slate-400">{run.configuration} · fold_{run.fold}</span>
              <span class="text-slate-500">·</span>
              <span class:text-ok={run.status === 'completed'} class:text-slate-500={run.status !== 'completed'}>{run.status}</span>
            </li>
          {/each}
        </ul>
      {/if}
    </section>

    <section class="bg-bg-soft border border-border-soft rounded p-3">
      <h3 class="text-xs uppercase tracking-wider text-slate-500 mb-2">Datasets</h3>
      <p class="text-sm text-slate-200">{state.data.counts.datasets} raw · {state.data.counts.preprocessed_datasets} preprocessed</p>
      <p class="text-xs text-slate-500 mt-1">{state.data.counts.runs} runs total, {state.data.counts.completed_runs} completed</p>
    </section>

    <section class="bg-bg-soft border border-border-soft rounded p-3">
      <h3 class="text-xs uppercase tracking-wider text-slate-500 mb-2">System</h3>
      <ul class="text-xs space-y-1">
        <li>Raw: <span class="text-slate-400">{gb(state.data.system.disk.raw.free)} free of {gb(state.data.system.disk.raw.total)}</span></li>
        <li>Preprocessed: <span class="text-slate-400">{gb(state.data.system.disk.preprocessed.free)} free of {gb(state.data.system.disk.preprocessed.total)}</span></li>
        <li>Results: <span class="text-slate-400">{gb(state.data.system.disk.results.free)} free of {gb(state.data.system.disk.results.total)}</span></li>
      </ul>
      <p class="text-[10px] text-slate-600 mt-2">GPU stats land in Phase 7.</p>
    </section>
  </div>
{/if}
