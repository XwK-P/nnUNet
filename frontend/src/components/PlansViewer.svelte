<script lang="ts">
  import { endpoints, ApiError } from '../lib/api';

  let { datasetId }: { datasetId: string } = $props();

  let state = $state<
    | { kind: 'idle' }
    | { kind: 'loading' }
    | { kind: 'loaded'; data: Record<string, unknown> }
    | { kind: 'error'; error: ApiError | Error }
  >({ kind: 'idle' });

  $effect(() => {
    state = { kind: 'loading' };
    endpoints
      .getDatasetPlans(datasetId)
      .then((data) => (state = { kind: 'loaded', data }))
      .catch((e) => (state = { kind: 'error', error: e }));
  });
</script>

{#if state.kind === 'loading' || state.kind === 'idle'}
  <p class="text-sm text-slate-400">Loading plans…</p>
{:else if state.kind === 'error'}
  <p class="text-sm text-err">
    {state.error instanceof ApiError && state.error.status === 404
      ? 'No plans.json found — run plan_and_preprocess first.'
      : `Failed to load plans: ${state.error.message}`}
  </p>
{:else}
  <pre class="text-[11px] text-slate-300 bg-bg-soft border border-border-soft rounded p-3 overflow-auto max-h-96">{JSON.stringify(state.data, null, 2)}</pre>
{/if}
