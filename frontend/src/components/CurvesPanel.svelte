<script lang="ts">
  import LineChart from '../lib/charts/LineChart.svelte';
  import { createRunStreamStore, type RunStreamState } from '../lib/stores/runStream';

  let { runId }: { runId: string } = $props();
  let s = $state<RunStreamState>({ metrics: {}, log: [], imageSamples: [], connected: false });

  const KEYS = ['train_loss', 'val_loss', 'mean_fg_dice', 'learning_rate', 'epoch_duration'];

  function series(key: string): number[][] {
    const m = s.metrics[key];
    if (!m || m.steps.length === 0) return [[0], [null as unknown as number]];
    return [m.steps, m.values];
  }

  // Recreate the SSE store every time runId changes — the parent
  // mounts this component once and just swaps the prop when the user
  // picks a different run, so an onMount-only setup would leave us
  // listening to the previous run forever. The $effect cleanup tears
  // down the old subscription and EventSource before the new one is
  // built.
  $effect(() => {
    s = { metrics: {}, log: [], imageSamples: [], connected: false };
    const store = createRunStreamStore(runId);
    const unsub = store.subscribe((next) => (s = next));
    return () => {
      unsub();
      store.close();
    };
  });
</script>

<div class="grid grid-cols-2 gap-3">
  {#each KEYS as k}
    <LineChart data={series(k)} series={[{ label: k }]} title={k} />
  {/each}
</div>

<p class="text-[10px] text-slate-600 mt-2">{s.connected ? 'live' : 'connecting…'}</p>
