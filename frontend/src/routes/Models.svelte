<script lang="ts">
  import ModelsList from '../components/ModelsList.svelte';
  import ModelExportDialog from '../components/ModelExportDialog.svelte';
  import ModelImportDialog from '../components/ModelImportDialog.svelte';
  import FindBestConfigForm from '../components/FindBestConfigForm.svelte';
  import EnsembleForm from '../components/EnsembleForm.svelte';
  import PostprocForm from '../components/PostprocForm.svelte';
  import type { Model } from '../lib/types';

  let exportingModel = $state<Model | null>(null);
  let importing = $state(false);

  function handleAction(kind: string, m: Model): void {
    if (kind === 'export') exportingModel = m;
  }
</script>

<h2 class="text-lg font-semibold text-slate-100">Models</h2>

<div class="mt-4 grid grid-cols-1 xl:grid-cols-[1fr_360px] gap-4">
  <div class="min-w-0">
    <ModelsList onAction={handleAction} />
  </div>

  <div class="space-y-3">
    <div class="bg-bg-soft border border-border-soft rounded p-3">
      <h4 class="text-xs uppercase tracking-wider text-slate-500 mb-2">Tools</h4>
      <button
        type="button"
        class="text-[11px] bg-bg-panel border border-border-soft rounded px-2 py-0.5 text-slate-200 hover:bg-bg-soft"
        onclick={() => (importing = true)}
      >Import zip…</button>
    </div>
    <FindBestConfigForm />
    <EnsembleForm />
    <PostprocForm />
  </div>
</div>

{#if exportingModel}
  <ModelExportDialog model={exportingModel} onClose={() => (exportingModel = null)} />
{/if}
{#if importing}
  <ModelImportDialog onClose={() => (importing = false)} />
{/if}
