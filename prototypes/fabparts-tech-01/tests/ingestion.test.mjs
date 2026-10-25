import test from 'node:test';
import assert from 'node:assert/strict';
import {IngestionController,emptyFields} from '../src/ingestion.ts';

function setup(overrides={}){
  const calls=[],saved=[],states=[];
  let pending=null;
  const store={get:()=>pending,set:id=>pending=id,clear:()=>pending=null};
  const session={preparation:'a'.repeat(48),operation_id:'operation',part_id:'',fields:emptyFields(),selections:{},candidates:[],collections:[{id:'lab',name:'LabParts'},{id:'personal',name:'PersonalParts'}],packages:[],categories:[]};
  const responses={
    ingestion_begin:()=>structuredClone(session),
    ingestion_inspect:()=>({duplicates:[],package_selections:{},candidates:[]}),
    ingestion_search:()=>({candidates:[],notices:[]}),
    ingestion_commit:()=>({status:'saved',part_id:'part',operation_id:'operation'}),
    ingestion_result:()=>({status:'not_committed',operation_id:'operation'}),
    ingestion_cancel:()=>({cancelled:true}),
    choose_ingestion_files:()=>({cancelled:false,files:[],errors:[]}),
    restart_engine:()=>({read_only:false}),
    ...overrides,
  };
  const invoke=async(command,args)=>{
    const method=command==='ingestion_command'?args.request.method:command;
    const params=command==='ingestion_command'?args.request.params:args;
    calls.push([method,params]);
    if(!responses[method])throw Error('unexpected '+method);
    return responses[method](params);
  };
  const flow=new IngestionController(invoke,s=>states.push(s),async id=>{saved.push(id);},store);
  return {flow,calls,saved,states,store,session};
}
test('reference-only draft, library choice and actual receipt precede navigation',async()=>{
  const {flow,calls,saved,store}=setup();
  await flow.begin('','personal');
  assert.deepEqual(flow.state.fields.collections,['personal']);
  await flow.next();assert.equal(flow.state.error,'identity_required');
  flow.edit({reference:'Partial reference'});
  await flow.next();await flow.next();
  assert.equal(flow.state.step,2);
  await flow.commit();
  assert.deepEqual(saved,['part']);assert.equal(store.get(),null);
  const request=calls.find(([m])=>m==='ingestion_commit')[1];
  assert.equal(request.fields.mpn,'');assert.equal(request.fields.package_id,'');
});
test('no empty membership can be confirmed',async()=>{
  const {flow,calls}=setup();await flow.begin();flow.edit({reference:'A',collections:[]});
  await flow.commit();assert.equal(flow.state.error,'library_required');
  assert.ok(!calls.some(([m])=>m==='ingestion_commit'));
});
test('native file results are prepared, not automatically selected or saved',async()=>{
  const file={handle:'f',file:{original_name:'library.kicad_sym',extension:'.kicad_sym',size_bytes:14,sha256:'a'},symbols:['A','B']};
  const {flow,calls}=setup({choose_ingestion_files:()=>({cancelled:false,files:[file],errors:[]}),
    ingestion_search:({role})=>({candidates:role==='SYMBOL'?[{token:'candidate',role,name:'A',storage:'staged'}]:[],notices:[]})});
  await flow.begin();await flow.pick();
  assert.equal(flow.state.files[0].file.original_name,'library.kicad_sym');
  assert.deepEqual(flow.state.selections,{});
  assert.equal(flow.state.fields.reference,'');
  flow.choose('SYMBOL','candidate');
  assert.equal(flow.state.selections.SYMBOL,'candidate');
  assert.ok(!calls.some(([m])=>m==='ingestion_commit'));
});
test('picker cancellation and rejected file do not invent success',async()=>{
  const a=setup({choose_ingestion_files:()=>({cancelled:true,files:[],errors:[]})});
  await a.flow.begin();await a.flow.pick();assert.deepEqual(a.flow.state.files,[]);
  const b=setup({choose_ingestion_files:()=>({cancelled:false,files:[],errors:[{message:'File refused'}]})});
  await b.flow.begin();await b.flow.pick();assert.equal(b.flow.state.error,'File refused');
});
test('removing a preparation file clears its choice and candidates',async()=>{
  const {flow}=setup({ingestion_remove:()=>({removed:['candidate']})});
  await flow.begin();flow.state.files=[{handle:'file'}];flow.state.candidates=[{token:'candidate'}];
  flow.choose('SYMBOL','candidate');await flow.remove('file');
  assert.deepEqual(flow.state.files,[]);assert.deepEqual(flow.state.selections,{});
});
test('backend duplicates and membership request use the existing part',async()=>{
  const {flow,calls}=setup({ingestion_inspect:()=>({duplicates:[{id:'existing',name:'A'}],package_selections:{},candidates:[]})});
  await flow.begin();flow.edit({reference:'A',collections:['lab','personal']});await flow.next();
  assert.equal(flow.state.duplicates[0].id,'existing');
  await flow.commit('membership','existing');
  const params=calls.find(([m])=>m==='ingestion_commit')[1];
  assert.equal(params.action,'membership');assert.equal(params.existing_id,'existing');
  assert.deepEqual(params.fields.collections,['lab','personal']);
});
test('shared package selection comes from the engine and does not reuse a previous package token',async()=>{
  const {flow}=setup({ingestion_inspect:()=>({duplicates:[],package_selections:{FOOTPRINT:'shared'},candidates:[{token:'shared',role:'FOOTPRINT'}]})});
  await flow.begin();flow.choose('MODEL_3D','previous');flow.edit({package_id:'package'});await flow.inspect(true);
  assert.deepEqual(flow.state.selections,{FOOTPRINT:'shared'});
});
test('double confirmation in flight sends exactly one write',async()=>{
  let finish;const {flow,calls,saved}=setup({ingestion_commit:()=>new Promise(resolve=>finish=resolve)});
  await flow.begin();flow.edit({reference:'A'});
  const first=flow.commit();await flow.commit();
  assert.equal(calls.filter(([m])=>m==='ingestion_commit').length,1);assert.deepEqual(saved,[]);
  finish({status:'saved',part_id:'part'});await first;assert.deepEqual(saved,['part']);
});
test('lost commit response recovers receipt without repeating the write',async()=>{
  const {flow,calls,saved,store}=setup({ingestion_commit:()=>{throw {code:'TIMEOUT'};},
    ingestion_result:()=>({status:'saved',part_id:'part'})});
  await flow.begin();flow.edit({reference:'A'});await flow.commit();
  assert.deepEqual(saved,['part']);assert.equal(store.get(),null);
  assert.equal(calls.filter(([m])=>m==='ingestion_commit').length,1);
});
test('engine lost after confirmation keeps operation across restart and blocks blind retry',async()=>{
  let restarted=false;
  const {flow,calls,saved,store}=setup({ingestion_commit:()=>{throw Error('lost');},
    ingestion_result:()=>{if(!restarted)throw Error('stopped');return {status:'saved',part_id:'part'};},
    restart_engine:()=>{restarted=true;return {};}});
  await flow.begin();flow.edit({reference:'A'});await flow.commit();
  assert.equal(flow.state.recovery,true);assert.equal(store.get(),'operation');
  await flow.commit();assert.equal(calls.filter(([m])=>m==='ingestion_commit').length,1);
  assert.equal(await flow.cancel(),false);
  await flow.recover();assert.deepEqual(saved,['part']);assert.equal(store.get(),null);
});
test('rollback keeps form data and never navigates to a success view',async()=>{
  const {flow,saved,store}=setup({ingestion_commit:()=>{throw {message:'Storage full'};}});
  await flow.begin();flow.edit({reference:'Keep my draft'});await flow.commit();
  assert.equal(flow.state.error,'Storage full');assert.equal(flow.state.fields.reference,'Keep my draft');
  assert.deepEqual(saved,[]);assert.equal(store.get(),null);
});
test('resume loads persisted metadata and choices, stale search responses are discarded',async()=>{
  let finish;
  const {flow}=setup({
    ingestion_begin:()=>({preparation:'p',operation_id:'o',part_id:'part',fields:{...emptyFields(),reference:'Persisted',collections:['lab']},selections:{SYMBOL:'saved'},candidates:[{token:'saved',role:'SYMBOL'}],collections:[],packages:[],categories:[]}),
    ingestion_search:({query})=>query==='old'?new Promise(r=>finish=r):{candidates:[{token:'new',role:'SYMBOL'}],notices:[]},
  });
  await flow.begin('part');assert.equal(flow.state.fields.reference,'Persisted');
  const old=flow.search('SYMBOL','old');await flow.search('SYMBOL','new');
  finish({candidates:[{token:'old',role:'SYMBOL'}],notices:[]});await old;
  assert.deepEqual(flow.state.candidates.map(c=>c.token),['saved','new']);
});
test('cancel waits for backend cleanup before returning and disposal discards late begin',async()=>{
  const {flow,calls}=setup();await flow.begin();assert.equal(await flow.cancel(),true);
  assert.equal(calls.at(-1)[0],'ingestion_cancel');assert.equal(flow.state.session,null);
  let finish;const late=setup({ingestion_begin:()=>new Promise(r=>finish=r)});
  const begin=late.flow.begin();late.flow.dispose();finish(late.session);await begin;
  assert.equal(late.flow.state.session,null);
});
test('local index notices remain visible after other role searches',async()=>{
  const {flow}=setup({ingestion_search:({role})=>({candidates:[],notices:role==='SYMBOL'?['Local index missing']:[]})});
  await flow.begin();await flow.search('SYMBOL');await flow.search('DATASHEET');await flow.search('SYMBOL');
  assert.deepEqual(flow.state.notices,['Local index missing']);
});
