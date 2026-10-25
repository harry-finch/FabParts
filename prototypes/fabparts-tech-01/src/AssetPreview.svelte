<script lang="ts">
import { invoke } from '@tauri-apps/api/core';
import { Maximize2, X, RefreshCw } from '@lucide/svelte';
import type { Detail } from './controller';
import { PreviewController, type Preview } from './preview';
import DrawingView from './DrawingView.svelte';
import PdfView from './PdfView.svelte';
let { detail, role }: {detail:Detail;role:string}=$props();
let value=$state<Preview>({status:'loading'}), assetId=$state(''), dialog:HTMLDialogElement, large=$state(false);
let candidates=$derived([...detail.associated_assets.filter(a=>a.type===role).map(a=>({id:a.id,name:a.name})), ...(role==='DATASHEET'?detail.documents.filter(d=>!detail.associated_assets.some(a=>a.id===d.asset_id)).map(d=>({id:d.asset_id,name:d.title})):[])]);
const controller=new PreviewController(invoke,p=>value=p);
$effect(()=>{void controller.load(detail.id,role,assetId);return ()=>controller.dispose();});
function enlarge(){large=true;dialog.showModal();}function close(){large=false;dialog.close();}
const labels:Record<string,string>={loading:'Chargement…',absent:'Aucune ressource sélectionnée',missing:'Ressource introuvable',inaccessible:'Ressource inaccessible',unsupported:'Format non pris en charge',too_large:'Aperçu hors limites',error:'Erreur de lecture'};
</script>
{#if candidates.length}<label class="candidate">Aperçu <select bind:value={assetId}><option value="">Sélection courante</option>{#each candidates as c}<option value={c.id}>{c.name} · associé</option>{/each}</select></label>{/if}
{#snippet content(expanded:boolean)}
{#if value.status==='ready'}{#if value.drawings?.length}<DrawingView drawings={value.drawings} large={expanded}/>{:else if value.bytes}<PdfView bytes={value.bytes} large={expanded}/>{/if}
{:else}<div class="empty" role="status"><strong>{labels[value.status] || 'Aperçu indisponible'}</strong>{#if value.message}<span>{value.message}</span>{/if}</div>{/if}
{/snippet}
{#if !large}{@render content(false)}{/if}
{#if value.status==='ready'}<div class="actions"><span>{value.selected?'Sélection courante':'Ressource associée · non sélectionnée'}</span><button class="btn quiet" onclick={enlarge}><Maximize2 size={13}/>{role==='DATASHEET'?'Ouvrir':'Voir'}</button></div><p class="provenance">{value.name} · {value.storage==='managed'?'Asset Store FabParts':'Référence KiCad'} · {value.origin}</p>
{:else if value.status!=='loading'}<button class="retry btn quiet" onclick={()=>void controller.load(detail.id,role,assetId)}><RefreshCw size={12}/>Réessayer</button>{/if}
<dialog bind:this={dialog} onclose={()=>large=false} oncancel={()=>large=false}>
<header><div><strong>{value.name}</strong><span>Consultation · ne constitue pas une validation</span></div><button class="btn quiet" aria-label="Fermer l’aperçu" onclick={close}><X size={18}/></button></header>
{#if large}{@render content(true)}{/if}<p class="provenance">{value.storage==='managed'?'Asset Store FabParts':'Référence KiCad'} · {value.origin}</p>
</dialog>
<style>
.empty{min-height:174px;padding:12px;display:flex;align-items:center;justify-content:center;flex-direction:column;gap:8px;text-align:center;font-size:var(--fs-xs);color:var(--text-secondary);background:var(--bg-workspace)}.empty strong{font-weight:500}.candidate{display:flex;align-items:center;gap:6px;padding:6px 8px;font-size:var(--fs-xs);color:var(--text-secondary)}select{width:0;flex:1;background:var(--bg-input);color:var(--text-primary);border:1px solid var(--border);padding:3px;min-width:0}.actions{display:flex;align-items:center;justify-content:space-between;padding:2px 8px;font-size:var(--fs-xs);gap:6px;color:var(--text-secondary)}.provenance{margin:0;padding:4px 8px;font-size:var(--fs-xs);color:var(--text-secondary);overflow-wrap:anywhere}.retry{margin:4px 8px}dialog{padding:0;width:min(1040px,92vw);max-height:92vh;border:1px solid var(--border);background:var(--bg-panel);color:var(--text-primary);overflow:auto}dialog::backdrop{background:rgb(0 0 0 / .6)}header{display:flex;align-items:center;justify-content:space-between;padding:12px 16px;border-bottom:1px solid var(--divider)}header div{display:flex;flex-direction:column;gap:4px}header span{font-size:var(--fs-xs);color:var(--text-secondary)}
</style>
