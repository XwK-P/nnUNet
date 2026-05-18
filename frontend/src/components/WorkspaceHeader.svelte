<script lang="ts">
  import { createWorkspaceStore } from '../lib/stores/workspace';

  const ws = createWorkspaceStore();
  let current = $state<string | null>(ws.get());

  ws.subscribe((v) => (current = v));

  function clear(): void {
    ws.clear();
  }
</script>

<header
  class="flex items-center gap-3 bg-bg-panel border-b border-border px-4 py-2 text-xs"
>
  <strong class="text-slate-100">nnU-Net Manager</strong>

  <span class="bg-bg-soft px-2 py-0.5 rounded text-slate-400">
    Workspace: {current ?? '(none — pick a dataset)'}
    {#if current}
      <button class="ml-2 text-slate-500 hover:text-slate-300" onclick={clear}>×</button>
    {/if}
  </span>

  <span class="bg-emerald-900 text-emerald-200 px-2 py-0.5 rounded-full text-[10px]">
    ● 0 jobs running
  </span>

  <span class="text-amber-400 text-[10px]">GPU: pending</span>

  <span class="flex-1"></span>

  <a href="#/settings" class="text-slate-400 hover:text-slate-200">⚙ Settings</a>
</header>
