<script lang="ts">
  import { tick } from 'svelte';
  import { createRunStreamStore, type RunStreamState } from '../lib/stores/runStream';

  let { runId }: { runId: string } = $props();
  let s = $state<RunStreamState>({ metrics: {}, log: [], imageSamples: [], connected: false });
  let pre: HTMLPreElement | undefined = $state();

  // Recreate the SSE store every time runId changes. See CurvesPanel
  // for the rationale: an onMount-only setup ignores prop swaps and
  // keeps streaming the previous run.
  $effect(() => {
    s = { metrics: {}, log: [], imageSamples: [], connected: false };
    const store = createRunStreamStore(runId);
    const unsub = store.subscribe(async (next) => {
      s = next;
      await tick();
      if (pre) pre.scrollTop = pre.scrollHeight;
    });
    return () => {
      unsub();
      store.close();
    };
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
