<script lang="ts">
// Présente les preuves M5, les avertissements relus et une préparation distincte de l’état métier.
import {onDestroy,untrack} from 'svelte';
import {invoke} from '@tauri-apps/api/core';
import {ShieldCheck,TriangleAlert,CircleX,Check,RefreshCw} from '@lucide/svelte';
import {ReviewController,reviewInitial,type ReviewState,type Subject} from './validation';
import {vt,findingLabel,reportDate,type ValidationKey} from './validation_text';
let {id,kind='Part',writable=false,compact=false,onbusy=()=>{},onpart=()=>{}}:{id:string;kind?:Subject['kind'];writable?:boolean;compact?:boolean;onbusy?:(busy:boolean)=>void;onpart?:(id:string)=>void}=$props();
let state=$state<ReviewState>(reviewInitial());
const flow=new ReviewController(invoke,next=>{state=next;onbusy(next.busy);});
$effect(()=>{const subject={kind,id};untrack(()=>{void flow.select(subject);});});
onDestroy(()=>{flow.dispose();onbusy(false);});
const data=$derived(state.data);
</script>
<section class="validation-panel" aria-busy={state.busy} aria-label={vt(kind==='Part'?'title':'collection')}>
 <header><h2 class="section-heading"><ShieldCheck size={15}/>{vt(kind==='Part'?'title':'collection')}</h2>
  {#if !compact}<div class="actions">
   {#if writable}<button class="btn primary" disabled={state.busy} onclick={()=>void flow.validate()}><ShieldCheck size={14}/>{vt(data?.report?'refresh':kind==='Part'?'validate':'validateCollection')}</button>{/if}
   <button class="btn" title={vt('check')} disabled={state.busy} onclick={()=>void flow.refresh()}><RefreshCw size={14}/>{vt('check')}</button>
  </div>{/if}
 </header>
 {#if state.busy}<p role="status" class="secondary">{vt('loading')}</p>
 {:else if data}
  <div class="summary" aria-live="polite">
   {#if data.readiness}<strong class:ready={data.readiness!=='INCOMPLETE'}>{vt(data.readiness)}</strong>{/if}
   <span class:error={data.state==='ERROR'} class:warning={data.state==='WARNING'||data.state==='STALE'} class:ready={data.state==='PASS'}>{vt('fullResult')} : {vt(data.state)}</span>
   {#if data.report}<span class="secondary small">{vt('report')} {reportDate(data.report.created_at)}</span>{/if}
  </div>
  {#if data.state==='STALE'}<p class="warning">{vt('stale')}</p>{:else if !data.report}<p class="secondary">{vt('empty')}</p>{/if}
  {#if data.readiness==='SCHEMATIC'}<p class="secondary small">{vt('schematicScope')}</p>{/if}
  {#if !compact}
   <p class="secondary small">{vt('scope')} {kind==='Part'?vt('optional'):vt('memberScope')}</p>
   {#if !writable}<p class="secondary small">{vt('readonly')}</p>{/if}
   {#if data.report}
    {#if data.state==='STALE'}<p class="secondary">{vt('historical')}</p>{/if}
    <div class="counts"><span class="error">{data.report.counts.ERROR} {vt('ERROR')}</span><span class="warning">{data.report.counts.WARNING} {vt('WARNING')}</span><span class="ready">{data.report.counts.PASS} {vt('PASS')}</span></div>
    {#if data.report.warnings_accepted&&data.state!=='STALE'}<p class="secondary">{vt('accepted')}</p>{/if}
    {#if data.report.counts.WARNING}<button class="btn" disabled={state.busy} onclick={()=>flow.examine()}><TriangleAlert size={14}/>{vt('examine')}</button>{/if}
    {#each ['ERROR','WARNING','PASS'] as level}
     {@const rows=data.findings.filter(f=>f.level===level)}
     {#if rows.length}<details open={level==='ERROR'||(level==='WARNING'&&state.reviewOpen)}>
      <summary class:error={level==='ERROR'} class:warning={level==='WARNING'}>{vt(level as ValidationKey)} · {rows.length}</summary>
      <ul>{#each rows as finding}<li>
       <span class="finding-title">{#if level==='ERROR'}<CircleX size={14}/>{:else if level==='WARNING'}<TriangleAlert size={14}/>{:else}<Check size={14}/>{/if}<strong>{vt(finding.role as ValidationKey)}{finding.resource?' · '+finding.resource:''}</strong></span>
       <span>{findingLabel(finding.code)}</span>
       {#if level==='ERROR'}<p>{finding.message}</p>{/if}
       <details class="diagnostic"><summary>{vt('diagnostic')}</summary><p>{finding.message}</p><code>{finding.code}</code>{#if finding.sha256}<code>SHA-256 {finding.sha256}</code>{/if}</details>
      </li>{/each}</ul>
     </details>{/if}
    {/each}
    {#if data.total_findings>100}<nav class="pager" aria-label={vt('findings')}><button class="btn" disabled={state.busy||data.offset===0} onclick={()=>void flow.refresh(Math.max(0,data.offset-100),data.member_offset)}>{vt('previous')}</button><span>{data.offset+1}–{Math.min(data.offset+100,data.total_findings)} / {data.total_findings} {vt('findings')}</span><button class="btn" disabled={state.busy||data.offset+100>=data.total_findings} onclick={()=>void flow.refresh(data.offset+100,data.member_offset)}>{vt('next')}</button></nav>{/if}
    {#if state.reviewOpen&&writable&&data.state!=='STALE'&&data.report.counts.WARNING>0&&!data.report.warnings_accepted}
     {#if !state.allPages}<p class="secondary">{vt('pages')}</p>{/if}
     <div class="acceptance"><label><input type="checkbox" checked={state.confirmed} disabled={state.busy||!state.allPages} onchange={event=>flow.confirm(event.currentTarget.checked)}/>{vt('confirm')}</label>
     <button class="btn" disabled={state.busy||!state.confirmed||!data.handle} onclick={()=>void flow.accept()}>{vt('accept')}</button></div>
    {/if}
   {/if}
   {#if kind==='Collection'}
    <h3>{data.total_members} {vt('members')} · {vt(data.eligible?'qualified':data.state==='WARNING'?'pending':'notQualified')}</h3>
    <ul class="members">{#each data.members as member}<li><button class="btn quiet" title={vt('open')} disabled={state.busy} onclick={()=>onpart(member.id)}>{member.name}</button><span>{vt(member.state)}</span><span class:error={member.errors>0}>{member.errors} {vt('ERROR')}</span><span class:warning={member.warnings>0}>{member.warnings} {vt('WARNING')}</span></li>{/each}</ul>
    {#if data.total_members>50}<nav class="pager" aria-label={vt('members')}><button class="btn" disabled={state.busy||data.member_offset===0} onclick={()=>void flow.refresh(data.offset,Math.max(0,data.member_offset-50))}>{vt('previous')}</button><span>{data.member_offset+1}–{Math.min(data.member_offset+50,data.total_members)} / {data.total_members}</span><button class="btn" disabled={state.busy||data.member_offset+50>=data.total_members} onclick={()=>void flow.refresh(data.offset,data.member_offset+50)}>{vt('next')}</button></nav>{/if}
   {/if}
  {/if}
 {/if}
 {#if state.error}<p role="alert" class="error">{vt(state.error==='REPORT_CHANGED'?'changed':'failed')} <span class="secondary small">{state.error}</span></p>{/if}
</section>
<style>
.validation-panel{min-width:0;border-top:1px solid var(--divider);padding:var(--s3) 0;display:flex;flex-direction:column;gap:var(--s2)}
header,.actions,.summary,.counts,.pager{display:flex;gap:var(--s2);align-items:center;flex-wrap:wrap}header{justify-content:space-between}h2{display:flex;align-items:center;gap:var(--s2);margin:0}h3{font-size:var(--fs-sm);margin:var(--s2) 0}
p{margin:0;overflow-wrap:anywhere}.error{color:var(--danger-text)}.warning{color:var(--warning)}.ready{color:var(--success)}
.actions button{white-space:normal;height:auto;min-height:28px}.counts{font-size:var(--fs-sm)}details{min-width:0}summary{cursor:pointer;padding:var(--s1) 0;font-size:var(--fs-sm)}
ul{list-style:none;margin:0;padding:0}li{padding:var(--s2) 0;border-bottom:1px solid var(--divider);display:flex;flex-direction:column;gap:var(--s1);font-size:var(--fs-sm);overflow-wrap:anywhere}.finding-title{display:flex;align-items:center;gap:var(--s2)}strong{font-weight:500}.diagnostic{color:var(--text-secondary)}code{display:block;font-size:var(--fs-xs);overflow-wrap:anywhere}
.acceptance{display:flex;flex-direction:column;align-items:flex-start;gap:var(--s2)}label{display:flex;align-items:flex-start;gap:var(--s2);font-size:var(--fs-sm)}.members li{flex-direction:row;flex-wrap:wrap;align-items:center;gap:var(--s2)}
</style>
