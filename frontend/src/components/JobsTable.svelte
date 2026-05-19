<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { createJobsStore } from '../lib/stores/jobs';
  import JobActionsCell from './JobActionsCell.svelte';

  const jobs = createJobsStore();
  let s = $state(jobs.get());

  function fmtArgs(raw: string): string {
    try {
      const obj = JSON.parse(raw);
      if (Array.isArray(obj)) return obj.join(' ');
      if (typeof obj === 'object' && obj !== null) {
        return Object.entries(obj as Record<string, unknown>)
          .map(([k, v]) => `${k}=${v}`)
          .join(' ');
      }
      return raw;
    } catch {
      return raw;
    }
  }

  function fmtTs(ts: string | null): string {
    if (!ts) return '—';
    const d = new Date(ts);
    if (Number.isNaN(d.getTime())) return ts;
    return d.toLocaleString();
  }

  onMount(() => {
    const unsub = jobs.subscribe((next) => (s = next));
    jobs.startPolling(5000);
    return () => {
      unsub();
    };
  });
  onDestroy(() => {
    jobs.stopPolling();
  });
</script>

{#if s.kind === 'idle' || s.kind === 'loading'}
  <p class="text-xs text-slate-500">Loading jobs…</p>
{:else if s.kind === 'error'}
  <p class="text-xs text-err">Failed to load jobs: {s.error.message}</p>
{:else if s.data.length === 0}
  <p class="text-xs text-slate-500">
    No jobs tracked. Launch a preprocess, training, or predict run from the corresponding tab.
  </p>
{:else}
  <table class="w-full text-xs">
    <thead>
      <tr class="text-slate-500 border-b border-border-soft">
        <th class="text-left py-1 px-2">#</th>
        <th class="text-left py-1 px-2">Kind</th>
        <th class="text-left py-1 px-2">Status</th>
        <th class="text-left py-1 px-2">PID</th>
        <th class="text-left py-1 px-2">Exit</th>
        <th class="text-left py-1 px-2">Started</th>
        <th class="text-left py-1 px-2">Run / args</th>
        <th class="text-left py-1 px-2">Actions</th>
      </tr>
    </thead>
    <tbody>
      {#each s.data as j}
        <tr class="border-b border-border-soft hover:bg-bg-panel/40">
          <td class="py-1 px-2 text-slate-300">{j.id}</td>
          <td class="py-1 px-2 text-slate-300">{j.kind}</td>
          <td
            class="py-1 px-2"
            class:text-ok={j.status === 'completed' || j.status === 'succeeded'}
            class:text-err={j.status === 'failed'}
            class:text-amber-400={['queued', 'starting', 'running', 'pending'].includes(j.status)}
            class:text-slate-500={j.status === 'cancelled'}
          >
            {j.status}
          </td>
          <td class="py-1 px-2 text-slate-400">{j.pid ?? '—'}</td>
          <td class="py-1 px-2 text-slate-400">{j.exit_code ?? '—'}</td>
          <td class="py-1 px-2 text-slate-500">{fmtTs(j.started_at)}</td>
          <td class="py-1 px-2 text-slate-400 truncate max-w-md font-mono text-[10px]">
            {j.output_run_id ?? fmtArgs(j.args_json)}
          </td>
          <td class="py-1 px-2">
            <JobActionsCell job={j} onChanged={() => jobs.load()} />
          </td>
        </tr>
      {/each}
    </tbody>
  </table>
{/if}
