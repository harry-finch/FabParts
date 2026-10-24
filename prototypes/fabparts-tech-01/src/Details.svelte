<script lang="ts">
import { Box, Folder, Cpu, CircuitBoard, FileText } from '@lucide/svelte';
import Section from '../../fabparts-ux/src/components/Section.svelte';
import Disclosure from '../../fabparts-ux/src/components/Disclosure.svelte';
import type { Detail } from './controller';
import Resources from './Resources.svelte';
import { text as t, stateLabel, roles, roleLabel } from './text';
let { detail, full = false }: { detail: Detail; full?: boolean } = $props();
const icons = { SYMBOL:Cpu, FOOTPRINT:CircuitBoard, MODEL_3D:Box, DATASHEET:FileText };
</script>
{#snippet properties()}
<Section id="tech-properties" title={t('properties')}>
  <dl><dt>{t('manufacturer')}</dt><dd>{detail.manufacturer || t('unknown')}</dd>
  <dt>MPN</dt><dd>{detail.mpn || t('unknown')}</dd><dt>{t('package')}</dt><dd>{detail.package?.name || t('unknown')}</dd>
  <dt>{t('category')}</dt><dd>{detail.category || t('unknown')}</dd></dl>
</Section>
{/snippet}
{#if full}
<div class="identity-heading"><div><span class="eyebrow">{detail.category || t('unknown')}</span><h1>{detail.reference}</h1><p>{detail.manufacturer || t('unknown')} · {detail.description || t('unknown')}</p></div><div class="identity-state"><span>{stateLabel(detail.state)}</span><span class="secondary small">{t('qualification')}</span></div></div>
<div class="detail-columns"><div class="detail-resources"><h2 class="section-heading">{t('resources')}</h2><Resources {detail}/></div><aside class="properties">
{@render properties()}
<Section id="tech-membership" title={t('libraries')}><div class="members">{#each detail.libraries as library}<span><Folder size={12}/>{library.name}</span>{:else}<span class="secondary">{t('unknown')}</span>{/each}</div></Section>
{@render technical()}
</aside></div>
{:else}
<div class="inspector-heading">
  <span class="eyebrow">{detail.category || t('unknown')}</span>
  <h2>{detail.reference}</h2><p>{detail.manufacturer || t('unknown')}</p><p>{detail.description}</p>
  <div class="members">{#each detail.libraries as library}<span><Folder size={12}/>{library.name}</span>{/each}</div>
</div>
<Section id="tech-state" title={t('state')}>
  <span>{stateLabel(detail.state)}</span><p class="secondary small">{t('qualification')}</p>
</Section>
{@render properties()}
<Section id="tech-resources" title={t('resources')}>
  {#each roles as role}
    {@const assets = detail.associated_assets.filter(a => a.type === role)}
    {@const external = detail.selections.filter(s => s.type === role && s.external)}
    {@const Icon = icons[role as keyof typeof icons]}
    <div class="resource-meta">
      <div class="resource-title"><Icon size={16}/><strong>{roleLabel(role)}</strong></div>
      {#if !assets.length && !external.length}<span class="secondary small">{t('missing')}</span>{/if}
      {#each assets as asset}
        <strong class="resource-name">{asset.name}</strong><span class="secondary small">{t(asset.selected ? 'selected' : 'associated')} · {asset.origin}</span>
      {/each}
      {#each external as selection}
        <strong class="resource-name">{selection.external?.library}:{selection.external?.name}</strong>
        <span class="secondary small">{t('selected')} · {t('external')}</span>
      {/each}
      {#if assets.length || external.length}<span class="secondary small">{t('preview')}</span>{/if}
    </div>
  {/each}
</Section>
{@render technical()}
{/if}
{#if full && detail.documents.length}
  <Section id="tech-documents" title={t('documents')}>
    {#each detail.documents as document}<p>{document.title} · {document.revision || '—'} · {document.language || '—'}</p>{/each}
  </Section>
{/if}
{#snippet technical()}
<div class="advanced"><Disclosure id="tech-resource-meta" label={t('technical')}>
  <dl><dt>UUID</dt><dd>{detail.id}</dd><dt>{t('state')}</dt><dd>{detail.state}</dd></dl>
  {#each detail.associated_assets as asset}
    <strong>{asset.name}</strong><dl><dt>{t('file')}</dt><dd>{asset.file?.name || t('unknown')}</dd><dt>{t('state')}</dt><dd>{asset.validation_state}</dd><dt>{t('source')}</dt><dd>{asset.source || '—'}</dd><dt>{t('hash')}</dt><dd>{asset.file?.sha256 || '—'}</dd></dl>
  {/each}
  {#each detail.selections.filter(s => s.external) as selection}<dl><dt>KiCad</dt><dd>{selection.external?.relative_path}</dd><dt>{t('hash')}</dt><dd>{selection.external?.sha256}</dd></dl>{/each}
</Disclosure></div>
{/snippet}
<style>
.resource-meta{display:flex;flex-direction:column;gap:6px;padding:8px 0;border-bottom:1px solid var(--divider)}
.resource-title{display:flex;gap:8px;align-items:center}.resource-title strong{font-weight:500}.resource-name{font-size:var(--fs-sm);font-weight:500;overflow-wrap:anywhere}
dd{overflow-wrap:anywhere;min-width:0}p{margin:4px 0}
</style>
