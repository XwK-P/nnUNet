<script lang="ts">
  import { endpoints } from '../lib/api';
  import type { Model, ExportModelRequest } from '../lib/types';

  let { model, onClose }: { model: Model; onClose: () => void } = $props();

  let outputZip = $state('');
  let folds = $state<string[]>([]);
  $effect(() => {
    folds = model.folds.map((f) => f.fold);
  });
  let busy = $state(false);
  let error = $state<string | null>(null);

  function toggleFold(fold: string): void {
    folds = folds.includes(fold) ? folds.filter((x) => x !== fold) : [...folds, fold];
  }

  async function submit(): Promise<void> {
    if (!outputZip) {
      error = 'output zip required';
      return;
    }
    busy = true;
    error = null;
    try {
      const req: ExportModelRequest = {
        dataset_id: Number(model.dataset_id.replace(/^Dataset/, '').split('_')[0]),
        output_zip: outputZip,
        configurations: [model.configuration],
        folds,
        trainer: model.trainer_name,
        plans: model.plans_name,
      };
      await endpoints.postExportModel(req);
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
    aria-label="Export model"
    tabindex="-1"
    onclick={(e) => e.stopPropagation()}
    onkeydown={(e) => e.stopPropagation()}
  >
    <h3 class="text-sm font-semibold text-slate-100 mb-3">Export {model.id}</h3>
    <label class="block text-xs text-slate-500 mb-1" for="export-zip">Output zip path</label>
    <input
      id="export-zip"
      class="w-full bg-bg-soft border border-border-soft rounded px-2 py-1 text-sm text-slate-100"
      bind:value={outputZip}
      placeholder="/abs/path/model.zip"
    />
    <div class="mt-3">
      <span class="block text-xs text-slate-500 mb-1">Folds</span>
      <div class="flex gap-1 flex-wrap">
        {#each model.folds as f}
          <label class="text-[11px] flex items-center gap-1">
            <input
              type="checkbox"
              checked={folds.includes(f.fold)}
              onchange={() => toggleFold(f.fold)}
            />
            {f.fold}
          </label>
        {/each}
      </div>
    </div>
    {#if error}<p class="text-[11px] text-err mt-2">{error}</p>{/if}
    <div class="flex gap-2 mt-4 justify-end">
      <button type="button" class="text-xs text-slate-400 px-3 py-1" onclick={onClose}>Cancel</button>
      <button
        type="button"
        class="text-xs bg-accent text-bg-base px-3 py-1 rounded"
        disabled={busy}
        onclick={submit}
      >
        {busy ? 'Queuing…' : 'Export'}
      </button>
    </div>
  </div>
</div>
