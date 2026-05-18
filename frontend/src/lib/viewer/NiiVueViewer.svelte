<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { Niivue } from '@niivue/niivue';

  let {
    volumeUrl,
    overlayUrl = undefined,
    overlayOpacity = 0.5,
    axis = 0,
    slice = undefined as number | undefined,
  }: {
    volumeUrl: string;
    overlayUrl?: string;
    overlayOpacity?: number;
    axis?: number;
    slice?: number;
  } = $props();

  let canvas: HTMLCanvasElement | undefined;
  let nv: InstanceType<typeof Niivue> | null = null;

  onMount(async () => {
    if (!canvas) return;
    nv = new Niivue({ logLevel: 'warn' });
    nv.attachToCanvas(canvas);
    const volumes: { url: string; opacity?: number }[] = [{ url: volumeUrl }];
    if (overlayUrl) volumes.push({ url: overlayUrl, opacity: overlayOpacity });
    await nv.loadVolumes(volumes);
    nv.setSliceType(axis);
  });

  $effect(() => {
    if (!nv) return;
    nv.setSliceType(axis);
    if (overlayUrl) nv.setOpacity(1, overlayOpacity);
  });

  onDestroy(() => {
    // NiiVue does not expose a tidy dispose; let GC handle it after canvas detach.
    nv = null;
  });
</script>

<div class="w-full h-[480px] bg-bg-soft border border-border-soft rounded">
  <canvas bind:this={canvas} class="w-full h-full block"></canvas>
</div>
