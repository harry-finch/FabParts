<script lang="ts">
// Publications de collection : confirmation explicite, intégrité ponctuelle, reconstruction native.
import {onDestroy,untrack} from 'svelte';
import {invoke} from '@tauri-apps/api/core';
import {pt} from './publication_text';
import {findingLabel,reportDate} from './validation_text';
import {i18n} from '../../fabparts-ux/src/lib/i18n.svelte';
import Disclosure from '../../fabparts-ux/src/components/Disclosure.svelte';
import {PublicationController,initialPublications,publicationRecovery} from './publications';
let {id,writable=false,onbusy=()=>{},onvalidation=()=>{}}:{id:string;writable?:boolean;onbusy?:(busy:boolean)=>void;onvalidation?:()=>void}=$props();
let view=$state(initialPublications());
const flow=new PublicationController(invoke,publicationRecovery,next=>{view=next;onbusy(next.busy);});

$effect(()=>{const identity=id;untrack(()=>void flow.select(identity));});
onDestroy(()=>{flow.dispose();onbusy(false);});
const date=reportDate;
const check=(state:string)=>state==='PASS'?pt('integrity_verified'):state==='FAILED'?pt('verification_failed'):state==='CHECKING'?pt('checking'):pt('not_checked');
</script>
<section class="publications" aria-busy={view.busy}>
<h1>{pt('kicad_publications')}</h1>
<p class="secondary">{pt('retained_versions_for_kicad_project_integration')}</p>
{#if view.busy}<p role="status">{pt('operation_in_progress')}</p>{/if}
{#if view.error}<p class="error" role="alert">{pt('operation_not_confirmed')} {view.error} {view.errorMessage}</p>{/if}
{#if view.pending}<div class="pending" role="alert"><p>{pt('a_publication_needs_reconciliation_check_its')} v{view.pending.version}</p><button class="btn" disabled={view.busy} onclick={()=>flow.recover()}>{pt('reconnect_and_check_outcome')}</button></div>{/if}
{#if view.notice}<p role="status" class="secondary">{view.notice==='committed'?pt('committed_publication_confirmed_in_history'):view.notice==='reserved'?pt('number_reserved_without_a_valid_publication'):view.notice==='absent'?pt('no_committed_version_prepare_again_before'):pt('verified_reconstruction')+view.notice.replace('rebuilt:','')}</p>{/if}
{#if view.history}
<div class="publication-toolbar"><h2>{view.history.name}</h2><span>{view.history.count} {pt('components')}</span><span class="grow"></span><button class="btn" disabled={view.busy} onclick={()=>flow.refresh()}>{pt('refresh')}</button></div>
<p>{pt('collection_qualification')} : <strong>{view.history.state}</strong> · {pt('proposed_version')} : {view.history.proposed??'—'}</p>
{#if !view.history.eligible}<p class="secondary">{pt('publication_blocked_validate_the_collection_fix')}</p>{/if}
<div class="publication-actions"><button class="btn" disabled={view.busy} onclick={onvalidation}>{pt('library_qualification')}</button>{#if writable&&!view.summary}<button class="btn primary" disabled={view.busy||!view.history.eligible||!view.history.proposed||!!view.pending} onclick={()=>flow.prepare()}>{pt('publish_a_new_version')}</button>{:else if !writable}<span class="secondary">{pt('read_only')}</span>{/if}</div>
{#if view.summary}
<div class="publication-summary"><h2>{pt('confirm_publication')} · v{view.summary.version}</h2><p>{view.summary.name} · {view.summary.count} {pt('components')} · {view.summary.level}{#if view.summary.warnings_accepted} · {pt('warnings_accepted')} ({view.summary.warnings}){/if}</p>
{#if view.summary.warning_codes?.length}<p class="secondary">{view.summary.warning_codes.map(findingLabel).join(' · ')}</p>{/if}
{#each view.summary.parts as part}<div class="publication-part"><strong>{part.name}</strong><span class="secondary">{part.resources.map(r=>`${r.role} : ${r.name} (${r.origin})`).join(' · ')}</span></div>{/each}
<div class="publication-actions"><button class="btn quiet" disabled={view.busy||view.summary.offset===0} onclick={()=>flow.prepare(view.summary!.offset-50)}>{pt('previous')}</button><span>{view.summary.offset+1}–{Math.min(view.summary.offset+50,view.summary.count)} / {view.summary.count}</span><button class="btn quiet" disabled={view.busy||view.summary.offset+50>=view.summary.count} onclick={()=>flow.prepare(view.summary!.offset+50)}>{pt('next')}</button></div>
<p class="secondary">{pt('immutable_version_builder_restrictions_still_apply')}</p>
<label class="publication-consent"><input type="checkbox" checked={view.confirmed} disabled={view.busy} onchange={e=>flow.confirm(e.currentTarget.checked)}/>{pt('i_confirm_publication_of_this_collection')}</label><div class="publication-actions"><button class="btn primary" disabled={view.busy||!view.confirmed} onclick={()=>flow.publish()}>{pt('confirm_and_publish')}</button><button class="btn" disabled={view.busy} onclick={()=>flow.cancel()}>{pt('cancel')}</button></div></div>
{/if}
<h2>{pt('history')}</h2>
{#if !view.history.total}<p class="secondary">{pt('no_published_version')}</p>{/if}
{#if view.history.reserved_count}<p class="secondary">{view.history.reserved_count} {pt('reserved_number_s_without_a_committed')}</p>{/if}
{#each view.history.versions as version}<div class="publication-version"><div><strong>v{version.version} · {version.collection_name}</strong><p class="secondary">{date(version.created_at)} · {check(view.checks[version.version]||version.verification)}</p></div><div class="publication-actions"><button class="btn" disabled={view.busy} onclick={()=>flow.details(version.version)}>{pt('details')}</button><button class="btn" disabled={view.busy} onclick={()=>flow.verify(version.version)}>{pt('verify_integrity')}</button>{#if writable}<button class="btn" disabled={view.busy||!!view.pending} onclick={()=>flow.rebuild(version.version,i18n.locale)}>{pt('rebuild_into_a_new_folder')}</button>{/if}</div></div>{/each}
<div class="publication-actions"><button class="btn quiet" disabled={view.busy||view.history.offset===0} onclick={()=>flow.refresh(view.history!.offset-50)}>{pt('previous')}</button><span>{view.history.total} {pt('versions')}</span><button class="btn quiet" disabled={view.busy||view.history.offset+50>=view.history.total} onclick={()=>flow.refresh(view.history!.offset+50)}>{pt('next')}</button></div>
{#if view.detail}<div class="publication-summary"><h2>{pt('historical_snapshot')} · v{view.detail.version}</h2><p>{view.detail.name} · {view.detail.count} {pt('components')} · {view.detail.level} · {view.detail.file_count} {pt('files')}</p>{#each view.detail.parts as part}<div class="publication-part"><strong>{part.name}</strong><span class="secondary">{part.resources.map(r=>`${r.role} : ${r.name}`).join(' · ')}</span></div>{/each}<div class="publication-actions"><button class="btn quiet" disabled={view.busy||view.detail.offset===0} onclick={()=>flow.details(view.detail!.version,view.detail!.offset-50)}>{pt('previous')}</button><button class="btn quiet" disabled={view.busy||view.detail.offset+50>=view.detail.count} onclick={()=>flow.details(view.detail!.version,view.detail!.offset+50)}>{pt('next')}</button></div><Disclosure id="publication-technical" label={pt('technical_details')}><p class="digest">SHA-256 {view.detail.manifest_sha256}</p><p class="digest">{view.detail.library}</p>{#each view.detail.files||[] as file}<p class="digest">{file}</p>{/each}</Disclosure></div>{/if}
{:else if !view.busy}<button class="btn" onclick={()=>flow.refresh()}>{pt('retry_reading')}</button>{/if}
</section>
<style>
.publications{max-width:1100px;min-width:0}.publications h1{margin-top:var(--s4)}.publications h2{font-size:var(--fs-md)}.publication-toolbar,.publication-actions{display:flex;align-items:center;gap:var(--s2);flex-wrap:wrap}.publication-actions{margin:var(--s2) 0}.publication-version,.publication-summary,.pending{padding:var(--s3) 0;border-top:1px solid var(--border)}.publication-version{display:flex;justify-content:space-between;gap:var(--s3);flex-wrap:wrap}.publication-part{display:flex;flex-direction:column;gap:var(--s1);padding:var(--s2) 0;overflow-wrap:anywhere}.publication-consent{display:flex;align-items:center;gap:var(--s2);margin:var(--s3) 0}.digest{overflow-wrap:anywhere;font-size:var(--fs-sm)}.error{color:var(--danger-text)}button{max-width:100%;white-space:normal;height:auto;min-height:var(--control-h)}
</style>
