import type {Transport} from './controller';
export type Integration={targets:{id:string;configuration:string}[];target:string;latest:number|null;active:number|null;previous:number|null;state:string;publication_error?:string;kicad_open?:boolean;verified?:boolean;checked_at?:string;error?:string;tables:{name:string;present:boolean}[];installed?:{id:string;name:string;version:number}[];operations:{id:string;date:string;version:number;collection:string}[]};
export type IntegrationSummary={handle:string;collection_name?:string;version?:number;active?:number|null;nickname?:string;uris?:string[];tables:string[];target:string;action?:string;reconcile?:boolean};
export type State={busy:boolean;data:Integration|null;summary:IntegrationSummary|null;confirmed:boolean;error:string;message:string;notice:string};
export const initialIntegration=():State=>({busy:false,data:null,summary:null,confirmed:false,error:'',message:'',notice:''});
export class IntegrationController{
 state=initialIntegration();private id='';private target='';private disposed=false;
 private invoke:Transport;private changed:(s:State)=>void;
 constructor(invoke:Transport,changed:(s:State)=>void){this.invoke=invoke;this.changed=changed;}
 private emit(p:Partial<State>){if(this.disposed)return;this.state={...this.state,...p};this.changed(this.state);}
 private call<T>(action:string,extra:Record<string,unknown>={}){return this.invoke<T>('integration_command',{request:{action,id:this.id,...(this.target?{target:this.target}:{}),...extra}});}
 private async run(work:()=>Promise<void>){if(this.state.busy||this.disposed)return;this.emit({busy:true,error:'',message:'',notice:'',confirmed:false});try{await work();}catch(e){this.emit({summary:null,error:(e as {code?:string})?.code||'INTEGRATION_FAILED',message:(e as {message?:string})?.message||''});}finally{this.emit({busy:false});}}
 async select(id:string,target=''){if(this.state.busy)return;this.id=id;this.target=target;this.emit(initialIntegration());await this.refresh();}
 async refresh(){await this.run(async()=>{this.emit({data:null,summary:null});const data=await this.call<Integration>('get');this.target=data.target;this.emit({data,summary:null});});}
 async choose(target:string){if(this.state.busy)return;this.target=target;await this.refresh();}
 async prepare(version:number){await this.run(async()=>{const summary=await this.call<IntegrationSummary>('prepare',{version});this.emit({summary});});}
 async prepareRecovery(){await this.run(async()=>{const summary=await this.call<IntegrationSummary>('recovery');this.emit({summary});});}
 confirm(value:boolean){this.emit({confirmed:value&&!!this.state.summary&&!this.state.busy});}
 cancel(){this.emit({summary:null,confirmed:false});}
 async apply(){const summary=this.state.summary;if(!summary||!this.state.confirmed)return;
  await this.run(async()=>{try{const data=await this.call<Integration>(summary.action==='restore_previous_tables'?'recover':'activate',{handle:summary.handle});this.emit({data,summary:null,notice:'confirmed'});}catch(error){
    // Inspect durable state after an uncertain outcome; never repeat the mutation.
    try{const data=await this.call<Integration>('get');this.emit({data,summary:null});}catch{this.emit({data:null,summary:null});}throw error;
  }});
 }
 async verify(){await this.run(async()=>{this.emit({data:this.state.data?{...this.state.data,verified:false}:null});try{const data=await this.call<Integration>('verify');this.emit({data});}catch(error){this.emit({data:this.state.data?{...this.state.data,state:'ERROR',verified:false}:null});throw error;}});}
 async reconnect(){await this.run(async()=>{await this.invoke('restart_engine',{});const data=await this.call<Integration>('get');this.target=data.target;this.emit({data,summary:null});});}
 dispose(){this.disposed=true;}
}
