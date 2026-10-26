import type {Transport} from './controller';
export type AIConfig={enabled:boolean;backend:'gemini'|'chat'|'ollama';endpoint:string;model:string;destination:string;availability:'disabled'|'configured'|'missing_key'};
export type Identification={revision:number;values:Record<string,string>;history:{source:{label:string;reference:string;origin:string};recorded_at:string;before:{field:string;value:string}[];after:{field:string;value:string}[]}[]};
export type PreparedAI={handle:string;payload:string;sha256:string;destination:string;backend:string;model:string;revision:number};
export type AIRow={field:string;current:string;proposed:string;conflict:boolean};
export const ai=<T>(invoke:Transport,method:string,params:Record<string,unknown>={}):Promise<T>=>invoke<T>('assistance_command',{request:{method,params}});
export type AIDiagnostic={code:string;http_status:number|null};
export type AIState={config:AIConfig|null;identification:Identification|null;prepared:PreparedAI|null;text:string;include:boolean;consent:boolean;rows:AIRow[];selected:string[];replace:boolean;pending:boolean;saving:boolean;diagnostic:AIDiagnostic|null;error:string;message:string};
export const initialAI=():AIState=>({config:null,identification:null,prepared:null,text:'',include:false,consent:false,rows:[],selected:[],replace:false,pending:false,saving:false,diagnostic:null,error:'',message:''});
export class AssistanceController {
 state=initialAI();private epoch=0;private handle='';private invoke:Transport;private id:string;
 private changed:(state:AIState)=>void;private accepted:()=>Promise<void>|void;private delay:()=>Promise<void>;
 constructor(invoke:Transport,id:string,changed:(state:AIState)=>void,accepted:()=>Promise<void>|void,delay:()=>Promise<void>=()=>new Promise(r=>setTimeout(r,200))){this.invoke=invoke;this.id=id;this.changed=changed;this.accepted=accepted;this.delay=delay;}
 private emit(patch:Partial<AIState>){this.state={...this.state,...patch};this.changed(this.state);}
 private error(e:unknown){return (e as {message?:string}).message||String(e);}
 async load(){const epoch=this.epoch;try{const [config,identification]=await Promise.all([ai<AIConfig>(this.invoke,'assistance_configuration'),ai<Identification>(this.invoke,'assistance_identification',{id:this.id})]);if(epoch===this.epoch)this.emit({config,identification});}catch(e){if(epoch===this.epoch)this.emit({error:this.error(e)});}}
 private async revoke(handle:string){try{await ai(this.invoke,'assistance_cancel',{id:this.id,handle});}catch{/* Session may already be closed. */}}
 invalidate(){this.epoch++;const handle=this.handle;this.handle='';if(handle)void this.revoke(handle);this.emit({prepared:null,consent:false,rows:[],selected:[],replace:false,pending:false,diagnostic:null,error:'',message:''});}
 edit(text:string,include:boolean){if(this.state.saving)return;this.invalidate();this.emit({text,include});}
 authorize(value:boolean){if(this.state.prepared&&!this.state.pending)this.emit({consent:value});}
 select(field:string,value:boolean){const selected=value?[...new Set([...this.state.selected,field])]:this.state.selected.filter(f=>f!==field);this.emit({selected,replace:false});}
 replace(value:boolean){this.emit({replace:value});}
 async prepare(){
  this.invalidate();const epoch=this.epoch;this.emit({pending:true});
  try{const prepared=await ai<PreparedAI>(this.invoke,'assistance_prepare',{id:this.id,text:this.state.text,include:this.state.include});if(epoch!==this.epoch){void this.revoke(prepared.handle);return;}this.handle=prepared.handle;this.emit({prepared,consent:false});}
  catch(e){if(epoch===this.epoch)this.emit({error:this.error(e)});}finally{if(epoch===this.epoch)this.emit({pending:false});}
 }
 async start(){
  const prepared=this.state.prepared;if(!prepared||!this.state.consent||this.state.pending)return;
  const epoch=this.epoch;this.emit({pending:true,consent:false,rows:[],selected:[],replace:false,diagnostic:null,error:'',message:''});
  try{
   await ai(this.invoke,'assistance_start',{id:this.id,handle:prepared.handle,consent:true});
   while(epoch===this.epoch){const result=await ai<{status:string;rows:AIRow[];error?:AIDiagnostic}>(this.invoke,'assistance_status',{id:this.id,handle:prepared.handle});if(epoch!==this.epoch)return;
    if(result.status==='error'){this.emit({diagnostic:result.error??{code:'unknown',http_status:null}});throw Error('analysis_failed');}
    if(result.status==='ready'){this.emit({rows:result.rows,selected:[],replace:false});return;}
    await this.delay();
   }
  }catch(e){if(epoch===this.epoch)this.emit({error:this.error(e),prepared:null,consent:false});}finally{if(epoch===this.epoch)this.emit({pending:false});}
 }
 async accept(){
  if(!this.state.prepared||this.state.pending||this.state.saving||!this.state.selected.length)return;
  const epoch=this.epoch;this.emit({saving:true,error:''});
  try{const identification=await ai<Identification>(this.invoke,'assistance_accept',{id:this.id,handle:this.state.prepared.handle,fields:this.state.selected,replace_existing:this.state.replace});if(epoch!==this.epoch)return;this.handle='';this.emit({identification,prepared:null,rows:[],selected:[],replace:false,consent:false,text:'',include:false,message:'accepted'});await this.accepted();}
  catch(e){if(epoch===this.epoch)this.emit({error:this.error(e),prepared:null,rows:[],selected:[],replace:false,consent:false});}finally{if(epoch===this.epoch)this.emit({saving:false});}
 }
 dispose(){this.invalidate();}
}
