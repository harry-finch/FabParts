<script lang="ts">
import {onMount} from 'svelte';
import {invoke} from '@tauri-apps/api/core';
import {i18n} from '../../fabparts-ux/src/lib/i18n.svelte';
import {external,type Configuration} from './external';
let {onchange=()=>{},disabled=false}:{onchange?:(value:Configuration)=>void;disabled?:boolean}=$props();
const tr=(fr:string,en:string)=>i18n.locale==='fr'?fr:en;
let config=$state<Configuration|null>(null), saving=$state(false), error=$state(''), message=$state('');
let kicad=$state(false), pdf=$state(false), revision=$state('9.0.0'), domains=$state('');
function apply(value:Configuration){config=value;kicad=value.kicad.enabled;pdf=value.pdf.enabled;revision=value.kicad.revision;domains=value.pdf.domains.join(', ');onchange(value);}
onMount(()=>{let live=true;void external<Configuration>(invoke,'external_configuration').then(value=>{if(live)apply(value);}).catch(e=>{if(live)error=e.message||String(e);});return()=>{live=false;};});
async function save(source:string){
 saving=true;error='';message='';
 try{apply(await external<Configuration>(invoke,'external_configure',{source,enabled:source==='kicad'?kicad:pdf,revision,domains:domains.split(',').map(v=>v.trim()).filter(Boolean)}));message=tr('Configuration enregistrée localement.','Configuration saved locally.');}
 catch(e){error=(e as {message?:string}).message||String(e);}finally{saving=false;}
}
</script>
<div class="external-settings">
 <h2>{tr('Sources externes · facultatives','External sources · optional')}</h2>
 <p class="secondary">{tr('Désactivées par défaut. Aucune connexion automatique. Chaque recherche ou téléchargement reste une action distincte.','Disabled by default. No automatic connections. Each search or download remains a separate action.')}</p>
 {#if config}
 <fieldset disabled={saving||disabled}>
 <legend>KiCad · GitLab</legend>
 <label class="check"><input type="checkbox" bind:checked={kicad}/>{tr('Autoriser la recherche officielle KiCad','Enable official KiCad search')}</label>
 <label>{tr('Révision (tag, branche simple ou commit)','Revision (tag, simple branch or commit)')}<input class="input" bind:value={revision} maxlength="80"/></label>
 <button class="btn" onclick={()=>save('kicad')}>{tr('Enregistrer KiCad','Save KiCad settings')}</button>
 </fieldset>
 <fieldset disabled={saving||disabled}>
 <legend>{tr('PDF constructeur','Manufacturer PDF')}</legend>
 <label class="check"><input type="checkbox" bind:checked={pdf}/>{tr('Autoriser les téléchargements constructeur','Enable manufacturer downloads')}</label>
 <label>{tr('Domaines HTTPS exacts, séparés par des virgules','Exact HTTPS domains, separated by commas')}<input class="input" bind:value={domains} maxlength="8192" placeholder="www.ti.com, www.st.com"/></label>
 <p class="secondary">{tr('Aucun joker, redirection ou réseau privé. Le consentement sera redemandé pour chaque URL.','No wildcards, redirects or private networks. Consent is required for each URL.')}</p>
 <button class="btn" onclick={()=>save('pdf')}>{tr('Enregistrer PDF','Save PDF settings')}</button>
 </fieldset>
 {:else if !error}<p role="status">{tr('Lecture des paramètres locaux…','Reading local settings…')}</p>{/if}
 {#if message}<p role="status">{message}</p>{/if}
 {#if error}<p class="error" role="alert">{error}</p>{/if}
</div>
<style>
.external-settings{display:flex;flex-direction:column;gap:var(--s3);min-width:0}h2{font-size:var(--fs-md);margin:0}p{font-size:var(--fs-sm);margin:0;overflow-wrap:anywhere}.secondary{color:var(--text-secondary)}fieldset{display:flex;flex-direction:column;gap:var(--s3);min-width:0;border:1px solid var(--border);padding:var(--s3)}legend{font-size:var(--fs-sm);padding:0 var(--s2)}label{display:flex;flex-direction:column;gap:var(--s2);font-size:var(--fs-sm)}label.check{flex-direction:row;align-items:center}.input{width:100%;min-width:0}button{align-self:start}.error{color:var(--danger-text)}
</style>
