<script lang="ts">
  import { onMount } from 'svelte';
  import Router from 'svelte-spa-router';
  import Sidebar from './components/Sidebar.svelte';
  import WorkspaceHeader from './components/WorkspaceHeader.svelte';
  import { endpoints } from './lib/api';
  import { createThemeStore } from './lib/stores/theme';
  import { useNotifications } from './lib/useNotifications';

  import Dashboard from './routes/Dashboard.svelte';
  import Datasets from './routes/Datasets.svelte';
  import Train from './routes/Train.svelte';
  import Monitor from './routes/Monitor.svelte';
  import Compare from './routes/Compare.svelte';
  import Predict from './routes/Predict.svelte';
  import Models from './routes/Models.svelte';
  import Jobs from './routes/Jobs.svelte';
  import Settings from './routes/Settings.svelte';

  createThemeStore(); // initializes html.dark class

  const routes = {
    '/': Dashboard,
    '/datasets': Datasets,
    '/train': Train,
    '/monitor': Monitor,
    '/compare': Compare,
    '/predict': Predict,
    '/models': Models,
    '/jobs': Jobs,
    '/settings': Settings,
    '*': Dashboard,
  };

  // Poll /api/jobs every 5s; pipe terminal transitions into the system-notification helper.
  onMount(() => {
    const notifier = useNotifications();
    const seen = new Map<number, string>();
    const tick = async (): Promise<void> => {
      try {
        const jobs = await endpoints.getJobs();
        for (const j of jobs) {
          if (seen.get(j.id) !== j.status) {
            seen.set(j.id, j.status);
            notifier.fire({
              jobId: j.id,
              kind: j.kind,
              // Cast through any — server statuses are a superset of the enum here.
              status: j.status as any,
            });
          }
        }
      } catch {
        /* swallow — Notifications shouldn't break the app */
      }
    };
    const id = setInterval(tick, 5000);
    tick();
    return () => clearInterval(id);
  });
</script>

<div class="flex flex-col h-full bg-bg text-slate-100">
  <WorkspaceHeader />
  <div class="flex flex-1 min-h-0">
    <Sidebar />
    <main class="flex-1 overflow-auto p-4">
      <Router {routes} />
    </main>
  </div>
</div>
