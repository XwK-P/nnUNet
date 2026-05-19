<script lang="ts">
  import { onMount, tick } from 'svelte';
  import uPlot from 'uplot';
  import 'uplot/dist/uPlot.min.css';
  import type { RunMetricSeries } from '../lib/types';

  let { metrics = [] as RunMetricSeries[] }: { metrics: RunMetricSeries[] } = $props();

  type XAxis = 'epoch' | 'wall_time';
  let metricKey = $state<string>('');
  let xAxis = $state<XAxis>('epoch');
  let smoothing = $state<number>(0);  // 0..0.95

  let containerEl: HTMLDivElement | undefined = $state();
  let chart: uPlot | undefined;

  function allKeys(): string[] {
    const keys = new Set<string>();
    for (const m of metrics) for (const k of Object.keys(m.series)) keys.add(k);
    return [...keys].sort();
  }

  function ema(values: number[], alpha: number): number[] {
    if (alpha <= 0) return values;
    const out: number[] = [];
    let last = values[0] ?? 0;
    for (const v of values) {
      last = alpha * last + (1 - alpha) * v;
      out.push(last);
    }
    return out;
  }

  function buildSeries(): { data: uPlot.AlignedData; opts: uPlot.Options } {
    const palette = [
      '#67e8f9', '#fca5a5', '#86efac', '#fcd34d',
      '#a5b4fc', '#f9a8d4', '#fdba74', '#c4b5fd',
    ];
    const allX = new Set<number>();
    const seriesData: { runId: string; xs: number[]; ys: number[] }[] = [];
    for (const m of metrics) {
      const pts = m.series[metricKey] ?? [];
      const xs = pts.map((p) => xAxis === 'epoch' ? p.step : (p.wall_time ?? p.step));
      const ys = ema(pts.map((p) => p.value), smoothing);
      for (const x of xs) allX.add(x);
      seriesData.push({ runId: m.run_id, xs, ys });
    }
    const sortedX = [...allX].sort((a, b) => a - b);
    const aligned: uPlot.AlignedData = [sortedX];
    const opts: uPlot.Options = {
      width: containerEl?.clientWidth ?? 600,
      height: 360,
      scales: { x: { time: false } },
      axes: [
        { stroke: '#94a3b8', grid: { stroke: '#1f2937' } },
        { stroke: '#94a3b8', grid: { stroke: '#1f2937' } },
      ],
      series: [{ label: xAxis }],
    };
    seriesData.forEach((s, i) => {
      const map = new Map<number, number>();
      s.xs.forEach((x, j) => map.set(x, s.ys[j]));
      aligned.push(sortedX.map((x) => map.has(x) ? (map.get(x) as number) : null));
      opts.series.push({
        label: s.runId,
        stroke: palette[i % palette.length],
        width: 1.5,
        spanGaps: true,
      });
    });
    return { data: aligned, opts };
  }

  function render() {
    if (!containerEl || !metricKey) return;
    chart?.destroy();
    const { data, opts } = buildSeries();
    chart = new uPlot(opts, data, containerEl);
  }

  onMount(() => {
    const keys = allKeys();
    if (!metricKey && keys.length) metricKey = keys[0];
    tick().then(render);
    return () => chart?.destroy();
  });

  $effect(() => {
    // re-render on any control change or new metrics payload
    metricKey; xAxis; smoothing; metrics;
    tick().then(render);
  });
</script>

<div class="bg-bg-soft border border-border-soft rounded p-3">
  <div class="flex items-center gap-3 mb-2 text-[11px]">
    <label class="text-slate-500">metric</label>
    <select class="bg-bg-panel border border-border-soft rounded px-2 py-0.5 text-slate-200"
            bind:value={metricKey}>
      {#each allKeys() as k}
        <option value={k}>{k}</option>
      {/each}
    </select>
    <label class="text-slate-500">x-axis</label>
    <select class="bg-bg-panel border border-border-soft rounded px-2 py-0.5 text-slate-200"
            bind:value={xAxis}>
      <option value="epoch">epoch</option>
      <option value="wall_time">wall_time</option>
    </select>
    <label class="text-slate-500">smoothing</label>
    <input type="range" min="0" max="0.95" step="0.05" bind:value={smoothing} />
    <span class="text-slate-400">{smoothing.toFixed(2)}</span>
  </div>

  {#if metrics.length === 0}
    <p class="text-xs text-slate-500">Select runs to plot…</p>
  {:else if allKeys().length === 0}
    <p class="text-xs text-slate-500">Selected runs have no metric history.</p>
  {/if}

  <div bind:this={containerEl} class="w-full"></div>
</div>
