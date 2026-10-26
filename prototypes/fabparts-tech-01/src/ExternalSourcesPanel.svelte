<script lang="ts">
import {onDestroy,onMount,untrack} from 'svelte';
import {invoke} from '@tauri-apps/api/core';
import {i18n} from '../../fabparts-ux/src/lib/i18n.svelte';
import Disclosure from '../../fabparts-ux/src/components/Disclosure.svelte';
import ExternalSettings from './ExternalSettings.svelte';
import {external,ExternalController,type Configuration,type RemoteCandidate,type Result,type Staged} from './external';
let {preparation,query='',onstaged}:{preparation:string;query?:string;onstaged:(value:Staged)=>void}=$props();
const tr=(fr:string,en:string)=>i18n.locale==='fr'?fr:en;
let config=$state<Configuration|null>(null), pending=$state(false), error=$state(''), notice=$state('');
let role=$state('SYMBOL'), library=$state('Timer'), term=$state(untrack(()=>query.slice(0,255)));
let candidates=$state<RemoteCandidate[]>([]), selected=$state(''), url=$state(''), consent=$state(false);
const candidate=$derived(candidates.find(c=>c.token===selected));
function result(value:Result){
 if(value.candidates){candidates=value.candidates;selected='';notice=(value.notices||[]).join(' ');if(!candidates.length)notice=tr('Aucun résultat distant. Les ressources locales restent disponibles.','No remote results. Local resources remain available.');}
 if(value.file&&value.candidate){onstaged({file:value.file,candidate:value.candidate});notice=tr('Téléchargé pour examen, sans sélection ni enregistrement. Examinez la carte puis retenez la ressource si elle convient.','Downloaded for inspection, without selection or saving. Inspect the resource card, then select it if appropriate.');}
}
const controller=new ExternalController(invoke,untrack(()=>preparation),result,value=>pending=value,value=>error=value);
onDestroy(()=>controller.cancel());
onMount(()=>{let live=true;void external<Configuration>(invoke,'external_configuration').then(value=>{if(live)config=value;}).catch(e=>{if(live)error=e.message||String(e);});return()=>{live=false;};});
function configure(value:Configuration){config=value;candidates=[];selected='';consent=false;controller.cancel();}
function search(){notice='';candidates=[];selected='';void controller.start('external_search',{role,library,query:term});}
</script>
<section class="external-panel">
 <h3>{tr('Sources externes · sur demande','External sources · on demand')}</h3>
 <p class="secondary">{tr('La recherche locale reste prioritaire. Télécharger, retenir et enregistrer sont trois décisions distinctes.','Local search remains the primary path. Downloading, selecting and saving are separate decisions.')}</p>
 <Disclosure id="external-settings-wizard" label={tr('Activation et paramètres des sources','Source activation and settings')}><ExternalSettings onchange={configure} disabled={pending}/></Disclosure>
 <fieldset disabled={pending||!config?.kicad.enabled}>
  <legend>{tr('Recherche officielle KiCad','Official KiCad search')} · {config?.kicad.revision||'—'}</legend>
  <div class="fields">
   <label>{tr('Type de ressource','Resource type')}<select class="input" bind:value={role}><option value="SYMBOL">{tr('Symbole','Symbol')}</option><option value="FOOTPRINT">{tr('Empreinte','Footprint')}</option><option value="MODEL_3D">{tr('Modèle 3D','3D model')}</option></select></label>
   <label>{tr('Bibliothèque précise','Exact library')}<input class="input" bind:value={library} maxlength="255" placeholder="Device / Resistor_SMD / Package_SO"/></label>
   <label>{tr('Terme recherché','Search term')}<input class="input" bind:value={term} maxlength="255"/></label>
  </div>
  <button class="btn" disabled={!library.trim()||!term.trim()} onclick={search}>{tr('Rechercher en ligne','Search online')}</button>
 </fieldset>
 {#if config&&!config.kicad.enabled}<p class="secondary">{tr('Recherche officielle désactivée. Vous pouvez l’activer ci-dessus.','Official search is disabled. You can enable it above.')}</p>{/if}
 {#if candidates.length}
 <label>{tr('Examiner un résultat distant','Inspect a remote result')}<select class="input" bind:value={selected} disabled={pending}><option value="">{tr('Choisir pour examiner…','Choose to inspect…')}</option>{#each candidates as c}<option value={c.token}>{c.library}:{c.name}</option>{/each}</select></label>
 {/if}
 {#if candidate}<div class="candidate">
  <strong>{candidate.library}:{candidate.name}</strong><span>{candidate.description}</span>
  <span>{tr('Source officielle KiCad · téléchargement requis','Official KiCad source · download required')}</span>
  <span>{tr('Révision','Revision')} {candidate.revision} · {tr('Commit','Commit')} {candidate.commit}</span>
  <span class="source">{candidate.source}</span>
  <button class="btn" disabled={pending} onclick={()=>controller.start('external_download',{token:candidate!.token})}>{tr('Télécharger cette ressource','Download this resource')}</button>
 </div>{/if}
 <fieldset disabled={pending||!config?.pdf.enabled}>
  <legend>{tr('PDF constructeur · URL fournie','Manufacturer PDF · supplied URL')}</legend>
  <label>URL HTTPS<input class="input" value={url} oninput={e=>{url=e.currentTarget.value;consent=false;}} maxlength="2048" placeholder="https://www.ti.com/lit/ds/symlink/ne555.pdf"/></label>
  <label class="check"><input type="checkbox" bind:checked={consent}/>{tr('J’autorise le téléchargement de cette URL pour examen.','I authorize downloading this URL for inspection.')}</label>
  <button class="btn" disabled={!consent||!url.trim()} onclick={()=>{const authorized=consent;consent=false;void controller.start('external_pdf',{url,consent:authorized});}}>{tr('Télécharger ce PDF','Download this PDF')}</button>
 </fieldset>
 {#if config&&!config.pdf.enabled}<p class="secondary">{tr('Téléchargement PDF désactivé. Aucun document ne sera récupéré automatiquement.','PDF downloads are disabled. No document will be fetched automatically.')}</p>{/if}
 {#if pending}<div class="row" role="status"><span>{tr('Requête réseau en cours… vous pouvez continuer localement.','Network request in progress… you can continue locally.')}</span><button class="btn" onclick={()=>controller.cancel()}>{tr('Annuler la requête','Cancel request')}</button></div>{/if}
 {#if notice}<p role="status">{notice}</p>{/if}
 {#if error}<p class="error" role="alert">{tr('Source externe indisponible. Le parcours local reste disponible.','External source unavailable. The local workflow remains available.')} {error}</p>{/if}
</section>
<style>
.external-panel{display:flex;flex-direction:column;gap:var(--s3);border:1px solid var(--border);padding:var(--s3);margin:var(--s3) 0;background:var(--bg-panel);min-width:0}h3{font-size:var(--fs-md);margin:0}p{margin:0;font-size:var(--fs-sm);overflow-wrap:anywhere}.secondary{color:var(--text-secondary)}fieldset{display:flex;flex-direction:column;gap:var(--s3);min-width:0;border:1px solid var(--border);padding:var(--s3)}legend{font-size:var(--fs-sm);padding:0 var(--s2)}.fields{display:grid;grid-template-columns:1fr 1fr 1fr;gap:var(--s3)}label{display:flex;flex-direction:column;gap:var(--s2);font-size:var(--fs-sm);min-width:0}label.check{flex-direction:row;align-items:center}.input{width:100%;min-width:0}button{align-self:start}.candidate{display:flex;flex-direction:column;gap:var(--s2);font-size:var(--fs-sm);padding:var(--s3);border-left:2px solid var(--accent)}.source{overflow-wrap:anywhere;color:var(--text-secondary)}.row{display:flex;gap:var(--s3);flex-wrap:wrap;align-items:center;font-size:var(--fs-sm)}.error{color:var(--danger-text)}@media(max-width:850px){.fields{grid-template-columns:1fr}}
</style>
