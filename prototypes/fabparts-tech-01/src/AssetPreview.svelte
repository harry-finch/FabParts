<script lang="ts">
import { invoke } from '@tauri-apps/api/core';
import { Maximize2, X, RefreshCw } from '@lucide/svelte';
import { tr } from './text';
import type { Detail } from './controller';
import { PreviewController, type Preview } from './preview';
import DrawingView from './DrawingView.svelte';
import PdfView from './PdfView.svelte';
import ModelView from './ModelView.svelte';
let { detail, role, prepared }: {detail?:Detail;role:string;prepared?:{preparation:string;token:string}}=$props();
let value=$state<Preview>({status:'loading'}), assetId=$state(''), dialog:HTMLDialogElement, large=$state(false);
let candidates=$derived([...(detail?.associated_assets ?? []).filter(a=>a.type===role).map(a=>({id:a.id,name:a.name})), ...(role==='DATASHEET'?(detail?.documents ?? []).filter(d=>!detail?.associated_assets.some(a=>a.id===d.asset_id)).map(d=>({id:d.asset_id,name:d.title})):[])]);
const controller=new PreviewController(async (command,args)=>{
  if(command==='get_asset_preview' && prepared)return invoke('ingestion_command',{request:{method:'ingestion_preview',params:prepared}});
  return invoke(command,args);
},p=>value=p);
$effect(()=>{const id=prepared?.token || detail?.id;if(id)void controller.load(id,role,assetId);else value={status:'absent'};return ()=>controller.dispose();});
function enlarge(){large=true;dialog.showModal();}function close(){large=false;dialog.close();}
const labels = $derived({loading:tr('Chargement…','Loading…'),absent:tr('Aucune ressource sélectionnée','No resource selected'),missing:tr('Ressource introuvable','Resource not found'),inaccessible:tr('Ressource inaccessible','Resource inaccessible'),unsupported:tr('Format non pris en charge','Unsupported format'),too_large:tr('Aperçu hors limites','Preview exceeds limits'),error:tr('Erreur de lecture','Read error'),converter_missing:tr('Convertisseur STEP indisponible','STEP converter unavailable'),cancelled:tr('Conversion annulée','Conversion cancelled')} as Record<string,string>);
</script>
{#if candidates.length}<label class="candidate">{tr('Aperçu','Preview')} <select bind:value={assetId}><option value="">{tr('Sélection courante','Current selection')}</option>{#each candidates as c}<option value={c.id}>{c.name} · {tr('associé','associated')}</option>{/each}</select></label>{/if}
{#snippet content(expanded:boolean)}
{#if value.status==='ready'}{#if value.mesh}<ModelView mesh={value.mesh} large={expanded}/>{:else if value.drawings?.length}<DrawingView drawings={value.drawings} large={expanded}/>{:else if value.bytes}<PdfView bytes={value.bytes} large={expanded} compact={!!prepared}/>{/if}
{:else}<div class="empty" role="status"><strong>{value.status==='loading'&&role==='MODEL_3D'?tr('Chargement du modèle…','Loading model…'):labels[value.status] || tr('Aperçu indisponible','Preview unavailable')}</strong>{#if value.message}<span>{value.message}</span>{/if}</div>{/if}
{/snippet}
{#if !large}{@render content(false)}{/if}
{#if value.status==='ready'}<div class="actions"><span>{value.selected?tr('Sélection courante','Current selection'):prepared?tr('Préparation · non enregistrée','Preparation · not saved'):tr('Ressource associée · non sélectionnée','Associated resource · not selected')}</span><button class="btn quiet" onclick={enlarge}><Maximize2 size={13}/>{role==='DATASHEET'?tr('Ouvrir','Open'):tr('Voir','View')}</button></div><p class="provenance">{value.name} · {value.storage==='managed'?'Asset Store FabParts':value.storage==='staged'?tr('Fichier préparé','Prepared file'):tr('Référence KiCad','KiCad reference')} · {value.origin}</p>
{:else if value.status!=='loading'}<button class="retry btn quiet" onclick={()=>void controller.load(prepared?.token || detail?.id || '',role,assetId)}><RefreshCw size={12}/>{tr('Réessayer','Retry')}</button>{/if}
<dialog bind:this={dialog} onclose={()=>large=false} oncancel={()=>large=false}>
<header><div><strong>{value.name}</strong><span>{tr('Consultation · ne constitue pas une validation','Preview · does not constitute validation')}</span></div><button class="btn quiet" aria-label={tr('Fermer l’aperçu','Close preview')} onclick={close}><X size={18}/></button></header>
{#if large}{@render content(true)}{/if}<p class="provenance">{value.storage==='managed'?'Asset Store FabParts':value.storage==='staged'?tr('Fichier préparé','Prepared file'):tr('Référence KiCad','KiCad reference')} · {value.origin}</p>
</dialog>
<style>
.empty{min-height:174px;padding:12px;display:flex;align-items:center;justify-content:center;flex-direction:column;gap:8px;text-align:center;font-size:var(--fs-xs);color:var(--text-secondary);background:var(--bg-workspace)}.empty strong{font-weight:500}.candidate{display:flex;align-items:center;gap:6px;padding:6px 8px;font-size:var(--fs-xs);color:var(--text-secondary)}select{width:0;flex:1;background:var(--bg-input);color:var(--text-primary);border:1px solid var(--border);padding:3px;min-width:0}.actions{display:flex;align-items:center;justify-content:space-between;padding:2px 8px;font-size:var(--fs-xs);gap:6px;color:var(--text-secondary)}.provenance{margin:0;padding:4px 8px;font-size:var(--fs-xs);color:var(--text-secondary);overflow-wrap:anywhere}.retry{margin:4px 8px}dialog{padding:0;width:min(1040px,92vw);max-height:92vh;border:1px solid var(--border);background:var(--bg-panel);color:var(--text-primary);overflow:auto}dialog::backdrop{background:rgb(0 0 0 / .6)}header{display:flex;align-items:center;justify-content:space-between;padding:12px 16px;border-bottom:1px solid var(--divider)}header div{display:flex;flex-direction:column;gap:4px}header span{font-size:var(--fs-xs);color:var(--text-secondary)}
</style>
