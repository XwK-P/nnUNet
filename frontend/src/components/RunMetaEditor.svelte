<script lang="ts">
  import { endpoints } from '../lib/api';
  import type { Run } from '../lib/types';

  interface Props {
    run: Run;
    onSaved: (updated: Run) => void;
  }

  let { run, onSaved }: Props = $props();

  function parseTags(s: string | null): string[] {
    if (!s) return [];
    try {
      const v = JSON.parse(s);
      return Array.isArray(v) ? v.map(String) : [];
    } catch {
      return [];
    }
  }

  let tagsText = $state('');
  let notes = $state('');
  let busy = $state(false);
  let error = $state<string | null>(null);

  // Re-sync local state when a different run is selected (initial mount included).
  $effect(() => {
    tagsText = parseTags(run.tags_json).join(', ');
    notes = run.notes ?? '';
    error = null;
  });

  async function save(): Promise<void> {
    busy = true;
    error = null;
    try {
      const updated = await endpoints.updateRun(run.id, {
        tags: tagsText.split(',').map((t) => t.trim()).filter(Boolean),
        notes,
      });
      onSaved(updated);
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      busy = false;
    }
  }

  const tagsId = $derived(`run-meta-tags-${run.id}`);
  const notesId = $derived(`run-meta-notes-${run.id}`);
</script>

<div class="bg-bg-soft border border-border-soft rounded p-3">
  <h4 class="text-xs uppercase tracking-wider text-slate-500 mb-2">{run.id}</h4>
  <label class="block text-[11px] text-slate-500 mt-2" for={tagsId}>
    Tags (comma-separated)
  </label>
  <input
    id={tagsId}
    class="w-full bg-bg-panel border border-border-soft rounded px-2 py-1 text-sm text-slate-100"
    bind:value={tagsText}
    placeholder="baseline, v1"
  />
  <label class="block text-[11px] text-slate-500 mt-2" for={notesId}>Notes</label>
  <textarea
    id={notesId}
    class="w-full bg-bg-panel border border-border-soft rounded px-2 py-1 text-sm text-slate-100 min-h-20"
    bind:value={notes}
  ></textarea>
  {#if error}
    <p class="text-[11px] text-err mt-2">{error}</p>
  {/if}
  <div class="mt-2 flex justify-end">
    <button
      class="text-xs bg-accent text-bg-base px-3 py-1 rounded disabled:opacity-50"
      disabled={busy}
      onclick={save}
    >
      {busy ? 'Saving…' : 'Save'}
    </button>
  </div>
</div>
