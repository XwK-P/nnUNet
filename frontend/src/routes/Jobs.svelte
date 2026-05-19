<script lang="ts">
  import JobsTable from '../components/JobsTable.svelte';
</script>

<div class="space-y-2">
  <div class="flex items-baseline gap-3">
    <h2 class="text-lg font-semibold text-slate-100">Jobs</h2>
    <p class="text-[10px] text-amber-400">
      Stop/Restart actions land in Phase 4. Phase 3 shows tracked jobs (currently only CLI-discovered).
    </p>
  </div>
  <div class="mt-4 bg-bg-soft border border-border-soft rounded p-3">
    <JobsTable />
  </div>
</div>
