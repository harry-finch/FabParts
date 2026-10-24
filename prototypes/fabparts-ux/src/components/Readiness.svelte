<script lang="ts">
import { Check, CircleDashed, CircuitBoard } from "@lucide/svelte";
import { t } from "../lib/i18n.svelte";
import type { Ready } from "../lib/demo";
let { state }: { state: Ready } = $props();
</script>
<span class="readiness" class:ready={state!=='draft'} class:draft={state==='draft'}>{#if state==='pcb'}<Check size={13}/>{:else if state==='schematic'}<CircuitBoard size={13}/>{:else}<CircleDashed size={13}/>{/if}{t(`ux.${state}`)}</span>
<style>
.readiness {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: var(--fs-sm);
  white-space: nowrap;
}
.ready {
  color: var(--success);
}
.draft {
  color: var(--text-secondary);
}
</style>
