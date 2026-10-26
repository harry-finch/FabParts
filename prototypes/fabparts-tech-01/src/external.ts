import type {Transport} from './controller';
import type {Candidate,FileItem} from './ingestion';
export type Configuration={kicad:{enabled:boolean;revision:string};pdf:{enabled:boolean;domains:string[]}};
export type RemoteCandidate={token:string;asset_type:string;library:string;name:string;revision:string;commit:string;description:string;source:string;availability:string};
export type Staged={file:FileItem;candidate:Candidate};
export type Result={status:'loading'|'ready'|'error';handle?:string;message?:string;candidates?:RemoteCandidate[];notices?:string[]}&Partial<Staged>;
export const external=<T>(invoke:Transport,method:string,params:Record<string,unknown>={}):Promise<T>=>invoke<T>('external_command',{request:{method,params}});
export class ExternalController {
 private epoch=0;
 private handle='';
 private invoke:Transport; private preparation:string; private result:(value:Result)=>void;
 private pending:(value:boolean)=>void; private failed:(message:string)=>void; private delay:()=>Promise<void>;
 constructor(invoke:Transport,preparation:string,result:(value:Result)=>void,pending:(value:boolean)=>void,failed:(message:string)=>void,delay:()=>Promise<void>=()=>new Promise(resolve=>setTimeout(resolve,200))){
  this.invoke=invoke;this.preparation=preparation;this.result=result;this.pending=pending;this.failed=failed;this.delay=delay;
 }
 async start(method:string,params:Record<string,unknown>){
  const epoch=++this.epoch;
  this.pending(true);this.failed('');
  try{
   const started=await external<Result>(this.invoke,method,{preparation:this.preparation,...params});
   if(epoch!==this.epoch){if(started.handle)void this.cancelHandle(started.handle);return;}
   this.handle=started.handle||'';
   if(!this.handle)throw Error('Missing network operation');
   while(epoch===this.epoch){
    const value=await external<Result>(this.invoke,'external_status',{preparation:this.preparation,handle:this.handle});
    if(epoch!==this.epoch)return;
    if(value.status==='error')throw Error(value.message||'Source unavailable');
    if(value.status==='ready'){this.result(value);return;}
    await this.delay();
   }
  }catch(error){if(epoch===this.epoch)this.failed((error as {message?:string}).message||String(error));}
  finally{if(epoch===this.epoch){this.handle='';this.pending(false);}}
 }
 private async cancelHandle(handle:string){try{await external(this.invoke,'external_cancel',{preparation:this.preparation,handle});}catch{/* Preparation may already be closed. */}}
 cancel(){this.epoch++;const handle=this.handle;this.handle='';this.pending(false);if(handle)void this.cancelHandle(handle);}
}
