<script lang="ts">
  import { endpoints } from '../lib/api';

  let { onClose }: { onClose: () => void } = $props();

  let zipPath = $state('');
  let busy = $state(false);
  let error = $state<string | null>(null);

  async function submit(): Promise<void> {
    if (!zipPath) {
      error = 'zip path required';
      return;
    }
    busy = true;
    error = null;
    try {
      await endpoints.postImportModel({ zip_path: zipPath });
      onClose();
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      busy = false;
    }
  }
</script>

<div
  class="fixed inset-0 z-30 bg-black/60 flex items-center justify-center"
  role="button"
  tabindex="-1"
  onclick={onClose}
  onkeydown={(e) => { if (e.key === 'Escape') onClose(); }}
>
  <div
    class="bg-bg-panel border border-border-soft rounded p-4 w-[480px]"
    role="dialog"
    aria-modal="true"
    aria-label="Import model from zip"
    tabindex="-1"
    onclick={(e) => e.stopPropagation()}
    onkeydown={(e) => e.stopPropagation()}
  >
    <h3 class="text-sm font-semibold text-slate-100 mb-3">Import model from zip</h3>
    <label class="block text-xs text-slate-500 mb-1" for="import-zip-path">Local zip path</label>
    <input
      id="import-zip-path"
      class="w-full bg-bg-soft border border-border-soft rounded px-2 py-1 text-sm text-slate-100"
      bind:value={zipPath}
      placeholder="/abs/path/model.zip"
    />
    {#if error}<p class="text-[11px] text-err mt-2">{error}</p>{/if}
    <div class="flex gap-2 mt-4 justify-end">
      <button type="button" class="text-xs text-slate-400 px-3 py-1" onclick={onClose}>Cancel</button>
      <button
        type="button"
        class="text-xs bg-accent text-bg-base px-3 py-1 rounded"
        disabled={busy}
        onclick={submit}
      >
        {busy ? 'Queuing…' : 'Import'}
      </button>
    </div>
  </div>
</div>
