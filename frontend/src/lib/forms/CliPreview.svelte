<script lang="ts">
  let { cli }: { cli: string } = $props();
  let copied = $state(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(cli);
      copied = true;
      setTimeout(() => (copied = false), 1500);
    } catch {
      /* clipboard may be unavailable in test env */
    }
  }
</script>

<div class="bg-bg-soft border border-border-soft rounded p-2 font-mono text-[11px] flex gap-2 items-start">
  <code class="flex-1 break-all whitespace-pre-wrap">{cli}</code>
  <button
    type="button"
    class="px-2 py-0.5 bg-bg-panel rounded text-slate-300 hover:bg-bg-soft shrink-0"
    onclick={copy}
  >
    {copied ? 'copied!' : 'copy'}
  </button>
</div>
