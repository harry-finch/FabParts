<script lang="ts">
// Intégration globale : aperçu, consentement explicite et reprise conservatrice du journal.
import {onDestroy,untrack} from 'svelte';
import {invoke} from '@tauri-apps/api/core';
import Disclosure from '../../fabparts-ux/src/components/Disclosure.svelte';
import {reportDate} from './validation_text';
import {IntegrationController,initialIntegration} from './integration';
import {it,integrationError,type IntegrationKey} from './integration_text';
let {id,versions,writable=false,disabled=false,revision=0,onbusy=()=>{}}:{id:string;versions:number[];writable?:boolean;disabled?:boolean;revision?:number;onbusy?:(value:boolean)=>void}=$props();
let view=$state(initialIntegration());let version=$state(0);
const flow=new IntegrationController(invoke,next=>{view=next;onbusy(next.busy);});
$effect(()=>{const collection=id;const update=revision;untrack(()=>{void update;void flow.select(collection,view.data?.target||'');});});
$effect(()=>{if(!versions.includes(version))version=versions[0]||0;});
onDestroy(()=>{flow.dispose();onbusy(false);});
const busy=$derived(view.busy||disabled);
const blocked=$derived(busy||!writable||!!view.data?.kicad_open);
</script>
<section class="integration" aria-busy={view.busy}>
<h2>{it('title')}</h2>
{#if view.busy}<p role="status">{it('busy')}</p>{/if}
{#if view.error}<p class="integration-error" role="alert">{integrationError(view.error,view.message)}</p><Disclosure id="integration-error" label={it('details')}><p class="integration-path">{view.error} · {view.message}</p></Disclosure><button class="btn" disabled={busy} onclick={()=>flow.reconnect()}>{it('reconnect')}</button>{/if}
{#if view.notice}<p role="status">{it('confirmed')}</p>{/if}
{#if view.data}
{#if !view.data.targets.length}<p class="secondary">{it('none')}</p>{:else}
<div class="integration-actions"><label>{it('target')}<select class="input" value={view.data.target} disabled={busy} onchange={e=>flow.choose(e.currentTarget.value)}>{#each view.data.targets as target}<option value={target.id}>KiCad {target.id}</option>{/each}</select></label><button class="btn" disabled={busy} onclick={()=>flow.refresh()}>{it('refresh')}</button></div>
<p><strong>{it(view.data.state as IntegrationKey)}</strong> · {it('active')} : {view.data.active??it('notActive')} · {it('latest')} : {view.data.latest??'—'}</p>
{#if view.data.publication_error}<p class="integration-error">{integrationError('ERROR',view.data.publication_error)}</p>{/if}
{#if view.data.error}<p class="integration-error">{integrationError('ERROR',view.data.error)}</p><Disclosure id="integration-status-error" label={it('details')}><p class="integration-path">{view.data.error}</p></Disclosure>{/if}
<p class="secondary">{it('close')}</p>
{#if view.data.kicad_open}<p role="status">{it('open')}</p>{/if}
{#if !writable}<p class="secondary">{it('readonly')}</p>{/if}
{#if view.data.state==='RECONCILE_REQUIRED'}<p>{it('reconcile')}</p>{/if}
{#if view.data.state==='RECOVERY_REQUIRED'}<button class="btn" disabled={blocked} onclick={()=>flow.prepareRecovery()}>{it('recovery')}</button>{:else}
<div class="integration-actions"><label>{it('version')}<select class="input" bind:value={version} disabled={busy} onchange={()=>flow.cancel()}>{#each versions as v}<option value={v}>v{v}</option>{/each}</select></label><button class="btn" disabled={blocked||!version||!!view.data.publication_error} onclick={()=>flow.prepare(Number(version))}>{it(view.data.active?'activate':'install')}</button>{#if view.data.previous}<button class="btn" disabled={blocked||!!view.data.publication_error} onclick={()=>flow.prepare(view.data!.previous!)}>{it('rollback')} v{view.data.previous}</button>{/if}</div>{/if}
<button class="btn" disabled={busy||!view.data.active||view.data.state==='RECOVERY_REQUIRED'} onclick={()=>flow.verify()}>{it('verify')}</button>
{#if view.data.verified&&view.data.checked_at}<p role="status">{it('verified')} · {reportDate(view.data.checked_at)}</p>{/if}
{#if view.summary}<div class="integration-summary"><h3>{it('confirmTitle')} · KiCad {view.summary.target}{#if view.summary.version} · v{view.summary.version}{/if}</h3><p>{view.summary.collection_name}</p><p>{view.summary.tables.join(' + ')}</p>{#if view.summary.action==='restore_previous_tables'}<p>{it('restore')}</p>{:else}<Disclosure id="integration-summary-details" label={it('details')}><p class="integration-path">{view.summary.nickname}</p>{#each view.summary.uris||[] as uri}<p class="integration-path">{uri}</p>{/each}</Disclosure>{/if}<label class="integration-consent"><input type="checkbox" checked={view.confirmed} disabled={blocked} onchange={e=>flow.confirm(e.currentTarget.checked)}/>{it('confirm')}</label><div class="integration-actions"><button class="btn primary" disabled={blocked||!view.confirmed} onclick={()=>flow.apply()}>{it('apply')}</button><button class="btn" disabled={busy} onclick={()=>flow.cancel()}>{it('cancel')}</button></div></div>{/if}
<Disclosure id="integration-details" label={it('details')}><p class="integration-path">{view.data.targets.find(t=>t.id===view.data?.target)?.configuration}</p>{#each view.data.tables as table}<p>{table.name} · {it(table.present?'present':'absent')}</p>{/each}<h3>{it('installed')}</h3>{#each view.data.installed||[] as installed}<p>{installed.name} · v{installed.version}</p>{/each}<h3>{it('history')}</h3>{#each view.data.operations as op}<p>v{op.version} · {reportDate(op.date)}</p>{/each}</Disclosure>
{/if}{/if}
</section>
<style>
.integration{border-top:1px solid var(--border);margin-top:var(--s4);padding-top:var(--s3);min-width:0}.integration h2{font-size:var(--fs-md)}.integration-actions{display:flex;gap:var(--s2);align-items:end;flex-wrap:wrap;margin:var(--s2) 0}.integration-actions label{display:flex;flex-direction:column;gap:var(--s1)}.integration-consent{display:flex;gap:var(--s2);align-items:center;margin:var(--s3) 0}.integration-path,.integration p{overflow-wrap:anywhere}.integration-path{font-size:var(--fs-sm)}.integration-summary{border-top:1px solid var(--border);padding-top:var(--s2);margin-top:var(--s3)}.integration-error{color:var(--danger-text)}button{max-width:100%;white-space:normal;height:auto;min-height:var(--control-h)}
</style>
