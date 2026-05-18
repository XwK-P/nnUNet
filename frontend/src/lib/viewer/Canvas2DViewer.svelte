<script lang="ts">
  let { src, alt = 'preview' }: { src: string; alt?: string } = $props();
</script>

<div class="w-full bg-bg-soft border border-border-soft rounded p-2 flex items-center justify-center">
  <img {src} {alt} class="max-w-full max-h-[480px] object-contain" />
</div>
