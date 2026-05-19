<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { createRunStreamStore, type RunStreamState } from '../lib/stores/runStream';

  let { runId }: { runId: string } = $props();
  let store: ReturnType<typeof createRunStreamStore> | null = null;
  let s = $state<RunStreamState>({ metrics: {}, log: [], imageSamples: [], connected: false });

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

<div class="space-y-2">
  {#if s.imageSamples.length === 0}
    <p class="text-xs text-slate-500">
      No image samples emitted yet. The training loop writes them every N epochs when the TB image
      logger is enabled. Phase 6 will switch this panel to a NiiVue viewer for 2D/3D overlays.
    </p>
  {:else}
    <ul class="grid grid-cols-3 gap-2">
      {#each s.imageSamples as sample}
        <li class="bg-bg-soft border border-border-soft rounded p-2 text-[10px]">
          <p class="text-slate-400 truncate">{sample.tag} · step {sample.step}</p>
          {#if sample.url}
            <img src={sample.url} alt={sample.tag} class="mt-1 w-full rounded" />
          {:else}
            <div class="mt-1 w-full h-16 bg-bg-panel rounded flex items-center justify-center text-slate-600">
              no thumbnail
            </div>
          {/if}
        </li>
      {/each}
    </ul>
  {/if}
  <p class="text-[10px] text-slate-600">{s.connected ? 'live' : 'connecting…'}</p>
</div>
