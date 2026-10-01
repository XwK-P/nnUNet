<script lang="ts">
  import { onMount } from 'svelte';
  import { endpoints } from '../lib/api';
  import type { EnvVarsResponse, LogLevel, Run } from '../lib/types';
  import { createRunsStore } from '../lib/stores/runs';
  import { createThemeStore, type Theme } from '../lib/stores/theme';
  import RunMetaEditor from '../components/RunMetaEditor.svelte';

  let env = $state<EnvVarsResponse | null>(null);
  let logLevel = $state<LogLevel>('INFO');
  let envError = $state<string | null>(null);

  const theme = createThemeStore();
  let currentTheme = $state<Theme>(theme.get());

  const runs = createRunsStore();
  let runsState = $state(runs.get());
  let selected = $state<Run | null>(null);

  const THEMES: Theme[] = ['light', 'dark', 'system'];
  const LEVELS: LogLevel[] = ['DEBUG', 'INFO', 'WARNING', 'ERROR'];

  onMount(() => {
    const unsub = runs.subscribe((s) => (runsState = s));
    runs.load({});
    endpoints
      .getEnvVars()
      .then((d) => (env = d))
      .catch((e) => (envError = e instanceof Error ? e.message : String(e)));
    endpoints
      .getLogLevel()
      .then((d) => (logLevel = d.level))
      .catch(() => {});
    return unsub;
  });

  async function changeLogLevel(next: LogLevel): Promise<void> {
    try {
      const res = await endpoints.putLogLevel(next);
      logLevel = res.level;
    } catch (e) {
      envError = e instanceof Error ? e.message : String(e);
    }
  }

  function setTheme(t: Theme): void {
    theme.set(t);
    currentTheme = t;
  }

  function onSaved(updated: Run): void {
    selected = updated;
    runs.load({}); // refresh table
  }
</script>

<h2 class="text-lg font-semibold text-slate-100">Settings</h2>

<div class="mt-4 grid grid-cols-1 xl:grid-cols-2 gap-4">
  <section class="bg-bg-soft border border-border-soft rounded p-3">
    <h3 class="text-xs uppercase tracking-wider text-slate-500 mb-2">
      Environment variables (read-only)
    </h3>
    {#if envError}
      <p class="text-xs text-err">{envError}</p>
    {/if}
    {#if env}
      <table class="w-full text-xs">
        <thead>
          <tr class="text-slate-500 border-b border-border-soft">
            <th class="text-left py-1">Name</th>
            <th class="text-left py-1">Value</th>
          </tr>
        </thead>
        <tbody>
          {#each env.vars as v}
            <tr>
              <td class="py-1 text-slate-300 font-mono">{v.name}</td>
              <td class="py-1 text-slate-400 font-mono">
                {#if v.value === null}
                  <span class="text-slate-600">— unset —</span>
                {:else}
                  {v.value}
                {/if}
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
      <p class="text-[11px] text-slate-500 mt-2">
        Edit these in your shell, restart the server, then refresh this page.
      </p>
    {/if}
  </section>

  <section class="bg-bg-soft border border-border-soft rounded p-3">
    <h3 class="text-xs uppercase tracking-wider text-slate-500 mb-2">Server</h3>
    <div class="text-xs flex items-center gap-2">
      <label class="text-slate-500" for="settings-log-level">Log level</label>
      <select
        id="settings-log-level"
        class="bg-bg-panel border border-border-soft rounded px-2 py-0.5 text-slate-200"
        onchange={(e) =>
          changeLogLevel((e.currentTarget as HTMLSelectElement).value as LogLevel)}
        value={logLevel}
      >
        {#each LEVELS as l}
          <option value={l} selected={logLevel === l}>{l}</option>
        {/each}
      </select>
    </div>

    <h3 class="text-xs uppercase tracking-wider text-slate-500 mt-4 mb-2">Theme</h3>
    <div class="text-xs flex items-center gap-2">
      {#each THEMES as t}
        <button
          class="px-2 py-0.5 rounded border border-border-soft"
          class:bg-bg-panel={currentTheme === t}
          class:text-slate-100={currentTheme === t}
          class:text-slate-500={currentTheme !== t}
          onclick={() => setTheme(t)}
        >
          {t}
        </button>
      {/each}
    </div>
  </section>

  <section class="xl:col-span-2 bg-bg-soft border border-border-soft rounded p-3">
    <h3 class="text-xs uppercase tracking-wider text-slate-500 mb-2">Run tags & notes</h3>
    <div class="grid grid-cols-1 xl:grid-cols-[280px_1fr] gap-3">
      <div class="bg-bg border border-border-soft rounded p-2 max-h-80 overflow-auto">
        {#if runsState.kind === 'loading'}
          <p class="text-xs text-slate-500">Loading…</p>
        {:else if runsState.kind === 'error'}
          <p class="text-xs text-err">{runsState.error.message}</p>
        {:else if runsState.kind === 'loaded'}
          {#if runsState.data.length === 0}
            <p class="text-xs text-slate-500">No runs found.</p>
          {:else}
            <ul class="text-xs space-y-0.5">
              {#each runsState.data as r}
                <li>
                  <button
                    class="text-left w-full px-2 py-1 hover:bg-bg-panel rounded font-mono"
                    class:text-accent={selected?.id === r.id}
                    class:text-slate-300={selected?.id !== r.id}
                    onclick={() => (selected = r)}
                  >
                    {r.id}
                  </button>
                </li>
              {/each}
            </ul>
          {/if}
        {/if}
      </div>
      <div>
        {#if selected}
          <RunMetaEditor run={selected} {onSaved} />
        {:else}
          <p class="text-sm text-slate-400">
            Pick a run on the left to add tags or notes.
          </p>
        {/if}
      </div>
    </div>
  </section>
</div>
