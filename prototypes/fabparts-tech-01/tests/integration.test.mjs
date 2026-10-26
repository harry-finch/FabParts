import test from 'node:test';
import assert from 'node:assert/strict';
import {IntegrationController} from '../src/integration.ts';
const status=(patch={})=>({targets:[{id:'10.0',configuration:'/isolated/10.0'}],target:'10.0',latest:2,active:1,previous:null,state:'UPDATE_AVAILABLE',tables:[],operations:[],kicad_open:false,...patch});
const summary={handle:'opaque',version:2,target:'10.0',tables:['sym-lib-table','fp-lib-table']};
function setup(handler=async(action)=>action==='prepare'?summary:status()){
 const calls=[],states=[];const flow=new IntegrationController(async(command,args)=>{calls.push({command,args});return command==='restart_engine'?{}:handler(args.request.action,args.request);},s=>states.push(s));return{flow,calls,states};
}
test('activation requires a displayed summary and fresh explicit consent',async()=>{
 const {flow,calls}=setup();await flow.select('collection');await flow.apply();flow.confirm(true);await flow.apply();assert.equal(calls.length,1);await flow.prepare(2);await flow.apply();assert.equal(calls.length,2);flow.confirm(true);await flow.apply();assert.equal(calls.at(-1).args.request.action,'activate');assert.equal(flow.state.confirmed,false);assert.equal(flow.state.summary,null);
});
test('selecting another installation clears consent and summary',async()=>{
 const {flow}=setup();await flow.select('a');await flow.prepare(2);flow.confirm(true);await flow.choose('9.0');assert.equal(flow.state.confirmed,false);assert.equal(flow.state.summary,null);
});
test('lost activation reply reads durable state and never repeats the mutation',async()=>{
 let active=1;const {flow,calls}=setup(async(action)=>{if(action==='prepare')return summary;if(action==='activate'){active=2;throw{code:'TIMEOUT'};}return status({active,state:active===2?'CURRENT':'UPDATE_AVAILABLE'});});await flow.select('a');await flow.prepare(2);flow.confirm(true);await flow.apply();assert.equal(calls.filter(c=>c.args.request?.action==='activate').length,1);assert.equal(flow.state.data.active,2);assert.equal(flow.state.error,'TIMEOUT');assert.equal(flow.state.notice,'');await flow.apply();assert.equal(calls.filter(c=>c.args.request?.action==='activate').length,1);
});
test('interrupted two-table update exposes recovery rather than success',async()=>{
 const {flow}=setup(async(action)=>{if(action==='prepare')return summary;if(action==='activate')throw{code:'INTEGRATION_IO'};return status({state:'RECOVERY_REQUIRED'});});await flow.select('a');await flow.prepare(2);flow.confirm(true);await flow.apply();assert.equal(flow.state.data.state,'RECOVERY_REQUIRED');assert.equal(flow.state.notice,'');
});
test('recovery is separately reviewed and confirmed, never automatic',async()=>{
 const {flow,calls}=setup(async(action)=>action==='recovery'?{...summary,action:'restore_previous_tables'}:status({state:action==='recover'?'CURRENT':'RECOVERY_REQUIRED'}));await flow.select('a');await flow.prepareRecovery();await flow.apply();assert.equal(calls.filter(c=>c.args.request?.action==='recover').length,0);flow.confirm(true);await flow.apply();assert.equal(calls.at(-1).args.request.action,'recover');assert.equal(flow.state.data.state,'CURRENT');
});
test('external conflict remains visible after a failed apply',async()=>{
 const {flow}=setup(async(action)=>{if(action==='prepare')return summary;if(action==='activate')throw{code:'DOMAIN_ERROR',message:'TABLE_CHANGED: external edit'};return status({state:'INTERVENTION_REQUIRED'});});await flow.select('a');await flow.prepare(2);flow.confirm(true);await flow.apply();assert.equal(flow.state.message,'TABLE_CHANGED: external edit');assert.equal(flow.state.data.state,'INTERVENTION_REQUIRED');
});
test('verification errors clear earlier integrity evidence',async()=>{
 let fail=false;const {flow}=setup(async(action)=>{if(action==='verify'&&fail)throw{code:'DOMAIN_ERROR'};return status({verified:action==='verify'});});await flow.select('a');await flow.verify();assert.equal(flow.state.data.verified,true);fail=true;await flow.verify();assert.equal(flow.state.data.verified,false);assert.equal(flow.state.data.state,'ERROR');
});
test('double confirmation cannot enqueue another activation',async()=>{
 let done;const {flow,calls}=setup(async(action)=>action==='prepare'?summary:action==='activate'?new Promise(resolve=>done=resolve):status());await flow.select('a');await flow.prepare(2);flow.confirm(true);const one=flow.apply();await flow.apply();done(status({active:2,state:'CURRENT'}));await one;assert.equal(calls.filter(c=>c.args.request?.action==='activate').length,1);
});
test('reconnection only reads state and never activates implicitly',async()=>{
 const {flow,calls}=setup();await flow.select('a');await flow.reconnect();assert.equal(calls.at(-2).command,'restart_engine');assert.equal(calls.at(-1).args.request.action,'get');
});
test('disposed panels ignore late replies',async()=>{
 let done;const {flow,states}=setup(()=>new Promise(resolve=>done=resolve));const loading=flow.select('a');flow.dispose();const count=states.length;done(status());await loading;assert.equal(states.length,count);
});
test('missing installation and restore drift remain distinct',async()=>{
 const {flow}=setup(async()=>status({targets:[],target:'',active:null,state:'UNCONFIGURED'}));await flow.select('a');assert.equal(flow.state.data.state,'UNCONFIGURED');const other=setup(async()=>status({state:'RECONCILE_REQUIRED'}));await other.flow.select('a');assert.equal(other.flow.state.data.state,'RECONCILE_REQUIRED');assert.equal(other.calls.length,1);
});
