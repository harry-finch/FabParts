<!-- Vue de lecture : géométrie des quatre ressources UX 02, métadonnées réelles et aucun aperçu simulé. -->
<script lang="ts">
import { Box, Cpu, CircuitBoard, FileText, CircleDashed } from '@lucide/svelte';
import type { Detail } from './controller';
import { text as t, roles, roleLabel } from './text';
let { detail }: { detail: Detail } = $props();
const icons = { SYMBOL:Cpu, FOOTPRINT:CircuitBoard, MODEL_3D:Box, DATASHEET:FileText };
</script>
<div class="resources-grid">
{#each roles as role}
  {@const assets = detail.associated_assets.filter(a => a.type === role)}
  {@const external = detail.selections.filter(s => s.type === role && s.external)}
  {@const present = assets.length + external.length > 0}
  {@const Icon = icons[role as keyof typeof icons]}
  <section class="resource">
    <header><span><Icon size={14}/>{roleLabel(role)}</span><span class="resource-state"><CircleDashed size={12}/>{t(present ? 'qualificationShort' : 'missing')}</span></header>
    <div class="missing"><Icon size={28}/><span>{t('preview')}</span></div>
    <div class="resource-meta">
      {#each assets as asset}<strong>{asset.name}</strong><span>{t(asset.selected ? 'selected' : 'associated')} · {asset.origin}</span><span>{asset.file?.name || t('unknown')}</span>{/each}
      {#each external as selection}<strong>{selection.external?.library}:{selection.external?.name}</strong><span>{t('selected')} · {t('external')}</span>{/each}
      {#if !present}<span>{t('noResource')}</span>{/if}
    </div>
  </section>
{/each}
</div>
<style>
/* Same dimensions/tokens as the validated Resources.svelte, whose data/actions are demo-specific. */
.resources-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:var(--s3)}
.resource{min-width:0;border:1px solid var(--border);background:var(--bg-panel)}
header{min-height:34px;display:flex;align-items:center;justify-content:space-between;padding:0 var(--s3);border-bottom:1px solid var(--divider);gap:8px;flex-wrap:wrap}
header span{display:flex;align-items:center;gap:8px;font-size:var(--fs-sm);font-weight:600}
header .resource-state{gap:4px;font-size:var(--fs-xs);font-weight:400;color:var(--text-secondary)}
.missing{height:144px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:8px;padding:8px;text-align:center;color:var(--text-secondary);background:var(--bg-workspace);font-size:var(--fs-xs)}
.resource-meta{display:flex;flex-direction:column;gap:4px;padding:8px 12px;font-size:var(--fs-xs);color:var(--text-secondary);overflow-wrap:anywhere}
.resource-meta strong{font-size:var(--fs-sm);font-weight:500;color:var(--text-primary)}
@media (min-width:1650px){.missing{height:184px}}
@media (max-width:750px){.resources-grid{grid-template-columns:1fr}}
</style>
