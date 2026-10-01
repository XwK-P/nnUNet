<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import WorkspaceSwitcher from './WorkspaceSwitcher.svelte';
  import { createJobsStore } from '../lib/stores/jobs';

  const ACTIVE = new Set(['queued', 'starting', 'running', 'pending']);

  const jobs = createJobsStore();
  let activeCount = $state(0);

  onMount(() => {
    const unsub = jobs.subscribe((s) => {
      if (s.kind === 'loaded') {
        activeCount = s.data.filter((j) => ACTIVE.has(j.status)).length;
      }
    });
    jobs.startPolling(5000);
    return () => {
      unsub();
    };
  });
  onDestroy(() => {
    jobs.stopPolling();
  });
</script>

<header
  class="flex items-center gap-3 bg-bg-panel border-b border-border px-4 py-2 text-xs"
>
  <strong class="text-slate-100">nnU-Net Manager</strong>

  <WorkspaceSwitcher />

  <a
    href="#/jobs"
    class="px-2 py-0.5 rounded-full text-[10px] hover:underline"
    class:bg-emerald-900={activeCount === 0}
    class:text-emerald-200={activeCount === 0}
    class:bg-amber-700={activeCount > 0}
    class:text-amber-100={activeCount > 0}
    aria-label={`${activeCount} active jobs (open jobs page)`}
  >
    ● {activeCount} jobs running
  </a>

  <span class="text-amber-400 text-[10px]">GPU: pending</span>

  <span class="flex-1"></span>

  <a href="#/settings" class="text-slate-400 hover:text-slate-200">⚙ Settings</a>
</header>
