<script lang="ts">
import { Check, RefreshCw, TriangleAlert, CircleDashed } from "@lucide/svelte";
import { t } from "../lib/i18n.svelte";
import type { Sync } from "../lib/demo";
let { state }: { state: Sync } = $props();
</script>
<span class="sync" class:error={state==='error'} class:busy={state==='syncing'}>{#if state==='error'}<TriangleAlert size={13}/>{:else if state==='syncing'}<RefreshCw size={13}/>{:else if state==='available'}<Check size={13}/>{:else}<CircleDashed size={13}/>{/if}{t(`ux.${state}`)} <small>· {t('ux.simulated')}</small>
</span>
<style>
.sync {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: var(--fs-sm);
  color: var(--text-secondary);
  flex-wrap: wrap;
}
.error {
  color: var(--danger-text);
}
.busy {
  color: var(--info);
}
small {
  font-size: var(--fs-xs);
}
</style>
