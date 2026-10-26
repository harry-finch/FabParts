import type { Transport } from './controller';
export const ingestionRoles = ['SYMBOL','FOOTPRINT','MODEL_3D','DATASHEET'] as const;
export type Fields = { reference:string;mpn:string;manufacturer:string;description:string;category:string;package_id:string;package_name:string;collections:string[] };
export const emptyFields = ():Fields => ({reference:'',mpn:'',manufacturer:'',description:'',category:'',package_id:'',package_name:'',collections:[]});
export type MetadataSuggestion={token:string;field:"mpn"|"manufacturer"|"category";value:string;source:string;reference:string};
export type GuidedResult={candidates:Candidate[];metadata:MetadataSuggestion[];packages:{id:string;name:string;source:string}[];similar:{id:string;name:string}[];notices:string[]};
export type Candidate = {match?:string;reason?:string;source?:string;package?:string;token:string;role:string;name:string;origin:string;storage:string;sha256:string;warning:string;validation_state:string};
export type FileItem = {handle:string;file:{original_name:string;extension:string;sha256:string;size_bytes:number};symbols:string[]};
export type Duplicate = {id:string;name:string;mpn:string;manufacturer:string};
export type Preparation = {preparation:string;operation_id:string;part_id:string;fields:Fields;selections:Record<string,string>;candidates:Candidate[];collections:{id:string;name:string}[];packages:{id:string;name:string}[];categories:string[]};
export type Confirmation = {status:'saved'|'not_committed';part_id?:string;operation_id:string};
export type RecoveryStore = {get():string|null;set(id:string):void;clear():void};
export const browserRecovery:RecoveryStore = {
  get:()=>localStorage.getItem('fabparts.ingestion.operation'),
  set:id=>localStorage.setItem('fabparts.ingestion.operation',id),
  clear:()=>localStorage.removeItem('fabparts.ingestion.operation'),
};
export const business = <T>(invoke:Transport, method:string, params:Record<string,unknown>):Promise<T> =>
  invoke<T>('ingestion_command',{request:{method,params}});
export type IngestionState = {session:Preparation|null;fields:Fields;selections:Record<string,string>;candidates:Candidate[];files:FileItem[];duplicates:Duplicate[];notices:string[];busy:boolean;error:string;recovery:boolean;step:number;variant:boolean;searching:string[];discovering:boolean;discovered:boolean;metadata:MetadataSuggestion[];acceptedMetadata:Record<string,string>;proposedPackages:GuidedResult["packages"];similar:GuidedResult["similar"];previewing:Record<string,string>};
export const initialIngestion = ():IngestionState => ({session:null,fields:emptyFields(),selections:{},candidates:[],files:[],duplicates:[],notices:[],busy:false,error:'',recovery:false,step:0,variant:false,searching:[],discovering:false,discovered:false,metadata:[],acceptedMetadata:{},proposedPackages:[],similar:[],previewing:{}});

// Presentation state only. Identity, ownership and persistence are decided by Python.
export class IngestionController {
  state=initialIngestion();
  private epoch=0;
  private discoveryEpoch=0;
  private searches:Record<string,number>={};
  private invoke:Transport;
  private changed:(state:IngestionState)=>void;
  private saved:(id:string)=>Promise<void>|void;
  private recoveryStore:RecoveryStore;
  constructor(invoke:Transport, changed:(state:IngestionState)=>void,
              saved:(id:string)=>Promise<void>|void, recoveryStore:RecoveryStore) {
    this.invoke=invoke;this.changed=changed;this.saved=saved;this.recoveryStore=recoveryStore;
  }
  private emit(patch:Partial<IngestionState>) { this.state={...this.state,...patch};this.changed(this.state); }
  private error(error:unknown) {return (error as {message?:string})?.message || String(error);}
  private merge(candidates:Candidate[]) {
    const map=new Map(this.state.candidates.map(c=>[c.token,c]));
    for(const c of candidates)map.set(c.token,{...map.get(c.token),...c});
    return [...map.values()];
  }
  edit(patch:Partial<Fields>) {
    this.discoveryEpoch++;
    const acceptedMetadata={...this.state.acceptedMetadata};
    for(const key of Object.keys(patch))delete acceptedMetadata[key];
    const identityChanged=['reference','mpn','manufacturer'].some(k=>k in patch && patch[k as keyof Fields]!==this.state.fields[k as keyof Fields]);
    this.emit({fields:{...this.state.fields,...patch},acceptedMetadata,error:'',discovered:false,discovering:false,
      ...(identityChanged?{metadata:[],proposedPackages:[],similar:[],previewing:{},candidates:this.state.candidates.filter(c=>c.storage==='staged'||this.state.selections[c.role]===c.token)}:{})});
  }
  preview(role:string,token:string) {this.emit({previewing:{...this.state.previewing,[role]:token}});}
  acceptMetadata(item:MetadataSuggestion) {
    if(this.state.discovering||!this.state.metadata.some(m=>m.token===item.token))return;
    this.emit({fields:{...this.state.fields,[item.field]:item.value},acceptedMetadata:{...this.state.acceptedMetadata,[item.field]:item.token}});
    void this.inspect();
  }
  async discover() {
    if(!this.state.session||this.state.busy||this.state.discovering)return;
    const fields=this.state.fields, epoch=this.epoch, discovery=++this.discoveryEpoch;
    if(!(fields.reference.trim()||fields.mpn.trim())){this.emit({error:'identity_required'});return;}
    this.emit({discovering:true,discovered:false,error:'',step:2,notices:[]});
    try {
      await this.inspect();
      for(const role of ingestionRoles) {
        if(epoch!==this.epoch||discovery!==this.discoveryEpoch)return;
        const result=await business<GuidedResult>(this.invoke,'ingestion_discover',{preparation:this.state.session.preparation,fields,role});
        if(epoch!==this.epoch||discovery!==this.discoveryEpoch)return;
        const kept=this.state.candidates.filter(c=>c.role!==role||c.token===this.state.selections[role]||c.storage==='staged');
        this.emit({candidates:[...new Map([...kept,...result.candidates].map(c=>[c.token,c])).values()],metadata:result.metadata,proposedPackages:result.packages,similar:result.similar,notices:[...new Set([...this.state.notices,...result.notices])]});
      }
      this.emit({discovered:true});
    }catch(error){if(epoch===this.epoch&&discovery===this.discoveryEpoch)this.emit({error:this.error(error)});}
    finally{if(epoch===this.epoch&&discovery===this.discoveryEpoch)this.emit({discovering:false});}
  }
  choose(role:string,token:string) {
    const selections={...this.state.selections};if(token)selections[role]=token;else delete selections[role];
    this.emit({selections,previewing:{...this.state.previewing,[role]:token},error:''});
  }
  variant(value:boolean) {this.emit({variant:value});}
  async begin(partId='',library='all') {
    const epoch=++this.epoch;this.emit({...initialIngestion(),busy:true});
    try {
      const session=await business<Preparation>(this.invoke,'ingestion_begin',{part_id:partId});
      if(epoch!==this.epoch)return;
      const fields={...session.fields,collections:[...session.fields.collections]};
      if(!partId && session.collections.length)fields.collections=[session.collections.find(c=>c.id===library)?.id || session.collections[0].id];
      this.emit({session,fields,selections:session.selections,candidates:session.candidates,busy:false});
    }catch(error){if(epoch===this.epoch)this.emit({error:this.error(error),busy:false});}
  }
  addExternal(value:{file:FileItem;candidate:Candidate}) {
    this.emit({files:[...this.state.files.filter(f=>f.handle!==value.file.handle),value.file],
      candidates:this.merge([value.candidate]),previewing:{...this.state.previewing,[value.candidate.role]:value.candidate.token}});
  }
  async pick() {
    const prep=this.state.session?.preparation;if(!prep||this.state.busy)return;
    const epoch=this.epoch;this.emit({busy:true,error:''});
    try {
      const result=await this.invoke<{cancelled:boolean;files:FileItem[];errors:{message:string}[]}>('choose_ingestion_files',{preparation:prep});
      if(epoch!==this.epoch)return;
      if(!result.cancelled)this.emit({files:[...this.state.files,...result.files],error:result.errors.map(e=>e.message).join(' ')});
      for(const role of ingestionRoles)await this.search(role);
    }catch(error){if(epoch===this.epoch)this.emit({error:this.error(error)});}
    finally{if(epoch===this.epoch)this.emit({busy:false});}
  }
  async remove(handle:string) {
    const preparation=this.state.session?.preparation;if(!preparation||this.state.busy)return;
    const epoch=this.epoch;this.emit({busy:true,error:''});
    try {
      const {removed}=await business<{removed:string[]}>(this.invoke,'ingestion_remove',{preparation,handle});
      if(epoch!==this.epoch)return;
      this.emit({files:this.state.files.filter(f=>f.handle!==handle),candidates:this.state.candidates.filter(c=>!removed.includes(c.token)),selections:Object.fromEntries(Object.entries(this.state.selections).filter(([,v])=>!removed.includes(v)))});
    }catch(error){if(epoch===this.epoch)this.emit({error:this.error(error)});}
    finally{if(epoch===this.epoch)this.emit({busy:false});}
  }
  async search(role:string,query='') {
    const prep=this.state.session?.preparation;if(!prep)return;
    const epoch=this.epoch, token=(this.searches[role]||0)+1;this.searches[role]=token;
    this.emit({searching:[...new Set([...this.state.searching,role])]});
    try{
      const result=await business<{candidates:Candidate[];notices:string[]}>(this.invoke,'ingestion_search',{preparation:prep,role,query});
      if(epoch===this.epoch && token===this.searches[role]){
        const selected=this.state.selections[role];
        const kept=this.state.candidates.filter(c=>c.role!==role||c.token===selected);
        this.emit({candidates:[...new Map([...kept,...result.candidates].map(c=>[c.token,c])).values()],notices:[...new Set([...this.state.notices,...result.notices])]});
      }
    }catch(error){if(epoch===this.epoch)this.emit({error:this.error(error)});}
    finally{if(epoch===this.epoch&&token===this.searches[role])this.emit({searching:this.state.searching.filter(r=>r!==role)});}
  }
  async inspect(packageChanged=false) {
    const prep=this.state.session?.preparation;if(!prep)return false;
    const epoch=this.epoch, fields=this.state.fields;
    try{
      const info=await business<{duplicates:Duplicate[];package_selections:Record<string,string>;candidates:Candidate[]}>(this.invoke,'ingestion_inspect',{preparation:prep,fields});
      if(epoch!==this.epoch||fields!==this.state.fields)return false;
      let selections={...this.state.selections};
      if(packageChanged){delete selections.FOOTPRINT;delete selections.MODEL_3D;selections={...selections,...info.package_selections};}
      this.emit({duplicates:info.duplicates,candidates:this.merge(info.candidates),selections});
      return true;
    }catch(error){if(epoch===this.epoch)this.emit({error:this.error(error)});return false;}
  }
  async next() {
    if(this.state.busy||this.state.discovering||!this.state.session)return;
    if(!this.state.fields.reference.trim()&&!this.state.fields.mpn.trim()){this.emit({error:'identity_required'});return;}
    if(!this.state.fields.collections.length){this.emit({error:'library_required'});return;}
    this.emit({busy:true,error:''});
    if(await this.inspect()){
      const next=Math.min(2,this.state.step+1);
      if(next===2&&!this.state.discovered)for(const role of ingestionRoles)await this.search(role,(this.state.fields.mpn||this.state.fields.reference).slice(0,255));
      this.emit({step:next});
    }
    this.emit({busy:false});
  }
  back(step:number) {if(!this.state.busy)this.emit({step,error:''});}
  async commit(action:'save'|'variant'|'membership'='save', existingId='') {
    const session=this.state.session;if(!session||this.state.busy||this.state.discovering||this.state.recovery)return;
    if(!this.state.fields.reference.trim()&&!this.state.fields.mpn.trim()){this.emit({error:'identity_required'});return;}
    if(!this.state.fields.collections.length){this.emit({error:'library_required'});return;}
    const epoch=this.epoch;this.emit({busy:true,error:''});
    try {
      this.recoveryStore.set(session.operation_id);
      const result=await business<Confirmation>(this.invoke,'ingestion_commit',{
        preparation:session.preparation,operation_id:session.operation_id,
        fields:this.state.fields,selections:this.state.selections,metadata:this.state.acceptedMetadata,action,existing_id:existingId,
      });
      if(epoch!==this.epoch)return;
      if(result.status!=='saved'||!result.part_id)throw Error('confirmation_missing');
      this.recoveryStore.clear();
      await this.saved(result.part_id);
    }catch(error){
      if(epoch!==this.epoch)return;
      // Query the receipt before suggesting another attempt. Do not auto-repeat a write.
      try{
        const result=await business<Confirmation>(this.invoke,'ingestion_result',{operation_id:session.operation_id});
        if(epoch!==this.epoch)return;
        if(result.status==='saved'&&result.part_id){this.recoveryStore.clear();await this.saved(result.part_id);return;}
        this.recoveryStore.clear();this.emit({error:this.error(error)});
        await this.inspect();
      }catch{if(epoch===this.epoch)this.emit({error:'confirmation_unknown',recovery:true});}
    }finally{if(epoch===this.epoch)this.emit({busy:false});}
  }
  async recover() {
    const operation=this.recoveryStore.get();if(!operation||this.state.busy)return;
    this.emit({busy:true,error:''});
    try{
      await this.invoke('restart_engine');
      const result=await business<Confirmation>(this.invoke,'ingestion_result',{operation_id:operation});
      this.recoveryStore.clear();
      if(result.status==='saved'&&result.part_id)await this.saved(result.part_id);
      else this.emit({session:null,recovery:false,error:'not_committed'});
    }catch(error){this.emit({error:this.error(error),recovery:true});}
    finally{this.emit({busy:false});}
  }
  async cancel() {
    if(this.state.busy||this.state.recovery)return false;
    const prep=this.state.session?.preparation;this.epoch++;
    if(prep)try{await business(this.invoke,'ingestion_cancel',{preparation:prep});}catch(error){this.emit({error:this.error(error)});return false;}
    this.emit({session:null});return true;
  }
  dispose(){this.epoch++;}
}
