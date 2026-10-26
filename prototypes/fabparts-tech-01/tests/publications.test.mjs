import test from 'node:test';
import assert from 'node:assert/strict';
import {PublicationController} from '../src/publications.ts';
const history={scope:'workspace',id:'collection',name:'LabParts',count:1,state:'PASS',eligible:true,proposed:1,reserved_count:0,total:0,offset:0,versions:[]};
const summary={name:'LabParts',count:1,fingerprint:'a'.repeat(64),version:1,handle:'opaque',parts:[],offset:0};
function setup(handler=async()=>({})){
 const calls=[],states=[];let pending=null;
 const recovery={get:()=>pending,set:v=>{pending=v;},clear:()=>{pending=null;}};
 const flow=new PublicationController(async(cmd,args)=>{calls.push({cmd,args});if(cmd==='publication_query'&&args.query.action==='history')return history;if(cmd==='publication_query'&&args.query.action==='prepare')return summary;return handler(cmd,args);},recovery,s=>states.push(s));
 return {flow,calls,states,recovery};
}
test('publishing requires a fresh explicit confirmation and durable engagement',async()=>{
 const {flow,calls}=setup(async()=>({status:'COMMITTED',fingerprint:summary.fingerprint}));await flow.select('collection');await flow.publish();await flow.prepare();await flow.publish();assert.equal(calls.filter(c=>c.cmd==='publish_version').length,0);
 flow.confirm(true);await flow.publish();assert.equal(calls.filter(c=>c.cmd==='publish_version').length,1);assert.equal(calls.at(-2).args.query.action,'status');assert.equal(flow.state.notice,'committed');assert.equal(flow.state.confirmed,false);
});
test('lost reply after COMMIT is reconciled without a second mutation',async()=>{
 const {flow,calls,recovery}=setup(async(cmd)=>{if(cmd==='publish_version')throw{code:'TIMEOUT'};return{status:'COMMITTED',fingerprint:summary.fingerprint};});await flow.select('collection');await flow.prepare();flow.confirm(true);await flow.publish();await flow.publish();assert.equal(flow.state.notice,'committed');assert.equal(recovery.get(),null);assert.equal(calls.filter(c=>c.cmd==='publish_version').length,1);
});
test('unknown engagement persists across reopening and blocks any retry',async()=>{
 const {flow,calls,recovery}=setup(async()=>{throw{code:'ENGINE_UNAVAILABLE'};});await flow.select('collection');await flow.prepare();flow.confirm(true);await flow.publish();assert.ok(recovery.get());assert.equal(flow.state.notice,'');assert.equal(flow.state.error,'ENGINE_UNAVAILABLE');await flow.prepare();await flow.publish();assert.equal(calls.filter(c=>c.cmd==='publish_version').length,1);
});
test('reconnect consults durable status and never resends publish',async()=>{
 let failed=true;const {flow,calls,recovery}=setup(async(cmd)=>{if(cmd==='publish_version'||(cmd==='publication_query'&&failed))throw{code:'TIMEOUT'};return{status:'COMMITTED',fingerprint:summary.fingerprint};});await flow.select('collection');await flow.prepare();flow.confirm(true);await flow.publish();assert.ok(recovery.get());failed=false;await flow.recover();assert.equal(recovery.get(),null);assert.equal(flow.state.notice,'committed');assert.equal(calls.filter(c=>c.cmd==='publish_version').length,1);
});
for(const status of ['ABSENT','RESERVED'])test(`${status} is never announced as a successful publication`,async()=>{
 const {flow}=setup(async()=>({status}));await flow.select('collection');await flow.prepare();flow.confirm(true);await flow.publish();assert.equal(flow.state.notice,status.toLowerCase());assert.equal(flow.state.summary,null);
});
test('a conflicting fingerprint retains the unresolved request',async()=>{
 const {flow,recovery}=setup(async()=>({status:'COMMITTED',fingerprint:'different'}));await flow.select('collection');await flow.prepare();flow.confirm(true);await flow.publish();assert.ok(recovery.get());assert.equal(flow.state.error,'VERSION_CONFLICT');assert.equal(flow.state.notice,'');
});
test('double clicks send one mutation',async()=>{
 let done;const {flow,calls}=setup(async(cmd)=>cmd==='publish_version'?new Promise(resolve=>done=resolve):{status:'COMMITTED',fingerprint:summary.fingerprint});await flow.select('collection');await flow.prepare();flow.confirm(true);const first=flow.publish();await flow.publish();done({});await first;assert.equal(calls.filter(c=>c.cmd==='publish_version').length,1);
});
test('verification failure never retains PASS, and refresh discards stale checks',async()=>{
 let fail=false;const {flow}=setup(async()=>{if(fail)throw{code:'DOMAIN_ERROR'};return{};});await flow.select('collection');await flow.verify(1);assert.equal(flow.state.checks[1],'PASS');fail=true;await flow.verify(1);assert.equal(flow.state.checks[1],'FAILED');await flow.refresh();assert.deepEqual(flow.state.checks,{});
});
test('a new summary resets confirmation; disposed views ignore late responses',async()=>{
 const {flow,states}=setup();await flow.select('collection');await flow.prepare();flow.confirm(true);await flow.prepare();assert.equal(flow.state.confirmed,false);flow.dispose();const count=states.length;await flow.refresh();assert.equal(states.length,count);
});

test('a readonly copy or different workspace cannot clear another workspace pending publication',async()=>{
 const {flow,recovery}=setup();await flow.select('collection');recovery.set({scope:'other-workspace',id:'collection',version:1,fingerprint:summary.fingerprint});await flow.recover();assert.equal(flow.state.error,'WORKSPACE_MISMATCH');assert.ok(recovery.get());assert.equal(flow.state.notice,'');
});

test('a builder refusal remains actionable after confirming no COMMIT exists',async()=>{
 const {flow,recovery}=setup(async(cmd)=>{if(cmd==='publish_version')throw{code:'DOMAIN_ERROR',message:'Unresolved 3D link'};return{status:'ABSENT'};});await flow.select('collection');await flow.prepare();flow.confirm(true);await flow.publish();assert.equal(flow.state.error,'DOMAIN_ERROR');assert.equal(flow.state.errorMessage,'Unresolved 3D link');assert.equal(flow.state.notice,'absent');assert.equal(recovery.get(),null);
});

test('publication counts use singular and plural in both locales',async()=>{
 const {createServer}=await import('vite');const server=await createServer({server:{middlewareMode:true,hmr:false,ws:false},appType:'custom'});
 try {
  const {publicationCount}=await server.ssrLoadModule('/src/publication_text.ts');
  const {i18n}=await server.ssrLoadModule('../fabparts-ux/src/lib/i18n.svelte.ts');
  for(const locale of ['fr','en']) {
   i18n.locale=locale;
   assert.equal(publicationCount(1,'component'),locale==='fr'?'1 composant':'1 component');
   assert.equal(publicationCount(2,'component'),locale==='fr'?'2 composants':'2 components');
   assert.equal(publicationCount(1,'version'),'1 version');
   assert.equal(publicationCount(0,'version'),'0 versions');
  }
 } finally {await server.close();}
});
