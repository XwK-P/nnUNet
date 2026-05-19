<script lang="ts">
  import { onMount } from 'svelte';
  import { createModelsStore } from '../lib/stores/models';
  import type { Model } from '../lib/types';

  let { onAction }: { onAction: (kind: string, model: Model) => void } = $props();

  const models = createModelsStore();
  let state = $state(models.get());

  onMount(() => {
    const unsub = models.subscribe((s) => (state = s));
    models.load();
    return unsub;
  });

  function mb(n: number): string {
    return (n / 1024 / 1024).toFixed(1) + ' MB';
  }
</script>

{#if state.kind === 'loading' || state.kind === 'idle'}
  <p class="text-sm text-slate-400">Loading models…</p>
{:else if state.kind === 'error'}
  <p class="text-sm text-err">{state.error.message}</p>
{:else if state.data.length === 0}
  <p class="text-sm text-slate-400">No trained models yet — train something first.</p>
{:else}
  <div class="space-y-3">
    {#each state.data as m}
      <div class="bg-bg-soft border border-border-soft rounded p-3">
        <div class="flex items-center gap-2 mb-2">
          <strong class="text-sm text-slate-100">{m.id}</strong>
          <span class="flex-1"></span>
          <button
            type="button"
            class="text-[11px] bg-bg-panel border border-border-soft rounded px-2 py-0.5 text-slate-200 hover:bg-bg-soft"
            onclick={() => onAction('export', m)}
          >Export</button>
        </div>
        <table class="text-xs w-full">
          <thead>
            <tr class="text-slate-500 border-b border-border-soft">
              <th class="text-left py-1">Fold</th>
              <th class="text-left py-1">Status</th>
              <th class="text-left py-1">Checkpoints</th>
            </tr>
          </thead>
          <tbody>
            {#each m.folds as f}
              <tr>
                <td class="py-1 text-slate-300">{f.fold}</td>
                <td class="py-1">
                  <span
                    class:text-ok={f.status === 'completed'}
                    class:text-slate-500={f.status !== 'completed'}
                  >{f.status}</span>
                </td>
                <td class="py-1 text-slate-400">
                  {#if f.checkpoints.length === 0}—{/if}
                  {#each f.checkpoints as c, i}
                    {#if i > 0}, {/if}{c.name} ({mb(c.size_bytes)})
                  {/each}
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {/each}
  </div>
{/if}
