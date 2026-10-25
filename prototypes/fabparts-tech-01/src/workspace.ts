import type {Transport} from './controller';
export type WorkspaceInfo={mode:'personal';path:string;backups:string;schema:string;restart_required:boolean};
export type BackupSelection={handle:string;files:number;schema:string;created_at:string};
export type WorkspaceState={busy:boolean;info:WorkspaceInfo|null;selection:BackupSelection|null;backup:string;restart:boolean;error:string;message:'saved'|'verified'|'restored'|''};
export const workspaceInitial=():WorkspaceState=>({busy:false,info:null,selection:null,backup:'',restart:false,error:'',message:''});
// Presentation state only. The native host selects paths; Python verifies and restores data.
export class WorkspaceController{
 state=workspaceInitial();
 private invoke:Transport;
 private changed:(state:WorkspaceState)=>void;
 constructor(invoke:Transport,changed:(state:WorkspaceState)=>void){this.invoke=invoke;this.changed=changed;}
 private emit(patch:Partial<WorkspaceState>){this.state={...this.state,...patch};this.changed(this.state);}
 private async run(work:()=>Promise<void>){
  if(this.state.busy)return;
  this.emit({busy:true,error:'',message:''});
  try{await work();}catch(error){this.emit({error:(error as {code?:string}).code||'WORKSPACE_FAILED'});}
  finally{this.emit({busy:false});}
 }
 async load(){await this.run(async()=>{const info=await this.invoke<WorkspaceInfo>('workspace_info');this.emit({info,restart:info.restart_required});});}
 async backup(){if(this.state.restart)return;await this.run(async()=>{const result=await this.invoke<{path:string}>('backup_workspace');this.emit({backup:result.path,message:'saved'});});}
 async select(locale:string){if(this.state.restart)return;await this.run(async()=>{
  this.emit({selection:null});const result=await this.invoke<BackupSelection&{cancelled?:boolean}>('choose_workspace_backup',{locale});
  if(!result.cancelled)this.emit({selection:result,message:'verified'});
 });}
 async restore(locale:string){const selected=this.state.selection;if(!selected||this.state.restart)return;
  await this.run(async()=>{const result=await this.invoke<{cancelled?:boolean;restart_required?:boolean;retained_backup?:string}>('restore_workspace',{handle:selected.handle,locale});
   if(!result.cancelled)this.emit({selection:null,restart:!!result.restart_required,backup:result.retained_backup||'',message:'restored'});
  });
 }
}
