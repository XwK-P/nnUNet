<script lang="ts">
  import { launchEndpoints } from '../lib/api';
  import type { Job } from '../lib/types';

  let { job, onChanged }: { job: Job; onChanged: () => void } = $props();
  let busy = $state(false);
  let error = $state<string | null>(null);

  async function run(action: 'stop' | 'cancel' | 'restart') {
    busy = true;
    error = null;
    try {
      if (action === 'stop') await launchEndpoints.stopJob(job.id);
      else if (action === 'cancel') await launchEndpoints.cancelJob(job.id);
      else await launchEndpoints.restartJob(job.id);
      onChanged();
    } catch (e: unknown) {
      error = (e as Error).message;
    } finally {
      busy = false;
    }
  }

  const canStop = $derived(['starting', 'running'].includes(job.status));
  const canCancel = $derived(job.status === 'queued');
  const canRestart = $derived(
    ['completed', 'failed', 'killed', 'cancelled', 'unknown'].includes(job.status),
  );
</script>

<div class="flex gap-1 items-center">
  <button
    type="button"
    class="text-[10px] px-1 py-0.5 rounded"
    class:bg-bg-panel={canStop}
    class:text-slate-300={canStop}
    class:text-slate-700={!canStop}
    disabled={!canStop || busy}
    onclick={() => run('stop')}>stop</button
  >
  <button
    type="button"
    class="text-[10px] px-1 py-0.5 rounded"
    class:bg-bg-panel={canCancel}
    class:text-slate-300={canCancel}
    class:text-slate-700={!canCancel}
    disabled={!canCancel || busy}
    onclick={() => run('cancel')}>cancel</button
  >
  <button
    type="button"
    class="text-[10px] px-1 py-0.5 rounded"
    class:bg-bg-panel={canRestart}
    class:text-slate-300={canRestart}
    class:text-slate-700={!canRestart}
    disabled={!canRestart || busy}
    onclick={() => run('restart')}>restart</button
  >
  {#if error}<span class="text-[10px] text-err ml-1" title={error}>!</span>{/if}
</div>
