<script lang="ts">
  import PredictionList from './PredictionList.svelte';
  import type { Run } from '../lib/types';

  let { run }: { run: Run } = $props();
</script>

<div class="bg-bg-soft border border-border-soft rounded p-3 mb-3">
  <div class="flex items-center gap-2 text-xs">
    <strong class="text-slate-100">{run.dataset_id}</strong>
    <span class="text-slate-500">·</span>
    <span class="text-slate-300">{run.plans_name} · {run.trainer_name} · {run.configuration}</span>
    <span class="text-slate-500">·</span>
    <span class="text-slate-300">fold_{run.fold}</span>
    <span class="ml-auto text-xs" class:text-ok={run.status === 'completed'} class:text-slate-500={run.status !== 'completed'}>
      {run.status}
    </span>
  </div>
  <p class="text-[10px] text-slate-600 mt-1">Live curves / log / image samples land in Phase 3.</p>
</div>

<div class="bg-bg-soft border border-border-soft rounded p-3">
  <PredictionList runId={run.id} />
</div>
