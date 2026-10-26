import { visibleTimeout } from '../src/pdf_render.ts';
import test from 'node:test';
import assert from 'node:assert/strict';
import { PreviewController, fittedBounds, viewBox, zoomed, layerGroup, paintOrder } from '../src/preview.ts';
const drawing={status:'ready',kind:'SYMBOL',drawings:[{name:'Real',primitives:[]}]};
const pdf={status:'ready',kind:'DATASHEET',handle:'a'.repeat(48),size_bytes:3,chunk_bytes:65536};
function setup(invoke){const states=[];return {states,controller:new PreviewController(invoke,s=>states.push(s))};}
test('real neutral result, loading and failure states stay distinct',async()=>{
 for(const status of ['ready','absent','missing','inaccessible','unsupported','error','too_large']){const {states,controller}=setup(async()=>({...drawing,status}));await controller.load('id','SYMBOL');assert.equal(states[0].status,'loading');assert.equal(states.at(-1).status,status);}
});
test('new selection wins and old PDF handle is released',async()=>{
 let release;const calls=[];const {states,controller}=setup(async(cmd,args)=>{calls.push(cmd);if(cmd==='get_asset_preview')return args.query.id==='slow'?new Promise(r=>release=r):drawing;});
 const old=controller.load('slow','DATASHEET');await controller.load('new','SYMBOL');release(pdf);await old;assert.equal(states.at(-1).kind,'SYMBOL');assert.ok(calls.includes('release_preview'));assert.ok(!calls.includes('read_pdf_chunk'));
});
test('bounded PDF transport assembles bytes and releases snapshot',async()=>{
 const calls=[];const {states,controller}=setup(async(cmd,args)=>{calls.push([cmd,args]);return cmd==='get_asset_preview'?pdf:cmd==='read_pdf_chunk'?{offset:0,data:'YWJj',eof:true}:{};});await controller.load('id','DATASHEET');assert.equal(new TextDecoder().decode(states.at(-1).bytes),'abc');assert.equal(calls.at(-1)[0],'release_preview');
});
test('cancellation during chunk read cannot publish stale PDF',async()=>{
 let release;const calls=[];const {states,controller}=setup(async(cmd)=>{calls.push(cmd);return cmd==='get_asset_preview'?pdf:cmd==='read_pdf_chunk'?new Promise(r=>release=r):{};});const pending=controller.load('id','DATASHEET');await new Promise(r=>setTimeout(r,0));controller.dispose();release({offset:0,data:'YWJj',eof:true});await pending;assert.equal(states.at(-1).status,'loading');assert.equal(calls.at(-1),'release_preview');
});
test('oversized PDF and corrupt chunks fail with cleanup',async()=>{
 for(const result of [{...pdf,size_bytes:17000000},pdf]){const calls=[];const {states,controller}=setup(async(cmd)=>{calls.push(cmd);return cmd==='get_asset_preview'?result:cmd==='read_pdf_chunk'?{offset:0,data:'YQ==',eof:true}:{};});await controller.load('id','DATASHEET');assert.equal(states.at(-1).status,'error');assert.equal(calls.at(-1),'release_preview');}
});
test('zoom preserves centre, bounds scale; copper toggles pads/drills/labels',()=>{assert.equal(viewBox([-10,-5,20,10],2),'-5 -2.5 10 5');assert.equal(zoomed(8,2),8);assert.equal(zoomed(.5,.1),.5);assert.equal(layerGroup('PadLabel'),'F.Cu');assert.equal(layerGroup('F.SilkS'),'F.SilkS');});
test('SVG renders supplied 48 pads, geometry and escaped text',async()=>{
 const {createServer}=await import('vite');const server=await createServer({server:{middlewareMode:true,hmr:false,ws:false},appType:'custom'});
 try {const {default:View}=await server.ssrLoadModule('/src/DrawingView.svelte');const {render}=await server.ssrLoadModule('svelte/server');const primitives=Array.from({length:48},(_,i)=>({kind:'pad_rect',points:[[i,0],[1,2]],layer:i===0?'Pad1':'Pads',text:'',width:.1,filled:true,angle:90,size:.25}));primitives.push({kind:'text',points:[[0,4]],layer:'Pins',text:'<script>bad</script>',width:0,filled:false,angle:0,size:1});const {body}=render(View,{props:{drawings:[{name:'QFP48',unit:1,style:1,bounds:[-2,-2,52,8],units:'mm',warnings:[],primitives}]}});assert.equal((body.match(/<rect /g)||[]).length,48);assert.match(body,/rotate\(90\)/);assert.ok(body.includes('&lt;script>'));assert.ok(!body.includes('<script>bad'));}finally{await server.close();}
});

test('common-unit power pins paint above a later body fill',()=>{
const pin={kind:'text',layer:'Pins'}, body={kind:'rect',layer:'Body'}, drill={kind:'pad_oval',layer:'Drill'},pad={kind:'pad_rect',layer:'Pads'};
assert.deepEqual(paintOrder([pin,drill,body,pad]),[body,pad,drill,pin]);
});


test('PDF render deadline counts visible time and cleans up on cancellation', t=>{
 t.mock.timers.enable({apis:['setTimeout','Date'],now:0});
 const visibility=new EventTarget();visibility.hidden=false;
 let calls=0;
 visibleTimeout(()=>calls++,10000,visibility);
 t.mock.timers.tick(2000);visibility.hidden=true;visibility.dispatchEvent(new Event('visibilitychange'));
 t.mock.timers.tick(60000);assert.equal(calls,0);
 visibility.hidden=false;visibility.dispatchEvent(new Event('visibilitychange'));
 t.mock.timers.tick(7999);assert.equal(calls,0);t.mock.timers.tick(1);assert.equal(calls,1);
 const cancel=visibleTimeout(()=>calls++,10000,visibility);cancel();
 t.mock.timers.tick(10000);assert.equal(calls,1);
});

test('visible bounds fit tiny, large and elongated units with proportional margin',()=>{
 for(const scale of [.0001,1,100000]) {
  const box=fittedBounds({x:2*scale,y:-scale,width:10*scale,height:2*scale},.1*scale);
  assert.ok(box[0]<2*scale && box[1]<-scale);
  assert.ok(box[0]+box[2]>12*scale && box[1]+box[3]>scale);
  assert.ok(Math.abs(box[2]/scale-11.7)<1e-8);
 }
 assert.equal(fittedBounds({x:0,y:0,width:0,height:0}),null);
 assert.equal(fittedBounds({x:NaN,y:0,width:1,height:1}),null);
 assert.ok(fittedBounds({x:0,y:0,width:0,height:10})[2]>0);
});
