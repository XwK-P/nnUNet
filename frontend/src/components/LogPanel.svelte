<script lang="ts">
  import { onMount, onDestroy, tick } from 'svelte';
  import { createRunStreamStore, type RunStreamState } from '../lib/stores/runStream';

  let { runId }: { runId: string } = $props();
  let store: ReturnType<typeof createRunStreamStore> | null = null;
  let s = $state<RunStreamState>({ metrics: {}, log: [], imageSamples: [], connected: false });
  let pre: HTMLPreElement | undefined = $state();

  onMount(() => {
    store = createRunStreamStore(runId);
    const unsub = store.subscribe(async (next) => {
      s = next;
      await tick();
      if (pre) pre.scrollTop = pre.scrollHeight;
    });
    return () => {
      unsub();
    };
  });
  onDestroy(() => {
    store?.close();
  });
</script>

<div class="space-y-2">
  <div class="flex items-center text-[10px] text-slate-500">
    <span>{s.log.length} lines</span>
    <span class="ml-auto">{s.connected ? 'live' : 'connecting…'}</span>
  </div>
  <pre
    bind:this={pre}
    class="bg-black text-slate-200 text-[11px] font-mono p-2 h-80 overflow-auto whitespace-pre-wrap rounded border border-border-soft"
  >{s.log.join('\n')}</pre>
</div>
