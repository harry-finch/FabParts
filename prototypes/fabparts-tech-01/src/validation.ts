import type {Transport} from './controller';
export type Subject={kind:'Part'|'Collection';id:string};
export type Finding={code:string;level:'PASS'|'WARNING'|'ERROR';message:string;part_id:string;role:string;resource:string;sha256:string};
export type Review={kind:Subject['kind'];id:string;name:string;state:'UNCHECKED'|'STALE'|'PASS'|'WARNING'|'ERROR';eligible:boolean;readiness:'INCOMPLETE'|'SCHEMATIC'|'PCB'|null;
 report:{created_at:string;level:Finding['level'];ruleset:string;warnings_accepted:boolean;counts:Record<Finding['level'],number>}|null;
 findings:Finding[];total_findings:number;offset:number;members:{id:string;name:string;state:Review['state'];errors:number;warnings:number}[];member_offset:number;total_members:number;handle:string|null};
export type ReviewState={busy:boolean;data:Review|null;error:string;reviewOpen:boolean;confirmed:boolean;allPages:boolean};
export const reviewInitial=():ReviewState=>({busy:false,data:null,error:'',reviewOpen:false,confirmed:false,allPages:false});
// Presentation only. M5 and the Python projection own eligibility and preparation.
export class ReviewController{
 state=reviewInitial();
 private invoke:Transport;private changed:(state:ReviewState)=>void;
 private generation=0;private subject:Subject|null=null;private pages=new Set<number>();private reportKey='';
 constructor(invoke:Transport,changed:(state:ReviewState)=>void){this.invoke=invoke;this.changed=changed;}
 private emit(patch:Partial<ReviewState>){this.state={...this.state,...patch};this.changed(this.state);}
 async select(subject:Subject){this.generation++;this.subject=subject;this.pages.clear();this.reportKey='';this.emit(reviewInitial());await this.request('get_validation',{query:subject});}
 private async request(command:string,args:Record<string,unknown>){
  if(this.state.busy)return;
  const generation=this.generation;this.emit({busy:true,error:'',confirmed:false,reviewOpen:false});
  try{
   const data=await this.invoke<Review>(command,args);
   if(generation!==this.generation)return;
   const key=`${data.id}:${data.report?.created_at}:${data.state}:${data.report?.warnings_accepted}`;
   if(key!==this.reportKey){this.pages.clear();this.reportKey=key;}
   this.pages.add(data.offset);
   const allPages=Array.from({length:Math.ceil(data.total_findings/100)},(_,i)=>i*100).every(offset=>this.pages.has(offset));
   this.emit({data,allPages});
  }catch(error){if(generation===this.generation)this.emit({data:null,error:(error as {code?:string})?.code||'VALIDATION_FAILED',allPages:false});}
  finally{if(generation===this.generation)this.emit({busy:false});}
 }
 async refresh(offset=0,memberOffset=0){if(this.subject)await this.request('get_validation',{query:{...this.subject,offset,member_offset:memberOffset}});}
 async validate(){if(this.subject)await this.request('run_validation',{subject:this.subject});}
 examine(){this.emit({reviewOpen:true,confirmed:false});}
 confirm(value:boolean){this.emit({confirmed:value&&this.state.reviewOpen&&this.state.allPages});}
 async accept(){
  const data=this.state.data;
  if(!this.subject||!this.state.reviewOpen||!this.state.confirmed||!this.state.allPages||!data?.handle||(data.state==='STALE'||!data.report?.counts.WARNING)||data.report?.warnings_accepted)return;
  await this.request('accept_validation_warnings',{subject:this.subject,handle:data.handle});
 }
 dispose(){this.generation++;this.subject=null;}
}
