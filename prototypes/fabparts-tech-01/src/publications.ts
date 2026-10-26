import type {Transport} from './controller';
export type Version={version:number;created_at:string;collection_name:string;manifest_sha256:string;verification:string};
export type History={scope:string;id:string;name:string;count:number;state:string;eligible:boolean;proposed:number|null;reserved_count:number;total:number;offset:number;versions:Version[]};
export type Summary={name:string;count:number;fingerprint:string;library:string;offset:number;parts:{id:string;name:string;resources:{role:string;name:string;origin:string}[]}[];version:number;handle?:string;level:string;warnings_accepted:boolean;warnings?:number;warning_codes?:string[];file_count?:number;files?:string[];created_at?:string;manifest_sha256?:string};
export type Pending={scope:string;id:string;version:number;fingerprint:string};
export interface Recovery {get():Pending|null;set(value:Pending):void;clear():void}
const key='fabparts.publication.pending.v1';
export const publicationRecovery:Recovery={get(){try{const p=JSON.parse(localStorage.getItem(key)||'null');return p&&typeof p.scope==='string'&&typeof p.id==='string'&&Number.isInteger(p.version)&&typeof p.fingerprint==='string'?p:null;}catch{return null;}},set(p){localStorage.setItem(key,JSON.stringify(p));},clear(){localStorage.removeItem(key);}};
export type State={busy:boolean;history:History|null;summary:Summary|null;detail:Summary|null;confirmed:boolean;error:string;errorMessage:string;notice:string;pending:Pending|null;checks:Record<number,string>};
export const initialPublications=():State=>({busy:false,history:null,summary:null,detail:null,confirmed:false,error:'',errorMessage:'',notice:'',pending:null,checks:{}});
// M5/M6/M7 own qualification, construction and durable engagement. Never retry a mutation.
export class PublicationController{
 state=initialPublications();private id='';private generation=0;private disposed=false;
 private invoke:Transport;private recovery:Recovery;private changed:(s:State)=>void;
 constructor(invoke:Transport,recovery:Recovery,changed:(s:State)=>void){this.invoke=invoke;this.recovery=recovery;this.changed=changed;}
 private emit(p:Partial<State>){if(this.disposed)return;this.state={...this.state,...p};this.changed(this.state);}
 private query<T>(action:string,version?:number,offset=0,id=this.id){return this.invoke<T>('publication_query',{query:{action,id,...(version===undefined?{}:{version}),offset}});}
 private async run(work:()=>Promise<void>){if(this.state.busy)return;const g=this.generation;this.emit({busy:true,error:'',errorMessage:'',notice:'',confirmed:false});try{await work();}catch(e){if(g===this.generation)this.emit({error:(e as {code?:string})?.code||'PUBLICATION_FAILED',errorMessage:(e as {message?:string})?.message||'',summary:null});}finally{if(g===this.generation)this.emit({busy:false});}}
 async select(id:string){if(this.state.busy)return;this.generation++;this.id=id;this.emit({...initialPublications(),pending:this.recovery.get()});await this.refresh();}
 async refresh(offset=0){const g=this.generation;await this.run(async()=>{const history=await this.query<History>('history',undefined,offset);if(g===this.generation)this.emit({history,summary:null,detail:null,checks:{}});});}
 async prepare(offset=0){if(this.state.pending)return;const g=this.generation;await this.run(async()=>{const summary=await this.query<Summary>('prepare',undefined,offset);if(g===this.generation)this.emit({summary,detail:null});});}
 confirm(value:boolean){this.emit({confirmed:value&&!!this.state.summary?.handle&&!this.state.busy&&!this.state.pending});}
 cancel(){this.emit({summary:null,confirmed:false});}
 async publish(){
  const summary=this.state.summary;if(!summary?.handle||!this.state.confirmed||this.state.pending)return;
  await this.run(async()=>{
   const pending={scope:this.state.history!.scope,id:this.id,version:summary.version,fingerprint:summary.fingerprint};
   this.recovery.set(pending);this.emit({pending});
   let failure:unknown;
   try{await this.invoke('publish_version',{id:this.id,version:summary.version,handle:summary.handle});}catch(error){failure=error;}
   // A lost response never determines whether COMMIT exists.
   await this.reconcile();
   if(this.state.notice!=='committed'&&failure)throw failure;
  });
 }
 private async reconcile(){
  const p=this.recovery.get();if(!p)return;
  const current=await this.query<History>('history');
  if(current.scope!==p.scope)throw{code:'WORKSPACE_MISMATCH'};
  const status=await this.query<{status:string;fingerprint?:string}>('status',p.version,0,p.id);
  if(status.status==='COMMITTED'&&status.fingerprint!==p.fingerprint)throw{code:'VERSION_CONFLICT'};
  if(!['COMMITTED','ABSENT','RESERVED'].includes(status.status))throw{code:'UNKNOWN_ENGAGEMENT'};
  this.recovery.clear();this.emit({pending:null,summary:null,notice:status.status==='COMMITTED'?'committed':status.status==='RESERVED'?'reserved':'absent'});
  const history=await this.query<History>('history');this.emit({history,checks:{}});
 }
 async recover(){await this.run(async()=>{await this.invoke('restart_engine',{});await this.reconcile();});}
 async details(version:number,offset=0){await this.run(async()=>{const detail=await this.query<Summary>('details',version,offset);this.emit({detail,summary:null});});}
 async verify(version:number){await this.run(async()=>{this.emit({checks:{...this.state.checks,[version]:'CHECKING'}});try{await this.query('verify',version);this.emit({checks:{...this.state.checks,[version]:'PASS'}});}catch(e){this.emit({checks:{...this.state.checks,[version]:'FAILED'}});throw e;}});}
 async rebuild(version:number,locale:string){await this.run(async()=>{const r=await this.invoke<{cancelled?:boolean;rebuilt?:boolean;destination?:string}>('rebuild_publication',{id:this.id,version,locale});if(r.rebuilt)this.emit({notice:`rebuilt:${r.destination}`});});}
 dispose(){this.disposed=true;this.generation++;}
}
