import test from 'node:test';
import assert from 'node:assert/strict';
import { Controller, defaultQuery } from '../src/controller.ts';
// Test-only transport values: never imported by the application bundle.
const component = {id:'part-1',reference:'NE555',manufacturer:'',mpn:'',description:'Timer',category:'',package:null,libraries:[],state:'DRAFT'};
const page = {components:[component],total:1,offset:0,limit:50,facets:{categories:[],packages:[]}};
const health = {status:'ready',engine_version:'0.1.0',protocol_version:1,read_only:true,qt_loaded:false,pid:123,schema:'0007_asset_provenance'};
const detail = {...component,associated_assets:[],selections:[],documents:[],qualification:null,preview_available:false};
function setup(overrides = {}) {
  const calls=[];
  const invoke=async (command,args) => {
    calls.push([command,args]);
    if(overrides[command]) return overrides[command](args);
    return {restart_engine:health,health,list_libraries:[{id:'collection-1',name:'Workshop',count:1}],list_components:page,get_component:detail}[command];
  };
  const states=[];
  return {controller:new Controller(invoke,s=>states.push(s)),calls,states};
}
test('initial load reads libraries, list and selected detail in order', async () => {
  const {controller,calls,states}=setup();
  await controller.start();
  assert.deepEqual(calls.map(c=>c[0]),['restart_engine','list_libraries','list_components','get_component']);
  assert.equal(controller.state.phase,'ready');
  assert.equal(controller.state.libraries[0].name,'Workshop');
  assert.equal(controller.state.detail.reference,'NE555');
  assert.ok(states.some(s=>s.phase==='starting'));
  assert.ok(states.some(s=>s.loading));
});
test('search, filters and pagination reach the engine unchanged', async () => {
  const {controller,calls}=setup(); await controller.start();
  const query={...defaultQuery(),search:'NE555',library:'collection-1',category:'Timer',package:'DIP8',state:'DRAFT',offset:50};
  await controller.load(query);
  assert.deepEqual(calls.findLast(c=>c[0]==='list_components')[1],{query});
});
test('empty list clears selection and does not request a fake detail', async () => {
  const {controller,calls}=setup({list_components:()=>({...page,components:[],total:0})});
  await controller.start(); assert.equal(controller.state.detail,null); assert.equal(controller.state.page.total,0);
  assert.ok(!calls.some(c=>c[0]==='get_component'));
});
test('launch failure is explicit and never falls back to demo', async () => {
  const {controller,calls}=setup({restart_engine:()=>{throw {code:'LAUNCH_FAILED',message:'Absent'};}});
  await controller.start(); assert.equal(controller.state.phase,'failed'); assert.equal(controller.state.page.components.length,0);
  assert.equal(controller.state.error.code,'LAUNCH_FAILED'); assert.equal(calls.length,1);
});
test('crash during idle health clears stale catalogue and can restart', async () => {
  let crash=true;
  const {controller}=setup({health:()=>{if(crash) throw {code:'ENGINE_EXITED',message:'Stopped'}; return health;}});
  await controller.start(); await controller.heartbeat(); assert.equal(controller.state.phase,'failed'); assert.equal(controller.state.detail,null);
  crash=false; await controller.start(); assert.equal(controller.state.phase,'ready');
});
test('timeout in detail is explicit', async () => {
  const {controller}=setup({get_component:()=>{throw {code:'TIMEOUT',message:'Timeout'};}});
  await controller.start(); assert.equal(controller.state.phase,'failed'); assert.equal(controller.state.error.code,'TIMEOUT');
});
test('late selection never replaces newer detail', async () => {
  let release;
  const {controller}=setup({get_component:({id})=>id==='slow' ? new Promise(r=>release=r) : {...detail,id}});
  await controller.start(); const old=controller.select('slow'); await controller.select('new'); release({...detail,id:'slow'}); await old;
  assert.equal(controller.state.detail.id,'new');
});
test('late search results never replace the current list', async () => {
  let release;
  const {controller}=setup({list_components:({query})=>query.search==='slow' ? new Promise(r=>release=r) : page});
  await controller.start(); const old=controller.load({...defaultQuery(),search:'slow'}); await controller.load(defaultQuery());
  release({...page,components:[],total:0}); await old; assert.equal(controller.state.page.total,1);
});
test('resources absent remains a genuine empty detail', async () => {
  const {controller}=setup(); await controller.start(); assert.deepEqual(controller.state.detail.associated_assets,[]);
  assert.equal(controller.state.detail.qualification,null); assert.equal(controller.state.detail.preview_available,false);
});
test('disposing during startup prevents subsequent catalogue calls', async () => {
  let release;
  const {controller,calls}=setup({restart_engine:()=>new Promise(resolve=>release=resolve)});
  const pending=controller.start(); controller.dispose(); release(health); await pending;
  assert.deepEqual(calls.map(c=>c[0]),['restart_engine']);
});
test('late startup error cannot replace a successfully restarted session', async () => {
  let reject, first=true;
  const {controller}=setup({restart_engine:()=>{ if(first){first=false;return new Promise((_,r)=>reject=r);} return health; }});
  const old=controller.start(); await controller.start(); reject({code:'TIMEOUT',message:'Old'}); await old;
  assert.equal(controller.state.phase,'ready'); assert.equal(controller.state.detail.reference,'NE555');
});
test('idle health probes do not accumulate while the engine is slow', async () => {
  let release;
  const {controller,calls}=setup({health:()=>new Promise(resolve=>release=resolve)});
  await controller.start(); const pending=controller.heartbeat(); await controller.heartbeat();
  assert.equal(calls.filter(c=>c[0]==='health').length,1);
  release(health); await pending; assert.equal(controller.state.phase,'ready');
});
