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
      .getDatasetFingerprint(datasetId)
      .then((data) => (state = { kind: 'loaded', data }))
      .catch((e) => (state = { kind: 'error', error: e }));
  });

  function spacings(d: Record<string, unknown>): number[][] {
    const s = d['spacings'];
    if (Array.isArray(s)) return s as number[][];
    return [];
  }

  function intensityProps(d: Record<string, unknown>): Record<string, Record<string, number>> {
    const obj = d['foreground_intensity_properties_per_channel'];
    if (obj && typeof obj === 'object') return obj as Record<string, Record<string, number>>;
    return {};
  }
</script>

{#if state.kind === 'loading' || state.kind === 'idle'}
  <p class="text-sm text-slate-400">Loading fingerprint…</p>
{:else if state.kind === 'error'}
  <p class="text-sm text-err">
    {state.error instanceof ApiError && state.error.status === 404
      ? 'No fingerprint.json — dataset has not been preprocessed yet.'
      : `Failed to load fingerprint: ${state.error.message}`}
  </p>
{:else}
  <div class="space-y-4">
    <section>
      <h4 class="text-xs uppercase tracking-wider text-slate-500 mb-2">Spacings (first {Math.min(5, spacings(state.data).length)} of {spacings(state.data).length})</h4>
      <ul class="text-xs space-y-0.5">
        {#each spacings(state.data).slice(0, 5) as s}
          <li class="text-slate-300 font-mono">[{s.map((v) => v.toFixed(3)).join(', ')}]</li>
        {/each}
      </ul>
    </section>

    <section>
      <h4 class="text-xs uppercase tracking-wider text-slate-500 mb-2">Intensity per channel</h4>
      <table class="text-xs w-full">
        <thead>
          <tr class="text-slate-500 border-b border-border-soft">
            <th class="text-left py-1">Channel</th>
            <th class="text-right py-1">Mean</th>
            <th class="text-right py-1">Std</th>
          </tr>
        </thead>
        <tbody>
          {#each Object.entries(intensityProps(state.data)) as [ch, props]}
            <tr>
              <td class="py-1 text-slate-300">{ch}</td>
              <td class="py-1 text-right text-slate-400">{(props.mean ?? NaN).toFixed(2)}</td>
              <td class="py-1 text-right text-slate-400">{(props.std ?? NaN).toFixed(2)}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </section>
  </div>
{/if}
