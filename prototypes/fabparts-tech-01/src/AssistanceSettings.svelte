<script lang="ts">
import {onMount} from 'svelte';
import {invoke} from '@tauri-apps/api/core';
import {i18n} from '../../fabparts-ux/src/lib/i18n.svelte';
import {ai,type AIConfig} from './assistance';
let {disabled=false}:{disabled?:boolean}=$props();
const tr=(fr:string,en:string)=>i18n.locale==='fr'?fr:en;
let backend=$state<AIConfig['backend']>('chat'),endpoint=$state(''),model=$state(''),enabled=$state(false),loaded=$state(false),saving=$state(false),error=$state(''),availability=$state(''),message=$state('');
function apply(c:AIConfig){backend=c.backend;endpoint=c.endpoint;model=c.model;enabled=c.enabled;availability=c.availability;loaded=true;}
onMount(()=>{let live=true;void ai<AIConfig>(invoke,'assistance_configuration').then(c=>{if(live)apply(c);}).catch(e=>{if(live){error=e.message||String(e);loaded=true;}});return()=>{live=false;};});
function preset(value:AIConfig['backend']){backend=value;endpoint=value==='gemini'?'https://generativelanguage.googleapis.com/v1beta':value==='ollama'?'http://127.0.0.1:11434/api/chat':'';model='';enabled=false;availability='';message='';}
async function save(){saving=true;error='';message='';try{apply(await ai<AIConfig>(invoke,'assistance_configure',{enabled,backend,endpoint,model}));message=tr('Paramètres IA enregistrés localement.','AI settings saved locally.');}catch(e){error=(e as {message?:string}).message||String(e);}finally{saving=false;}}
</script>
<section class="ai-settings">
 <h2>{tr('Assistance IA — Facultative','AI assistance — Optional')}</h2>
 <p class="secondary">{tr('Désactivée par défaut. Aucun appel, découverte ou téléchargement de modèle automatique.','Disabled by default. No automatic requests, discovery or model downloads.')}</p>
 <fieldset disabled={disabled||saving||!loaded}>
 <label>{tr('Fournisseur','Provider')}<select class="input" value={backend} onchange={e=>preset(e.currentTarget.value as AIConfig['backend'])}><option value="ollama">Ollama local</option><option value="gemini">Gemini</option><option value="chat">{tr('API compatible OpenAI','OpenAI compatible API')}</option></select></label>
 <label>Endpoint<input class="input" bind:value={endpoint} oninput={()=>availability=''} maxlength="512"/></label>
 <label>{tr('Modèle déjà disponible','Existing model')}<input class="input" bind:value={model} oninput={()=>availability=''} maxlength="128"/></label>
 <label class="check"><input type="checkbox" bind:checked={enabled} onchange={()=>availability=''}/>{tr('Activer l’assistance IA','Enable AI assistance')}</label>
 <p class="secondary">{backend==='ollama'?tr('Modèle local déjà installé requis. Aucun téléchargement lancé par FabParts.','An installed local model is required. FabParts never downloads it.'):tr('Clé définie dans l’environnement de lancement : ','Key supplied through the launch environment: ')+(backend==='gemini'?'GEMINI_API_KEY':'KIPART_AI_API_KEY')+'. '+tr('Aucun champ ni stockage de clé dans FabParts.','No key input or key storage in FabParts.')}</p>
 <button class="btn" onclick={save}>{tr('Enregistrer les paramètres IA','Save AI settings')}</button>
 </fieldset>
 {#if availability}<p role="status">{availability==='disabled'?tr('Assistance désactivée.','Assistance disabled.'):availability==='missing_key'?tr('Clé absente du moteur. Relancer depuis l’environnement configuré.','Key missing in the engine. Relaunch from the configured environment.'):backend==='ollama'?tr('Configuration locale enregistrée ; service et modèle non vérifiés.','Local configuration saved; service and model not checked.'):tr('Clé détectée par le moteur. Sa validité, le quota et l’accès au modèle ne sont pas vérifiés avant une requête autorisée.','Key detected by the engine. Validity, quota and model access are not checked before an authorised request.')}</p>{/if}
 {#if message}<p role="status">{message}</p>{/if}{#if error}<p class="error" role="alert">{error}</p>{/if}
</section>
<style>
.ai-settings{display:flex;flex-direction:column;gap:var(--s3);min-width:0}h2{font-size:var(--fs-md);margin:0}p{font-size:var(--fs-sm);margin:0;overflow-wrap:anywhere}.secondary{color:var(--text-secondary)}fieldset{display:flex;flex-direction:column;gap:var(--s3);min-width:0;border:1px solid var(--border);padding:var(--s3)}label{display:flex;flex-direction:column;gap:var(--s2);font-size:var(--fs-sm)}label.check{flex-direction:row;align-items:center}.input{width:100%;min-width:0}button{align-self:start}.error{color:var(--danger-text)}
</style>
