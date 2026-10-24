<script lang="ts">
import { Minus, Plus, Maximize, ExternalLink, Check } from "@lucide/svelte";
import Resources from "./Resources.svelte";
import Preview from "./Preview.svelte";
import Dialog from "./Dialog.svelte";
import {
  candidate,
  copy,
  acceptResource,
  removeResource,
  acceptEligible,
  eligible,
  kinds,
  type Part,
  type Kind,
} from "../lib/demo";
import { t } from "../lib/i18n.svelte";
let { part, onupdate }: { part: Part; onupdate: (part: Part) => void } =
  $props();
let mode = $state<"view" | "change" | "roundtrip" | null>(null),
  kind = $state<Kind>("symbol"),
  zoom = $state(1),
  alternate = $state(false);
let input: HTMLInputElement;
let importError = $state(false);
let groupResult = $state<number | null>(null);
const eligibleCount = $derived(kinds.filter((k) => eligible(part, k)).length);
function open(k: Kind, m: "view" | "change") {
  kind = k;
  mode = m;
  zoom = 1;
  alternate = false;
}
function update(k: Kind, accept = false) {
  const next = accept ? acceptResource(part, k) : copy(part);
  if (!accept) next.resources[k] = candidate(part, k, alternate);
  next.confirmed = false;
  groupResult = null;
  onupdate(next);
  mode = null;
}
function importFile(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0];
  if (!file) return;
  const ext = file.name.split(".").pop()?.toLowerCase();
  const allowed = {
    symbol: ["kicad_sym"],
    footprint: ["kicad_mod"],
    model: ["step", "stp", "wrl"],
    datasheet: ["pdf"],
  }[kind];
  if (!allowed.includes(ext || "")) {
    importError = true;
    return;
  }
  const next = copy(part);
  next.resources[kind] = {
    name: file.name,
    source: "user",
    accepted: false,
    review: "choice",
    package: part.package,
    reference: part.ref,
  };
  next.confirmed = false;
  groupResult = null;
  onupdate(next);
  input.value = "";
  importError = false;
}
</script>
<Resources {part} onview={(k)=>open(k,'view')} onchange={(k)=>open(k,'change')} onimport={(k)=>{kind=k;input.click();}} onaccept={(k)=>update(k,true)} onremove={(k)=>{groupResult=null;onupdate(removeResource(part,k));}}/>
<div class="group-review"><div><span>{t('ux.eligibleCount',{n:eligibleCount})}</span><p>{t('ux.groupHint')}</p></div><button class="btn" disabled={!eligibleCount} onclick={()=>{groupResult=eligibleCount;const next=acceptEligible(part);next.confirmed=false;onupdate(next);}}><Check size={14}/>{t('ux.acceptAll')}</button></div>
{#if groupResult!==null}<p class="notice" role="status">{t('ux.groupResult',{n:groupResult})}</p>{/if}
<input class="sr-only" tabindex="-1" type="file" bind:this={input} onchange={importFile} aria-label={t('ux.import')}/>
{#if importError}<p class="notice error" role="alert">{t('ux.unsupported')}</p>{/if}
{#if mode==='view'}
 <Dialog title={`${t(`ux.${kind}`)} · ${part.resources[kind]?.name||part.ref}`} width={760} onclose={()=>mode=null}>
  <div class="preview-tools">
<span>{t('ux.previewTitle')}</span>
<div class="grow">
</div>
<button class="btn icon quiet" aria-label={t('ux.zoomOut')} title={t('ux.zoomOut')} onclick={()=>zoom=Math.max(.5,zoom-.25)}>
<Minus size={14}/>
</button>
<span>{Math.round(zoom*100)} %</span>
<button class="btn icon quiet" aria-label={t('ux.zoomIn')} title={t('ux.zoomIn')} onclick={()=>zoom=Math.min(3,zoom+.25)}>
<Plus size={14}/>
</button>
<button class="btn icon quiet" aria-label={t('ux.zoomReset')} title={t('ux.zoomReset')} onclick={()=>zoom=1}>
<Maximize size={14}/>
</button>
</div>
  <div class="large-preview">
<Preview {kind} pkg={part.resources[kind]?.package??part.package} reference={part.resources[kind]?.reference??part.ref} {zoom}/>
</div>
  <p class="secondary">{t('ux.notValidation')}</p>
<p>{t('ux.source')} · {t(`ux.${part.resources[kind]?.source==='manufacturer'?'manufacturerSource':part.resources[kind]?.source||'official'}`)}</p>
  {#snippet footer()}<button class="btn" disabled={kind==='datasheet'||kind==='model'} onclick={()=>mode='roundtrip'}>
<ExternalLink size={14}/>{t('ux.editKicad')}</button>
<button class="btn" onclick={()=>mode=null}>{t('common.close')}</button>{/snippet}
 </Dialog>
{:else if mode==='change'}
 <Dialog title={`${t('ux.chooseCandidate')} · ${t(`ux.${kind}`)}`} width={840} onclose={()=>mode=null}>
  <p class="secondary">{t('ux.candidateHint')}</p>
  {#if (kind==='footprint'||kind==='model')&&!part.package}<p class="notice">{t('ux.packageSearchHint')}</p>{/if}
  <div class="comparison">
   <section>
<h3>{t('ux.current')}</h3>{#if part.resources[kind]}<Preview {kind} pkg={part.resources[kind]?.package??part.package} reference={part.resources[kind]?.reference??part.ref}/>{:else}<p class="secondary">{t('ux.noPreview')}</p>{/if}<strong>{part.resources[kind]?.name||t('ux.missing')}</strong>
<p>{part.resources[kind]?t(`ux.${part.resources[kind]?.source==='manufacturer'?'manufacturerSource':part.resources[kind]?.source||'user'}`):'—'}</p>
</section>
   <section>
<h3>{t('ux.alternative')}</h3>
<Preview {kind} pkg={part.package} reference={part.ref}/>
<select class="input" bind:value={alternate} aria-label={t('ux.alternative')}>
<option value={false}>{t('ux.official')}</option>
<option value={true}>{t('ux.managed')}</option>
</select>
<strong>{candidate(part,kind,alternate).name}</strong>
<span>{t('ux.review')}</span>
</section>
  </div>
  {#snippet footer()}<button class="btn" onclick={()=>mode=null}>{t('ux.keep')}</button>
<button class="btn primary" disabled={(kind==='footprint'||kind==='model')&&!part.package} onclick={()=>update(kind)}>
<Check size={14}/>{t('ux.choose')}</button>{/snippet}
 </Dialog>
{:else if mode==='roundtrip'}
 <Dialog title={t('ux.roundtripTitle')} onclose={()=>mode=null}>
<p>{t('ux.roundtripText')}</p>
<p class="notice">{t('ux.roundtripLimit')}</p>
</Dialog>
{/if}
<style>
.group-review {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-top: 12px;
  flex-wrap: wrap;
  font-size: var(--fs-sm);
}
.group-review p {
  color: var(--text-secondary);
  font-size: var(--fs-xs);
  margin: 4px 0;
}
.preview-tools {
  display: flex;
  align-items: center;
  gap: 8px;
}
.grow {
  flex: 1;
}
.large-preview {
  height: 330px;
}
.large-preview :global(svg) {
  max-height: none;
}
.comparison {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}
.comparison section {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
}
.comparison section :global(.preview) {
  height: 170px;
}
.comparison strong {
  overflow-wrap: anywhere;
  font-size: var(--fs-sm);
}
.comparison p {
  margin: 0;
}
.secondary {
  color: var(--text-secondary);
}
.notice {
  color: var(--info);
  font-size: var(--fs-sm);
}
.error {
  color: var(--danger-text);
}
</style>
