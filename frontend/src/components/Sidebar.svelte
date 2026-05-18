<script lang="ts">
  import { location } from 'svelte-spa-router';

  type NavItem = { href: string; label: string };

  const items: NavItem[] = [
    { href: '/', label: 'Dashboard' },
    { href: '/datasets', label: 'Datasets' },
    { href: '/train', label: 'Train' },
    { href: '/monitor', label: 'Monitor' },
    { href: '/compare', label: 'Compare' },
    { href: '/predict', label: 'Predict' },
    { href: '/models', label: 'Models' },
    { href: '/jobs', label: 'Jobs' },
    { href: '/settings', label: 'Settings' },
  ];

  function isActive(loc: string, href: string): boolean {
    if (href === '/') return loc === '/' || loc === '';
    return loc === href || loc.startsWith(href + '/');
  }
</script>

<aside class="w-40 bg-bg-soft border-r border-border-soft px-2 py-3 text-xs">
  <nav class="flex flex-col gap-1">
    {#each items as item}
      <a
        href={'#' + item.href}
        class:text-accent={isActive($location, item.href)}
        class="px-2 py-1 rounded hover:bg-bg-panel text-slate-300"
      >
        {#if isActive($location, item.href)}● {/if}{item.label}
      </a>
    {/each}
  </nav>
  <div class="mt-4 text-[10px] text-slate-500 uppercase tracking-wider">System</div>
  <div class="px-2 py-1 text-[10px] text-slate-400">GPU info — pending Phase 0+</div>
  <div class="px-2 py-1 text-[10px] text-slate-400">Disk — pending Phase 0+</div>
</aside>
