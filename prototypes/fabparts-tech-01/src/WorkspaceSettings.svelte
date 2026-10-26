<script lang="ts">
// Paramètres de données : opérations natives, progression exclusive, reprise explicite après restauration.
import {onMount} from 'svelte';
import {invoke} from '@tauri-apps/api/core';
import {ArrowLeft,Save,FolderOpen,RotateCcw} from '@lucide/svelte';
import Section from '../../fabparts-ux/src/components/Section.svelte';
import ExternalSettings from './ExternalSettings.svelte';
import {i18n} from '../../fabparts-ux/src/lib/i18n.svelte';
import {WorkspaceController,workspaceInitial,type WorkspaceState} from './workspace';
import {workspaceText as t} from './workspace_text';
let {onback,onbusy,onblocked,onrestart}:{onback:()=>void;onbusy:(value:boolean)=>void;onblocked:(value:boolean)=>void;onrestart:()=>Promise<void>}=$props();
let state=$state<WorkspaceState>(workspaceInitial());
const controller=new WorkspaceController(invoke,next=>{state=next;onbusy(next.busy);onblocked(next.restart);});
onMount(()=>{void controller.load();return()=>onbusy(false);});
async function restart(){await onrestart();}
</script>
<section class="workspace-settings" aria-busy={state.busy}>
 <header><button class="btn quiet" disabled={state.busy} onclick={onback}><ArrowLeft size={14}/>{t('back')}</button><h1>{t('settings')}</h1></header>
 {#if state.info}
 <Section id="workspace-active" step={1} title={t('active')}>
  <p class="secondary">{t('personal')}</p><p class="path">{state.info.path}</p>
  <p class="secondary">{t('backups')}</p><p class="path">{state.info.backups}</p>
 </Section>
 <Section id="workspace-backup" step={2} title={t('save')}>
  <p class="secondary">{t('help')}</p>
  <button class="btn primary" disabled={state.busy||state.restart} onclick={()=>void controller.backup()}><Save size={14}/>{t('save')}</button>
  {#if state.backup}<p class="path secondary">{state.backup}</p>{/if}
 </Section>
 <Section id="workspace-restore" step={3} title={t('restore')}>
  <p class="secondary">{t('restoreHelp')}</p>
  <button class="btn" disabled={state.busy||state.restart} onclick={()=>void controller.select(i18n.locale)}><FolderOpen size={14}/>{t('choose')}</button>
  {#if state.selection}
   <p>{t('verified')} · {state.selection.files} {t('files')} · {t('schema')} {state.selection.schema}</p>
   <p class="secondary">{t('date')} {new Date(state.selection.created_at).toLocaleString(i18n.locale)}</p>
   <button class="btn" disabled={state.busy} onclick={()=>void controller.restore(i18n.locale)}>{t('confirm')}</button>
  {/if}
 </Section>
 <ExternalSettings disabled={state.busy||state.restart}/>
 {:else if !state.error}<p>{t('loading')}</p>{/if}
 {#if state.busy}<p role="status">{t('busy')}</p>{/if}
 {#if state.error}<div role="alert"><p class="error-text">{t('failed')}</p><p class="secondary">{state.error}</p><p class="secondary">{t('uncertain')}</p></div>{/if}
 {#if state.message}<p role="status">{t(state.message)}</p>{/if}
 {#if state.restart}<button class="btn" disabled={state.busy} onclick={()=>void restart()}><RotateCcw size={14}/>{t('restart')}</button>{/if}
</section>
<style>
.workspace-settings{overflow:auto;padding:var(--s4);display:flex;flex-direction:column;gap:var(--s4);max-width:100%;min-width:0}
header{display:flex;align-items:center;gap:var(--s3);flex-wrap:wrap}h1{font-size:var(--fs-lg);margin:0}
p{margin:var(--s2) 0;max-width:80ch}.path{overflow-wrap:anywhere;font-size:var(--fs-sm)}
.error-text{color:var(--danger-text)}
</style>
