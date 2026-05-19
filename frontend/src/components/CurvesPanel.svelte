<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import LineChart from '../lib/charts/LineChart.svelte';
  import { createRunStreamStore, type RunStreamState } from '../lib/stores/runStream';

  let { runId }: { runId: string } = $props();
  let store: ReturnType<typeof createRunStreamStore> | null = null;
  let s = $state<RunStreamState>({ metrics: {}, log: [], imageSamples: [], connected: false });

  const KEYS = ['train_loss', 'val_loss', 'mean_fg_dice', 'learning_rate', 'epoch_duration'];

  function series(key: string): number[][] {
    const m = s.metrics[key];
    if (!m || m.steps.length === 0) return [[0], [null as unknown as number]];
    return [m.steps, m.values];
  }

  onMount(() => {
    store = createRunStreamStore(runId);
    const unsub = store.subscribe((next) => (s = next));
    return () => {
      unsub();
    };
  });
  onDestroy(() => {
    store?.close();
  });
</script>

<div class="grid grid-cols-2 gap-3">
  {#each KEYS as k}
    <LineChart data={series(k)} series={[{ label: k }]} title={k} />
  {/each}
</div>

<p class="text-[10px] text-slate-600 mt-2">{s.connected ? 'live' : 'connecting…'}</p>
