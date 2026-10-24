<script lang="ts">
import {
  Check,
  CircleHelp,
  CircleDashed,
  Eye,
  Upload,
  Replace,
  Search,
  X,
  Box,
  FileText,
  Cpu,
  CircuitBoard,
} from "@lucide/svelte";
import Preview from "./Preview.svelte";
import { acceptanceBlock, kinds, type Kind, type Part } from "../lib/demo";
import { t } from "../lib/i18n.svelte";
let {
  part,
  onview,
  onchange,
  onimport,
  onaccept,
  onremove,
}: {
  part: Part;
  onview: (kind: Kind) => void;
  onchange: (kind: Kind) => void;
  onimport: (kind: Kind) => void;
  onaccept: (kind: Kind) => void;
  onremove: (kind: Kind) => void;
} = $props();
const icons = {
  symbol: Cpu,
  footprint: CircuitBoard,
  model: Box,
  datasheet: FileText,
};
</script>
<div class="resources-grid">
  {#each kinds as kind}
    {@const resource=part.resources[kind]}
    {@const Icon=icons[kind]}
    <section class="resource" data-resource={kind}>
      <header>
<span class="resource-name">
<Icon size={14}/>{t(`ux.${kind}`)}</span>
<span class="resource-state" class:success={resource?.accepted} class:warning={resource&&!resource.accepted}>{#if resource?.accepted}<Check size={12}/>{t('ux.accepted')}{:else if resource}<CircleHelp size={12}/>{resource.review||resource.source==='user'?t('ux.choice'):t('ux.review')}{:else}<CircleDashed size={12}/>{t('ux.missing')}{/if}</span>
</header>
      {#if resource}<button class="preview-button" onclick={()=>onview(kind)} aria-label={`${t('ux.view')} ${t(`ux.${kind}`)}`}>
<Preview {kind} pkg={resource.package??part.package} reference={resource.reference??part.ref}/>
</button>{:else}<div class="missing">
<Icon size={28}/>
<span>{t('ux.noPreview')}</span>
<small>{t(`ux.${kind}Help`)}</small>
</div>{/if}
      <div class="resource-meta">
<strong title={resource?.name}>{resource?.name||t(`ux.${kind}Help`)}</strong>
<span>{resource?t(`ux.${resource.source==='manufacturer'?'manufacturerSource':resource.source}`):t('ux.missing')}</span>
</div>
      {#if resource&&!resource.accepted&&(resource.review||resource.source==='user'||acceptanceBlock(part,kind))}<p class="resource-help">{t(acceptanceBlock(part,kind)==='conflict'?'ux.conflict':acceptanceBlock(part,kind)==='packageNeeded'?'ux.packageSearchHint':'ux.userReview')}</p>{/if}
      <div class="resource-actions">
        {#if resource}<button class="btn quiet" onclick={()=>onview(kind)}>
<Eye size={13}/>{t('ux.view')}</button>{/if}
        <button class="btn quiet" onclick={()=>onchange(kind)}>
{#if resource}<Replace size={13}/>{t('ux.change')}{:else}<Search size={13}/>{t('ux.searchResource')}{/if}</button>
        <button class="btn quiet" onclick={()=>onimport(kind)}>
<Upload size={13}/>{t('ux.import')}</button>
        {#if resource&&!resource.accepted}<button class="btn accept" disabled={!!acceptanceBlock(part,kind)} onclick={()=>onaccept(kind)} title={t('ux.notValidation')}>
<Check size={13}/>{t('ux.acceptChanges')}</button>{/if}
        {#if resource}<button class="btn quiet icon" aria-label={`${t('ux.removeProposal')} · ${t(`ux.${kind}`)}`} title={t('ux.removeProposal')} onclick={()=>onremove(kind)}><X size={13}/></button>{/if}
      </div>
    </section>
  {/each}
</div>
<style>
.resources-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--s3);
}
.resource {
  min-width: 0;
  border: 1px solid var(--border);
  background: var(--bg-panel);
}
header {
  height: 34px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 var(--s3);
  border-bottom: 1px solid var(--divider);
  gap: 8px;
}
.resource-name {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: var(--fs-sm);
  font-weight: 600;
}
.resource-state {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: var(--fs-xs);
  color: var(--text-secondary);
}
.success {
  color: var(--success);
}
.warning {
  color: var(--warning);
}
.preview-button {
  height: 144px;
  width: 100%;
  display: block;
  border: 0;
  padding: 0;
  background: var(--bg-workspace);
}
.resource-meta {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 8px 12px 4px;
  font-size: var(--fs-xs);
  color: var(--text-secondary);
}
.resource-meta strong {
  font-size: var(--fs-sm);
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text-primary);
}
.resource-help {
  margin: 4px 12px;
  color: var(--warning);
  font-size: var(--fs-xs);
}
.resource-actions {
  display: flex;
  gap: 2px;
  padding: 4px 6px 8px;
  flex-wrap: wrap;
}
.resource-actions .btn {
  font-size: var(--fs-xs);
  padding: 0 6px;
}
.accept {
  margin-left: auto;
}
.missing {
  height: 144px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: var(--text-secondary);
  background: var(--bg-workspace);
}
small {
  font-size: var(--fs-xs);
}
@media (max-width: 750px) {
  .resources-grid {
    grid-template-columns: 1fr;
  }
}
</style>
