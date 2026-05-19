<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import uPlot from 'uplot';
  import 'uplot/dist/uPlot.min.css';

  let {
    data,
    series,
    height = 160,
    title = '',
  }: {
    data: number[][];
    series: { label: string; stroke?: string }[];
    height?: number;
    title?: string;
  } = $props();

  let host: HTMLDivElement | undefined;
  let chart: uPlot | null = null;
  let ro: ResizeObserver | null = null;

  onMount(() => {
    if (!host) return;
    chart = new uPlot(
      {
        width: host.clientWidth,
        height,
        title,
        cursor: { drag: { x: false, y: false } },
        series: [
          { label: 'step' },
          ...series.map((s) => ({ label: s.label, stroke: s.stroke ?? '#60a5fa' })),
        ],
        axes: [{ grid: { stroke: '#1f2937' } }, { grid: { stroke: '#1f2937' } }],
      },
      data as uPlot.AlignedData,
      host,
    );
    ro = new ResizeObserver(() => chart?.setSize({ width: host!.clientWidth, height }));
    ro.observe(host);
  });

  $effect(() => {
    chart?.setData(data as uPlot.AlignedData);
  });

  onDestroy(() => {
    ro?.disconnect();
    ro = null;
    chart?.destroy();
    chart = null;
  });
</script>

<div bind:this={host} class="bg-bg-soft border border-border-soft rounded p-2"></div>
