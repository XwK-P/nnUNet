<script lang="ts">
  import Router from 'svelte-spa-router';
  import Sidebar from './components/Sidebar.svelte';
  import WorkspaceHeader from './components/WorkspaceHeader.svelte';
  import { createThemeStore } from './lib/stores/theme';

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
