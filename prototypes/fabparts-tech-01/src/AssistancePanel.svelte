<script lang="ts">
import {onMount,untrack} from 'svelte';
import {invoke} from '@tauri-apps/api/core';
import {i18n} from '../../fabparts-ux/src/lib/i18n.svelte';
import Disclosure from '../../fabparts-ux/src/components/Disclosure.svelte';
import {AssistanceController,initialAI,type AIState} from './assistance';
let {id,onsaved=()=>{}}:{id:string;onsaved?:()=>Promise<void>|void}=$props();
let s=$state<AIState>(initialAI());
const tr=(fr:string,en:string)=>i18n.locale==='fr'?fr:en;
const label=(f:string)=>({manufacturer:tr('Fabricant','Manufacturer'),mpn:'MPN',category:tr('Catégorie','Category'),notes:tr('Notes d’identification','Identification notes')} as Record<string,string>)[f]||f;
const flow=new AssistanceController(invoke,untrack(()=>id),next=>s=next,()=>onsaved());
const count=$derived(Array.from(s.text).length);
const conflicts=$derived(s.rows.some(row=>s.selected.includes(row.field)&&row.conflict));
onMount(()=>{void flow.load();return()=>flow.dispose();});
</script>
<section class="ai-panel" aria-busy={s.saving}>
 <p class="secondary">{tr('L’IA propose des informations non vérifiées. Aucun fichier, catalogue ou PDF n’est envoyé automatiquement.','AI suggestions are unverified. No file, catalogue or PDF is sent automatically.')}</p>
 {#if s.config}
 <p class="secondary">{s.config.backend} · {s.config.model||tr('Modèle non configuré','Model not configured')} · {s.config.availability==='disabled'?tr('Désactivée · configurer dans Paramètres','Disabled · configure in Settings'):s.config.availability==='missing_key'?tr('Clé absente · voir Paramètres','Missing key · see Settings'):tr('Sur demande seulement','On request only')}</p>
 {/if}
 <fieldset disabled={s.saving}>
 <label>{tr('Contexte à analyser','Context to analyze')}<textarea class="input" rows="5" maxlength="32000" value={s.text} oninput={e=>flow.edit(e.currentTarget.value,s.include)} placeholder={tr('Extrait textuel, marquage observé ou informations connues…','Text excerpt, observed marking or known information…')}></textarea></label>
 <span class:invalid={count>16000} class="secondary">{count} / 16 000 {tr('caractères','characters')}</span>
 <label class="check"><input type="checkbox" checked={s.include} onchange={e=>flow.edit(s.text,e.currentTarget.checked)}/>{tr('Inclure les champs d’identification actuels','Include current identification fields')}</label>
 <button class="btn" disabled={s.pending||!count||count>16000||s.config?.availability!=='configured'} onclick={()=>flow.prepare()}>{tr('Relire les données à envoyer','Review data to send')}</button>
 </fieldset>
 {#if s.prepared}
 <div class="send-review">
  <h3>{tr('Envoi à autoriser','Review before sending')}</h3>
  <dl><dt>{tr('Fournisseur','Provider')}</dt><dd>{s.prepared.backend}</dd><dt>{tr('Destination réelle','Actual destination')}</dt><dd>{s.prepared.destination}</dd><dt>{tr('Modèle','Model')}</dt><dd>{s.prepared.model}</dd></dl>
  <p class="secondary">{tr('JSON utilisateur exact (contexte et identification autorisée) :','Exact user JSON (context and authorized identification):')}</p>
  <pre aria-label={tr('JSON utilisateur exact','Exact user JSON')}>{s.prepared.payload}</pre>
  <p class="secondary">{tr('Une instruction fixe M11 demande uniquement quatre champs JSON, sans outils ni navigation.','A fixed M11 instruction requests only four JSON fields, without tools or browsing.')}</p>
  {#if !s.rows.length}<label class="check"><input type="checkbox" checked={s.consent} disabled={s.pending} onchange={e=>flow.authorize(e.currentTarget.checked)}/>{tr('J’autorise cet envoi pour cette requête.','I authorize this data transfer for this request.')}</label>
  <button class="btn primary" disabled={!s.consent||s.pending} onclick={()=>flow.start()}>{tr('Analyser et proposer des informations','Analyze and suggest information')}</button>{/if}
 </div>
 {/if}
 {#if s.pending}<div class="row" role="status"><span>{tr('Analyse en cours… vous pouvez continuer à naviguer.','Analysis in progress… you can continue navigating.')}</span><button class="btn" onclick={()=>flow.invalidate()}>{tr('Annuler l’analyse','Cancel analysis')}</button></div>{/if}
 {#if s.rows.length}
 <div class="comparison">
  <h3>{tr('Propositions IA · non vérifiées','AI suggestions · unverified')}</h3>
  <div class="table-wrap"><table><thead><tr><th>{tr('Accepter','Accept')}</th><th>{tr('Champ','Field')}</th><th>{tr('Valeur actuelle','Current value')}</th><th>{tr('Proposition IA','AI suggestion')}</th></tr></thead><tbody>{#each s.rows as row}<tr><td><input type="checkbox" aria-label={tr('Accepter : ','Accept: ')+label(row.field)} checked={s.selected.includes(row.field)} disabled={s.saving} onchange={e=>flow.select(row.field,e.currentTarget.checked)}/></td><th>{label(row.field)}</th><td>{row.current||'—'}</td><td>{row.proposed}</td></tr>{/each}</tbody></table></div>
  {#if conflicts}<label class="check"><input type="checkbox" checked={s.replace} disabled={s.saving} onchange={e=>flow.replace(e.currentTarget.checked)}/>{tr('Je confirme le remplacement des valeurs existantes cochées.','I confirm replacing the checked existing values.')}</label>{/if}
  <div class="row"><button class="btn primary" disabled={s.saving||!s.selected.length||conflicts&&!s.replace} onclick={()=>flow.accept()}>{tr('Accepter les champs cochés','Accept checked fields')}</button><button class="btn" disabled={s.saving} onclick={()=>flow.invalidate()}>{tr('Ignorer les propositions','Ignore suggestions')}</button></div>
 </div>{/if}
 {#if s.error}<p class="error" role="alert">{s.error==='analysis_failed'?tr('Analyse échouée ou réponse invalide. Aucun champ enregistré. Vérifiez le fournisseur ou continuez manuellement.','Analysis failed or response invalid. No fields saved. Check the provider or continue manually.'):s.error}</p>{/if}
 {#if s.message}<p role="status">{tr('Champs acceptés et provenance enregistrés.','Accepted fields and provenance saved.')}</p>{/if}
 {#if s.identification?.history.length}<Disclosure id="ai-identification-history" label={tr('Historique de l’identification','Identification history')}>{#each [...s.identification.history].reverse() as event}<div class="history"><span>{event.recorded_at} · {event.source.label} · {event.source.origin}</span><span class="secondary">{event.source.reference}</span>{#each event.after as value}<span>{label(value.field)} : {event.before.find(v=>v.field===value.field)?.value||'—'} → {value.value}</span>{/each}</div>{/each}</Disclosure>{/if}
</section>
<style>
.ai-panel{display:flex;flex-direction:column;gap:var(--s3);min-width:0;font-size:var(--fs-sm)}p,h3{margin:0}h3{font-size:var(--fs-sm)}.secondary{color:var(--text-secondary)}fieldset{border:0;margin:0;padding:0;display:flex;flex-direction:column;gap:var(--s3);min-width:0}label{display:flex;flex-direction:column;gap:var(--s2)}label.check{flex-direction:row;align-items:center;gap:var(--s2)}textarea{width:100%;min-height:100px;resize:vertical}.send-review,.comparison{display:flex;flex-direction:column;gap:var(--s3);border-top:1px solid var(--border);padding-top:var(--s3);min-width:0}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:var(--bg-workspace);padding:var(--s3);max-height:240px;overflow:auto;font-size:var(--fs-sm);margin:0}dl{display:grid;grid-template-columns:auto 1fr;gap:var(--s2);margin:0}dd{margin:0;overflow-wrap:anywhere}dt{color:var(--text-secondary)}.row{display:flex;flex-wrap:wrap;gap:var(--s3);align-items:center}.table-wrap{overflow:auto}table{width:100%;border-collapse:collapse;table-layout:fixed}th,td{text-align:left;border-bottom:1px solid var(--border);padding:var(--s2);vertical-align:top;overflow-wrap:anywhere;white-space:normal;overflow:visible;text-overflow:clip;line-height:1.4}.comparison thead th:first-child{width:64px}.comparison thead th:nth-child(2){width:22%}.comparison thead th:nth-child(3){width:28%}.comparison thead th:nth-child(4){width:auto}.comparison tbody th{position:static;background:transparent;color:var(--text-primary);font-size:var(--fs-sm)}.history{display:flex;flex-direction:column;gap:var(--s2);overflow-wrap:anywhere;border-top:1px solid var(--divider);padding-top:var(--s2)}button{align-self:start}.error,.invalid{color:var(--danger-text)}
</style>
