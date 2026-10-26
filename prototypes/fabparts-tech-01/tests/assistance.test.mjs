import test from 'node:test';
import assert from 'node:assert/strict';
import {AssistanceController} from '../src/assistance.ts';
const deferred=()=>{let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve};};
const prepared={handle:'a'.repeat(48),payload:'{"context":"exact","identification":{}}',backend:'ollama',model:'fixture',destination:'http://127.0.0.1:11434/api/chat',sha256:'sha',revision:0};
const rows=[{field:'mpn',current:'OLD',proposed:'SUGGESTED',conflict:true},{field:'category',current:'',proposed:'Fixture',conflict:false}];
function setup(overrides={},delay=async()=>{}){
 const calls=[],states=[],saved=[];
 const responses={assistance_configuration:()=>({enabled:true,availability:'configured'}),assistance_identification:()=>({revision:0,values:{},history:[]}),assistance_prepare:()=>prepared,assistance_start:()=>({status:'loading'}),assistance_status:()=>({status:'ready',rows}),assistance_cancel:()=>({cancelled:true}),assistance_accept:()=>({revision:1,values:{category:'Fixture'},history:[]}),...overrides};
 const invoke=async(command,{request})=>{assert.equal(command,'assistance_command');calls.push(request);assert.ok(responses[request.method]);return responses[request.method](request.params);};
 return {flow:new AssistanceController(invoke,'part',s=>states.push(s),()=>{saved.push(true);},delay),calls,states,saved};
}
test('opening AI section reads local config/profile only; no inference or consent',async()=>{
 const f=setup();await f.flow.load();assert.deepEqual(f.calls.map(c=>c.method),['assistance_configuration','assistance_identification']);assert.equal(f.flow.state.include,false);assert.equal(f.flow.state.consent,false);await f.flow.start();assert.equal(f.calls.length,2);
});
test('prepare displays exact server JSON; each edit immediately invalidates consent and proposal',async()=>{
 const f=setup();f.flow.edit('exact',false);await f.flow.prepare();assert.equal(f.flow.state.prepared.payload,prepared.payload);f.flow.authorize(true);f.flow.edit('changed',true);assert.equal(f.flow.state.prepared,null);assert.equal(f.flow.state.consent,false);await f.flow.start();assert.ok(!f.calls.some(c=>c.method==='assistance_start'));assert.ok(f.calls.some(c=>c.method==='assistance_cancel'));
});
test('suggestions begin unchecked; acceptance sends only selected field and opaque session',async()=>{
 const f=setup();f.flow.edit('exact',false);await f.flow.prepare();f.flow.authorize(true);await f.flow.start();assert.deepEqual(f.flow.state.selected,[]);assert.equal(f.flow.state.replace,false);assert.equal(f.flow.state.consent,false);await f.flow.accept();assert.deepEqual(f.saved,[]);f.flow.select('category',true);await f.flow.accept();const sent=f.calls.find(c=>c.method==='assistance_accept').params;assert.deepEqual(sent,{id:'part',handle:prepared.handle,fields:['category'],replace_existing:false});assert.equal(f.saved.length,1);assert.equal(f.flow.state.text,'');
});
test('replacement confirmation resets when the set of accepted fields changes',async()=>{
 const f=setup();await f.flow.prepare();f.flow.authorize(true);await f.flow.start();f.flow.select('mpn',true);f.flow.replace(true);f.flow.select('category',true);assert.equal(f.flow.state.replace,false);
});
test('late result after cancellation or component disposal cannot be used',async()=>{
 const wait=deferred(),f=setup({assistance_status:()=>wait.promise});await f.flow.prepare();f.flow.authorize(true);const running=f.flow.start();await Promise.resolve();await Promise.resolve();f.flow.dispose();wait.resolve({status:'ready',rows});await running;assert.deepEqual(f.flow.state.rows,[]);assert.equal(f.flow.state.prepared,null);assert.equal(f.saved.length,0);
});
test('editing context while prepare is pending revokes the eventual handle',async()=>{
 const wait=deferred(),f=setup({assistance_prepare:()=>wait.promise});const running=f.flow.prepare();f.flow.edit('new context',false);wait.resolve(prepared);await running;assert.equal(f.flow.state.prepared,null);assert.ok(f.calls.some(c=>c.method==='assistance_cancel'));
});
test('provider error never retries or saves; new authorization is required',async()=>{
 const f=setup({assistance_status:()=>({status:'error',rows:[]})});await f.flow.prepare();f.flow.authorize(true);await f.flow.start();assert.equal(f.flow.state.error,'analysis_failed');assert.equal(f.flow.state.pending,false);assert.equal(f.flow.state.consent,false);assert.equal(f.saved.length,0);assert.equal(f.calls.filter(c=>c.method==='assistance_start').length,1);
});
test('revision error before acceptance keeps local saved state and exposes no false success',async()=>{
 const f=setup({assistance_accept:()=>{throw Error('Context changed');}});await f.flow.prepare();f.flow.authorize(true);await f.flow.start();f.flow.select('category',true);await f.flow.accept();assert.equal(f.saved.length,0);assert.equal(f.flow.state.message,'');assert.equal(f.flow.state.error,'Context changed');
});

test('safe diagnostics survive the job boundary; edits clear them and never retry',async()=>{
 const f=setup({assistance_status:()=>({status:'error',rows:[],error:{code:'authentication',http_status:401}})});
 await f.flow.prepare();f.flow.authorize(true);await f.flow.start();
 assert.deepEqual(f.flow.state.diagnostic,{code:'authentication',http_status:401});
 assert.equal(f.flow.state.error,'analysis_failed');assert.equal(f.saved.length,0);
 f.flow.edit('changed',false);assert.equal(f.flow.state.diagnostic,null);
 assert.equal(f.calls.filter(c=>c.method==='assistance_start').length,1);
});

test('diagnostics are translated, actionable and never reflect unknown provider text',async()=>{
 const {assistanceError}=await import('../src/assistance-errors.ts');
 for(const [code,fr,en] of [['authentication','Authentification','Authentication'],['no_suggestions','sans suggestion','without usable'],['incomplete','limite de sortie','output limit'],['timeout','délai','time limit']]){
  assert.ok(assistanceError({code,http_status:null},'fr').includes(fr));
  assert.ok(assistanceError({code,http_status:null},'en').includes(en));
 }
 assert.ok(assistanceError({code:'authentication',http_status:401},'fr').includes('HTTP 401'));
 assert.ok(!assistanceError({code:'provider-secret',http_status:'secret'},'fr').includes('secret'));
 assert.ok(!assistanceError({code:'__proto__',http_status:null},'en').includes('__proto__'));
});
