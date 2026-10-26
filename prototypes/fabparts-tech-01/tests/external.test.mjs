import test from 'node:test';
import assert from 'node:assert/strict';
import {ExternalController} from '../src/external.ts';
import {IngestionController} from '../src/ingestion.ts';
const deferred=()=>{let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve};};
function setup(responses={},delay=async()=>{}){
 const calls=[],results=[],errors=[],pending=[];
 const invoke=async(command,{request})=>{assert.equal(command,'external_command');calls.push(request);return responses[request.method]?.(request.params);};
 return {controller:new ExternalController(invoke,'a'.repeat(48),v=>results.push(v),v=>pending.push(v),v=>errors.push(v),delay),calls,results,errors,pending};
}
test('external controller does no network on construction and polls bounded jobs explicitly',async()=>{
 let polls=0;
 const f=setup({external_search:()=>({handle:'b'.repeat(48)}),external_status:()=>++polls===1?{status:'loading'}:{status:'ready',candidates:[{token:'opaque',commit:'pinned',revision:'9.0.0'}]}});
 assert.deepEqual(f.calls,[]);
 await f.controller.start('external_search',{role:'SYMBOL',library:'Timer',query:'NE555D'});
 assert.equal(polls,2);assert.equal(f.results[0].candidates[0].commit,'pinned');
 assert.equal(f.calls[0].params.preparation,'a'.repeat(48));
 assert.deepEqual(f.pending,[true,false]);
 assert.ok(!f.calls.some(c=>c.method==='external_download'));
});
test('cancel pending start revokes the eventual handle and ignores stale result',async()=>{
 const waiting=deferred();const f=setup({external_search:()=>waiting.promise,external_cancel:()=>({cancelled:true})});
 const running=f.controller.start('external_search',{});f.controller.cancel();waiting.resolve({handle:'b'.repeat(48)});await running;
 assert.equal(f.calls.at(-1).method,'external_cancel');assert.deepEqual(f.results,[]);
});
test('cancel while polling ignores a delayed completed download',async()=>{
 const waiting=deferred();const f=setup({external_download:()=>({handle:'b'.repeat(48)}),external_status:()=>waiting.promise,external_cancel:()=>({cancelled:true})});
 const running=f.controller.start('external_download',{token:'opaque'});
 await Promise.resolve();await Promise.resolve();f.controller.cancel();waiting.resolve({status:'ready',file:{},candidate:{}});await running;
 assert.deepEqual(f.results,[]);assert.equal(f.pending.at(-1),false);
});
test('network error leaves UI available and never retries a download',async()=>{
 const f=setup({external_pdf:()=>({handle:'b'.repeat(48)}),external_status:()=>({status:'error',message:'offline'})});
 await f.controller.start('external_pdf',{url:'https://www.ti.com/r.pdf',consent:true});
 assert.equal(f.errors.at(-1),'offline');assert.equal(f.pending.at(-1),false);assert.deepEqual(f.results,[]);
 assert.equal(f.calls.filter(c=>c.method==='external_pdf').length,1);
});
test('downloaded resource is only prepared and previewed, existing selection is preserved',()=>{
 const flow=new IngestionController(async()=>{throw Error('No canonical write expected');},()=>{},()=>{},{get:()=>null,set:()=>{},clear:()=>{}});
 flow.state.selections={SYMBOL:'local-choice'};
 flow.addExternal({file:{handle:'file'},candidate:{token:'remote',role:'SYMBOL',origin:'KICAD_OFFICIAL',storage:'staged'}});
 assert.equal(flow.state.selections.SYMBOL,'local-choice');assert.equal(flow.state.previewing.SYMBOL,'remote');assert.equal(flow.state.files.length,1);
});
