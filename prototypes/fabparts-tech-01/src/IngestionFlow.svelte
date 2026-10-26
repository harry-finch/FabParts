<script lang="ts">
import { onMount } from 'svelte';
import { invoke } from '@tauri-apps/api/core';
import { ArrowLeft, ArrowRight, Upload, FileText, Check, Search, TriangleAlert, X, Cpu, Box, CircuitBoard } from '@lucide/svelte';
import { i18n } from '../../fabparts-ux/src/lib/i18n.svelte';
import Disclosure from '../../fabparts-ux/src/components/Disclosure.svelte';
import AssetPreview from './AssetPreview.svelte';
import ExternalSourcesPanel from './ExternalSourcesPanel.svelte';
import { roleLabel } from './text';
import { IngestionController, initialIngestion, browserRecovery, ingestionRoles, type IngestionState } from './ingestion';
let { personal=false, partId='', library='all', oncancel, onsave, onexisting }:{
  personal?:boolean;partId?:string;library?:string;oncancel:()=>void;onsave:(id:string)=>Promise<void>;onexisting:(id:string)=>Promise<void>
}=$props();
let s=$state<IngestionState>(initialIngestion());
let queries=$state<Record<string,string>>({});
let externalOpen=$state(false);
let searchOpen=$state<Record<string,boolean>>({});
const flow=new IngestionController(invoke,value=>s=value,id=>onsave(id),browserRecovery);
const tr=(fr:string,en:string)=>i18n.locale==='fr'?fr:en;
const icons={SYMBOL:Cpu,FOOTPRINT:CircuitBoard,MODEL_3D:Box,DATASHEET:FileText};
const incomplete=$derived(!s.fields.package_id&&!s.fields.package_name || ingestionRoles.some(r=>!s.selections[r]));
const error=$derived(({identity_required:tr('Saisir une référence ou un MPN.','Enter a reference or MPN.'),library_required:tr('Choisir au moins une bibliothèque.','Choose at least one library.'),confirmation_unknown:tr('Confirmation incertaine. Vérifiez le résultat avant de recommencer.','Confirmation is uncertain. Check the result before trying again.'),not_committed:tr('Aucun enregistrement confirmé. Rouvrez l’assistant pour recommencer.','No save was confirmed. Reopen the assistant to start again.')} as Record<string,string>)[s.error] || s.error);
onMount(()=>{void flow.begin(partId,library);return()=>flow.dispose();});
async function cancel(){if(await flow.cancel())oncancel();}
async function existing(id:string){if(await flow.cancel())await onexisting(id);}
function membership(id:string){const collections=s.fields.collections.includes(id)?s.fields.collections.filter(v=>v!==id):[...s.fields.collections,id];flow.edit({collections});}
async function packageChanged(value:string){flow.edit({package_id:value,package_name:''});await flow.inspect(true);}
const matchLabel=(match?:string)=>match==='exact'?tr('Nom exact · compatibilité à vérifier','Exact name · check compatibility'):match==='declared'?tr('Lien déclaré · à vérifier','Declared link · review required'):tr('Correspondance indicative','Indicative match');
const reasonLabel=(reason?:string)=>({name_match:tr('Recherche par nom','Name search'),catalogue_choice:tr('Choix du composant existant','Existing component selection'),catalogue_document:tr('Document du composant existant','Existing component document'),symbol_footprint:tr('Empreinte déclarée par le symbole · pins/pads concordants','Symbol footprint property · matching pin/pad numbers'),footprint_model:tr('Chemin 3D déclaré par l’empreinte','3D path declared by the footprint')} as Record<string,string>)[reason||'']||tr('Recherche locale','Local search');

</script>

<section class="add-flow" aria-busy={s.busy}>
  <header class="page-heading">
    <button class="btn quiet" disabled={s.busy||s.recovery} onclick={()=>s.step>0?flow.back(s.step-1):cancel()}><ArrowLeft size={14}/>{tr('Retour','Back')}</button>
    <h1>{partId?tr('Compléter le brouillon','Complete draft'):tr('Ajouter un composant','Add component')}</h1>
    <span class="secondary">{personal?tr('Espace personnel','Personal workspace'):tr('Environnement de test','Test environment')}</span>
  </header>
  <nav class="steps" aria-label={tr('Étapes de l’ajout','Ingestion steps')}>
    {#each [tr('Informations et fichiers','Information and files'),tr('Identification et package','Identity and package'),tr('Ressources et confirmation','Resources and confirmation')] as label,i}
      <button class:active={s.step===i} disabled={i>s.step||s.busy||s.recovery} onclick={()=>flow.back(i)} aria-current={s.step===i?'step':undefined}><span>{s.step>i?'✓':i+1}</span>{label}{#if i<2}<ArrowRight size={12}/>{/if}</button>
    {/each}
  </nav>
  <div class="flow-body">
    {#if s.session}
    <fieldset disabled={s.busy||s.recovery}>
    {#if s.step===0}
      <div class="intro"><h2>{tr('Commencez avec ce que vous avez','Start with what you have')}</h2><p>{tr('Une référence suffit. Ajoutez vos fichiers si vous les avez déjà.','A reference is enough. Add your files if you already have them.')}</p></div>
      <div class="input-columns">
        <div class="form-section">
          <h3>{tr('Informations','Information')}</h3>
          <label>{tr('Référence du composant','Component reference')}<input class="input" value={s.fields.reference} oninput={e=>flow.edit({reference:e.currentTarget.value})} placeholder="SENSOR-LAB-01" maxlength="2048"/></label>
          <label>{tr('MPN · facultatif','MPN · optional')}<input class="input" value={s.fields.mpn} oninput={e=>flow.edit({mpn:e.currentTarget.value})} maxlength="2048"/></label>
          <label>{tr('Fabricant · facultatif','Manufacturer · optional')}<input class="input" value={s.fields.manufacturer} oninput={e=>flow.edit({manufacturer:e.currentTarget.value})} maxlength="2048"/></label>
          {@render memberships()}
        </div>
        <div class="form-section">
          <h3>{tr('Vos fichiers','Your files')}</h3>
          <div class="drop"><Upload size={24}/><strong>{tr('Ajouter des fichiers locaux','Add local files')}</strong><span>.kicad_sym · .kicad_mod · .step / .stp / .wrl · .pdf</span><button class="btn" onclick={()=>flow.pick()}><Upload size={14}/>{tr('Parcourir les fichiers…','Browse files…')}</button></div>
          {#each s.files as file}<div class="file-row"><FileText size={14}/><span title={file.file.original_name}>{file.file.original_name}</span><span class="secondary small">{Math.ceil(file.file.size_bytes/1024)} Kio · {tr('Préparé','Prepared')}</span><button class="btn quiet" aria-label={tr('Retirer ','Remove ')+file.file.original_name} onclick={()=>flow.remove(file.handle)}><X size={14}/></button></div>{/each}
          <p class="small secondary">{tr('8 fichiers maximum, 16 Mio par fichier, 64 Mio au total. Seules les ressources choisies à la dernière étape seront importées.','Up to 8 files, 16 MiB per file, 64 MiB total. Only resources selected in the last step will be imported.')}</p>
          <p class="small secondary">{tr('Les originaux sont conservés. Aucun fichier n’est enregistré avant votre confirmation.','Original files are preserved. Nothing is saved until you confirm.')}</p>
        </div>
      </div>
    {:else if s.step===1}
      <div class="intro"><h2>{tr('Identifier sans deviner','Identify without guessing')}</h2><p>{tr('Complétez les informations connues. Le package peut être choisi plus tard.','Fill in the information you know. You can choose a package later.')}</p></div>
      <button class="btn primary" disabled={s.discovering} onclick={()=>flow.discover()}><Search size={14}/>{tr('Rechercher des ressources','Find resources')}</button>
      <div class="input-columns">
        <div class="form-section">
          <h3>{tr('Composant','Component')}</h3>
          <label>{tr('Référence','Reference')}<input class="input" value={s.fields.reference} oninput={e=>flow.edit({reference:e.currentTarget.value})}/></label>
          <label>MPN<input class="input" value={s.fields.mpn} oninput={e=>flow.edit({mpn:e.currentTarget.value})}/></label>
          <label>{tr('Fabricant','Manufacturer')}<input class="input" value={s.fields.manufacturer} oninput={e=>flow.edit({manufacturer:e.currentTarget.value})}/></label>
          <label>Description<input class="input" value={s.fields.description} oninput={e=>flow.edit({description:e.currentTarget.value})}/></label>
          <label>{tr('Catégorie','Category')}<input class="input" list="ingestion-categories" value={s.fields.category} oninput={e=>flow.edit({category:e.currentTarget.value})}/></label>
          <datalist id="ingestion-categories">{#each s.session.categories as category}<option value={category}></option>{/each}</datalist>
          <span class="small secondary">{tr('Informations saisies manuellement · provenance conservée','Manually entered information · provenance retained')}</span>
        </div>
        <div class="form-section">
          <h3>Package</h3>
          <label>{tr('Package existant','Existing package')}<select class="input" value={s.fields.package_id} onchange={e=>packageChanged(e.currentTarget.value)}><option value="">{tr('Inconnu / à compléter','Unknown / complete later')}</option>{#each s.session.packages as pkg}<option value={pkg.id}>{pkg.name}</option>{/each}</select></label>
          {#if !s.fields.package_id}<label>{tr('Ou nommer un nouveau package','Or name a new package')}<input class="input" value={s.fields.package_name} oninput={e=>flow.edit({package_name:e.currentTarget.value})} placeholder={tr('Nom explicite du package ou de sa variante','Explicit package or variant name')}/></label>{/if}
          <p class="small secondary">{tr('Un package existant conserve ses ressources partagées. Pour en changer, créez un package distinct.','An existing package keeps its shared resources. Create a separate package to change them.')}</p>
          <button class="btn quiet" onclick={()=>packageChanged('')}>{tr('Je compléterai le package plus tard','I will complete the package later')}</button>
          <p class="small secondary">{tr('Le nom d’un fichier ne détermine jamais le package.','A filename never determines the package.')}</p>
        </div>
      </div>
    {:else}
      <div class="intro review-intro"><div><h2>{s.fields.reference||s.fields.mpn} <span class="secondary">· {s.fields.manufacturer} · {s.fields.package_name||s.session.packages.find(p=>p.id===s.fields.package_id)?.name||tr('Package à compléter','Package missing')}</span></h2><p>{tr('Choisissez explicitement les ressources à conserver et examinez leurs aperçus.','Explicitly choose which resources to keep and inspect their previews.')}</p></div><button class="btn" onclick={()=>flow.back(1)}>{tr('Modifier','Edit')}</button></div>
      <div class="row"><button class="btn" disabled={s.discovering} onclick={()=>flow.discover()}><Search size={14}/>{tr('Rechercher des ressources','Find resources')}</button><span class="small secondary" role="status">{s.discovering?tr('Recherche locale en cours… les résultats apparaissent par ressource.','Searching locally… results appear by resource.'):s.discovered?tr('Propositions locales · aucun choix automatique','Local suggestions · no automatic selection'):''}</span></div>
      <button class="btn quiet" aria-expanded={externalOpen} onclick={()=>externalOpen=!externalOpen}>{tr('Compléter avec la recherche officielle KiCad…','Extend with official KiCad search…')}</button>
      {#if externalOpen}<ExternalSourcesPanel preparation={s.session.preparation} query={s.fields.mpn||s.fields.reference} onstaged={value=>flow.addExternal(value)}/>{/if}
      {#if s.metadata.length||s.proposedPackages.length}<Disclosure id="guided-metadata" label={tr('Informations locales proposées','Suggested local information')}>
        <p class="small secondary">{tr('Chaque valeur retenue garde sa provenance. Les champs saisis restent prioritaires.','Each accepted value retains its source. Entered fields take precedence.')}</p>
        {#each s.metadata as item}<div class="row"><span class="small">{item.field==='manufacturer'?tr('Fabricant','Manufacturer'):item.field==='category'?tr('Catégorie','Category'):'MPN'} : <strong>{item.value}</strong> · {item.source}</span><button class="btn quiet" disabled={s.discovering||s.acceptedMetadata[item.field]===item.token} onclick={()=>flow.acceptMetadata(item)}>{s.acceptedMetadata[item.field]===item.token?tr('Retenue','Accepted'):s.fields[item.field]&&s.fields[item.field]!==item.value?tr('Remplacer ce champ','Replace this field'):tr('Retenir ce champ','Accept this field')}</button></div>{/each}
        {#each s.proposedPackages as pkg}<div class="row"><span class="small">{pkg.name} · {pkg.source}</span><button class="btn quiet" disabled={s.discovering||s.fields.package_id===pkg.id} onclick={()=>packageChanged(pkg.id)}>{tr('Utiliser ce package et ses ressources partagées','Use this package and its shared resources')}</button></div>{/each}
      </Disclosure>{/if}
      {#if s.similar.length}<p class="small secondary">{tr('Composants similaires du catalogue : ','Similar catalogue components: ')}{s.similar.map(p=>p.name).join(' · ')}</p>{/if}
      <div class="resources-grid">
        {#each ingestionRoles as role}
          {@const Icon=icons[role]}
          {@const selected=s.candidates.find(c=>c.token===s.selections[role])}
          {@const previewToken=s.previewing[role]??selected?.token??s.candidates.find(c=>c.role===role)?.token??''}
          {@const proposed=s.candidates.find(c=>c.token===previewToken)}
          {@const shared=!!s.fields.package_id && ['FOOTPRINT','MODEL_3D'].includes(role)}
          <section class="resource">
            <header><span><Icon size={14}/>{roleLabel(role)}</span><span class="secondary small">{tr('Non validée','Not validated')}</span></header>
            <div class="resource-choice">
              <div class="resource-select"><label><span class="sr-only">{tr('Ressource','Resource')}</span><select class="input" value={previewToken} onchange={e=>flow.preview(role,e.currentTarget.value)} aria-label={tr('Examiner : ','Inspect: ')+roleLabel(role)}>
                <option value="" >{tr('Aucun aperçu','No preview')}</option>
                {#each s.candidates.filter(c=>c.role===role) as candidate}<option value={candidate.token} disabled={!!candidate.warning}>{candidate.name} · {candidate.storage==='staged'?(candidate.origin==='USER_PROVIDED'?tr('Fourni','Provided'):tr('Téléchargé','Downloaded')):candidate.storage==='managed'?tr('Géré','Managed'):'KiCad'}</option>{/each}
              </select></label>{#if !shared}<button class="btn quiet" aria-label={tr('Recherche locale : ','Local search: ')+roleLabel(role)} aria-expanded={!!searchOpen[role]} onclick={()=>searchOpen[role]=!searchOpen[role]}><Search size={14}/></button>{/if}</div>
              {#if proposed}<span class="small secondary">{matchLabel(proposed.match)} · {proposed.storage==='staged'?(proposed.origin==='USER_PROVIDED'?tr('Fichier fourni','Provided file'):tr('Téléchargé pour examen','Downloaded for inspection')):reasonLabel(proposed.reason)}{#if proposed.source} · {proposed.source}{/if}{#if proposed.package} · {proposed.package}{/if}</span>
              <span class="small">{selected?.token===proposed.token?tr('Retenue pour l’enregistrement','Selected for saving'):tr('Proposition non retenue','Suggestion not selected')}</span>
              {#if !shared && selected?.token!==proposed.token}<button class="btn" disabled={!!proposed.warning||s.discovering} onclick={()=>flow.choose(role,proposed.token)}>{tr('Retenir cette ressource','Select this resource')}</button>{/if}{/if}
              {#if selected && selected.token!==proposed?.token}<span class="small">{tr('Choix conservé : ','Selection kept: ')}{selected.name}</span>{/if}
              {#if selected && !shared && !s.session.selections[role]}<button class="btn quiet" onclick={()=>flow.choose(role,'')}>{tr('Retirer du choix','Clear selection')}</button>{/if}
              {#if shared}<span class="small secondary">{tr('Choix du package partagé','Shared package selection')}</span>
              {:else if searchOpen[role]}<div class="resource-search"><input class="input" aria-label={tr('Recherche locale : ','Local search: ')+roleLabel(role)} placeholder={tr('Rechercher localement…','Search locally…')} bind:value={queries[role]} onkeydown={e=>{if(e.key==='Enter'){e.preventDefault();void flow.search(role,queries[role]||'');}}}/><button class="btn quiet" disabled={s.searching.includes(role)} aria-label={tr('Rechercher : ','Search: ')+roleLabel(role)} onclick={()=>flow.search(role,queries[role]||'')}><Search size={14}/></button></div>{/if}
            </div>
            {#if proposed}{#key proposed.token}<AssetPreview {role} prepared={{preparation:s.session.preparation,token:proposed.token}}/>{/key}
            {:else}<div class="empty-preview"><Icon size={26}/><span>{s.discovering?tr('Recherche en cours…','Searching…'):tr('Aucune proposition · import manuel disponible à la première étape','No suggestion · manual import is available in the first step')}</span></div>{/if}
          </section>
        {/each}
      </div>
      <p class="small secondary">{tr('L’import et l’aperçu ne constituent pas une validation électrique ou mécanique. Le composant reste un brouillon.','Importing and previewing are not electrical or mechanical validation. The component remains a draft.')}</p>
      {@render memberships()}
      {#if s.notices.includes('INDEX_UNAVAILABLE')}<p class="small secondary" role="status">{tr('Index KiCad absent ou vide. Vous pouvez toujours importer vos fichiers à la première étape.','KiCad index missing or empty. You can still import your files in the first step.')}</p>{/if}
      {#if s.notices.length}<Disclosure id="ingestion-search-notices" label={tr('État de la recherche locale','Local search status')}>{#each s.notices as notice}<p class="small secondary">{notice==='INDEX_UNAVAILABLE'?tr('Index KiCad absent ou vide. Les fichiers fournis et les assets gérés restent disponibles ; configurez les racines et reconstruisez l’index local.','KiCad index missing or empty. Provided files and managed assets remain available; configure roots and rebuild the local index.'):notice}</p>{/each}</Disclosure>{/if}
    {/if}
    {#if s.step>0 && s.duplicates.length}
      <div class="duplicate"><h3>{tr('Composant déjà présent','Existing component')}</h3>
        {#each s.duplicates as duplicate}<div class="duplicate-row"><strong>{duplicate.name}</strong><span class="secondary small">{duplicate.manufacturer} · {duplicate.mpn}</span><div class="row"><button class="btn" onclick={()=>existing(duplicate.id)}>{tr('Voir l’existant','View existing')}</button><button class="btn" disabled={!s.fields.collections.length} onclick={()=>flow.commit('membership',duplicate.id)}>{tr('Ajouter aux bibliothèques choisies','Add to selected libraries')}</button></div></div>{/each}
        <p class="small secondary">{tr('L’ajout à une bibliothèque conserve les informations et les ressources de l’existant.','Adding a library membership keeps the existing information and resources.')}</p>
        <label class="variant"><input type="checkbox" checked={s.variant} onchange={e=>flow.variant(e.currentTarget.checked)}/>{tr('Je confirme la création d’une variante avec une référence distincte','I confirm creating a variant with a distinct reference')}</label>
      </div>
    {/if}
    </fieldset>
    {/if}
    {#if error}<div class="notice error" role="alert"><TriangleAlert size={16}/><span>{error}</span>{#if s.recovery}<button class="btn" disabled={s.busy} onclick={()=>flow.recover()}>{tr('Vérifier l’enregistrement','Check save result')}</button>{/if}</div>{/if}
    {#if s.busy}<div class="notice" role="status"><span>{tr('Traitement en cours…','Working…')}</span></div>{/if}
  </div>
  <footer class="flow-footer">
    <button class="btn" disabled={s.busy||s.recovery} onclick={cancel}>{tr('Annuler l’ajout','Cancel addition')}</button>
    <span class="secondary small">{personal?tr('Enregistrement local','Local save'):tr('Sauvegarde locale · sandbox','Local save · sandbox')}</span><div class="grow"></div>
    {#if s.step<2}<button class="btn" class:primary={s.step===0} disabled={s.busy||s.discovering||!s.session||s.recovery} onclick={()=>flow.next()}>{tr('Continuer','Continue')}<ArrowRight size={14}/></button>
    {:else}
      {#if incomplete}<button class="btn" disabled={s.busy||s.discovering||s.recovery||!!s.duplicates.length&&!s.variant} onclick={()=>flow.commit(s.variant?'variant':'save')}>{tr('Enregistrer comme brouillon','Save as draft')}</button>{/if}
      <button class="btn primary" disabled={s.busy||s.discovering||s.recovery||!!s.duplicates.length&&!s.variant} onclick={()=>flow.commit(s.variant?'variant':'save')}><Check size={14}/>{tr('Enregistrer dans FabParts','Save in FabParts')}</button>
    {/if}
  </footer>
</section>
{#snippet memberships()}
<div class="memberships"><span>{tr('Bibliothèques cibles','Target libraries')}</span><div>{#each s.session?.collections||[] as collection}<label><input type="checkbox" checked={s.fields.collections.includes(collection.id)} onchange={()=>membership(collection.id)}/>{collection.name}</label>{/each}</div></div>
{/snippet}
<style>
/* UX 02 AddFlow dimensions and Fab tokens, with the real TECH-02 preview grid. */
.add-flow{min-width:0;display:grid;grid-template-rows:auto auto 1fr auto;min-height:0;height:100%}
.page-heading{display:flex;align-items:center;gap:12px;min-height:48px;padding:0 12px;border-bottom:1px solid var(--border);background:var(--bg-panel)}
h1,h2{font-size:var(--fs-lg);font-weight:600;margin:0}.page-heading>span{margin-left:auto}
.steps{display:flex;padding:0 24px;border-bottom:1px solid var(--border);background:var(--bg-panel);gap:24px}
.steps button{display:flex;align-items:center;gap:8px;border:0;border-bottom:2px solid transparent;background:none;color:var(--text-secondary);min-height:42px;font-size:var(--fs-sm)}
.steps button.active{color:var(--text-primary);border-color:var(--accent)}.steps button:disabled{opacity:.5}
.steps button span{display:grid;place-items:center;min-width:18px;height:18px;border:1px solid var(--border-strong);border-radius:50%;font-size:var(--fs-xs)}
.flow-body{min-width:0;overflow:auto;padding:16px 24px;max-width:1180px;width:100%;margin:0 auto}fieldset{border:0;padding:0;margin:0;min-width:0}
.intro{margin-bottom:24px}.intro p{margin:8px 0 0;color:var(--text-secondary);font-size:var(--fs-sm)}
.input-columns{display:grid;grid-template-columns:1fr 1fr;gap:32px}.form-section{display:flex;flex-direction:column;gap:12px;min-width:0}
h3{font-size:var(--fs-xs);letter-spacing:.06em;text-transform:uppercase;color:var(--text-section);margin:0 0 4px}
.form-section label,.resource-choice label{display:flex;flex-direction:column;gap:6px;font-size:var(--fs-sm);color:var(--text-secondary)}
.input{width:100%;min-width:0}.memberships{display:flex;align-items:center;flex-wrap:wrap;gap:8px;font-size:var(--fs-sm);margin:8px 0}.memberships>span{color:var(--text-secondary)}
.memberships>div{display:flex;gap:20px;flex-wrap:wrap}.memberships label,.variant{display:flex;align-items:center;gap:6px;font-size:var(--fs-sm)}
.drop{display:flex;flex-direction:column;align-items:center;gap:12px;justify-content:center;min-height:180px;border:1px dashed var(--border-strong);color:var(--text-secondary);background:var(--bg-panel);padding:12px;text-align:center}
.drop span{font-size:var(--fs-xs)}.file-row{display:flex;align-items:center;gap:8px;min-width:0}.file-row>span:first-of-type{flex:1;overflow:hidden;text-overflow:ellipsis;font-size:var(--fs-sm)}
.secondary{color:var(--text-secondary)}.small{font-size:var(--fs-sm)}.review-intro{display:flex;justify-content:space-between;align-items:start;gap:16px;margin-bottom:12px}.review-intro h2 span{font-weight:400}
.flow-footer{flex-wrap:wrap;display:flex;gap:12px;align-items:center;padding:12px 16px;border-top:1px solid var(--border);background:var(--bg-panel)}.grow{flex:1}
.notice{display:flex;align-items:center;gap:12px;border-left:2px solid var(--info);padding:12px;margin-top:16px;color:var(--info);font-size:var(--fs-sm)}.error{color:var(--danger-text);border-color:var(--danger)}
.duplicate{border-top:1px solid var(--border);padding-top:16px;margin-top:16px}.duplicate-row{display:flex;flex-direction:column;gap:8px;margin:12px 0}.row{display:flex;gap:8px;flex-wrap:wrap}
.resources-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:var(--s3)}.resource{min-width:0;border:1px solid var(--border);background:var(--bg-panel)}
.resource header{min-height:34px;display:flex;align-items:center;justify-content:space-between;padding:0 var(--s3);border-bottom:1px solid var(--divider);gap:8px;flex-wrap:wrap}
.resource header span{display:flex;align-items:center;gap:8px;font-size:var(--fs-sm)}.resource-choice>span{overflow-wrap:anywhere}.resource-choice{padding:8px;display:flex;flex-direction:column;gap:6px}.resource-search{display:flex;gap:4px}.resource-select{display:flex;align-items:center;gap:4px}.resource-select label{flex:1;min-width:0}.resource-select select{height:28px;padding:2px 6px}
.empty-preview{min-height:174px;display:flex;align-items:center;justify-content:center;flex-direction:column;gap:12px;color:var(--text-secondary);font-size:var(--fs-sm);background:var(--bg-workspace)}
@media(max-width:1000px){.flow-body{padding:16px}.steps{gap:12px;padding:0 12px}.input-columns{gap:20px}.flow-footer>span,.page-heading>span{display:none}}
@media(max-width:750px){.input-columns,.resources-grid{grid-template-columns:1fr}.steps{gap:4px}.steps button{font-size:var(--fs-xs)}.steps :global(svg){display:none}.page-heading{flex-wrap:wrap}.page-heading h1{font-size:var(--fs-sm)}}
</style>
