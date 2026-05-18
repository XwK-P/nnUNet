<script lang="ts">
  import { createThemeStore, type Theme } from '../lib/stores/theme';

  const theme = createThemeStore();
  let current = $state<Theme>(theme.get());

  function set(t: Theme): void {
    theme.set(t);
    current = t;
  }
</script>

<h2 class="text-lg font-semibold text-slate-100">Settings</h2>
<p class="text-sm text-slate-400 mt-2">Phase 0 placeholder. Env-var management, GPU listing, About land in Phase 7.</p>

<div class="mt-4">
  <div class="text-[11px] uppercase tracking-wider text-slate-500">Theme</div>
  <div class="flex gap-2 mt-1 text-xs">
    {#each ['light','dark','system'] as t}
      <button
        class="px-3 py-1 rounded border border-border-soft"
        class:bg-accent-soft={current === t}
        class:text-slate-100={current === t}
        onclick={() => set(t)}
      >
        {t}
      </button>
    {/each}
  </div>
</div>
