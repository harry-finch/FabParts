import test from 'node:test';
import assert from 'node:assert/strict';
import {decodeMesh,verifyMeshHash} from '../src/mesh.ts';
import {PreviewController} from '../src/preview.ts';
import {geometryFor,ModelScene,fitDistance,directions} from '../src/model_scene.ts';
function fixture(){
 const bytes=new Uint8Array(109),d=new DataView(bytes.buffer);d.setUint32(0,0x46504d31);d.setUint32(4,3,true);d.setUint32(8,1,true);
 [7,-7,2,17,-7,2,7,-1,4].forEach((v,i)=>d.setFloat64(12+i*8,v,true));
 [0,1,2].forEach((v,i)=>d.setUint32(84+i*4,v,true));[.2,.4,.6].forEach((v,i)=>d.setFloat32(96+i*4,v,true));
 return bytes;
}
const meta={vertices:3,triangles:1,units:'mm',warnings:[]};
const digest=async bytes=>Buffer.from(await crypto.subtle.digest('SHA-256',bytes)).toString('hex');
test('FPM1 checks shape, positions, indices, materials and digest before GPU allocation',async()=>{
 const b=fixture(),mesh=decodeMesh(b,meta);assert.deepEqual(mesh.bounds,[[7,-7,2],[17,-1,4]]);await verifyMeshHash(b,await digest(b));
 await assert.rejects(verifyMeshHash(b,'a'.repeat(64)));
 for(const offset of [0,4,8,12,84,96,108]){const bad=b.slice();bad.fill(255,offset,offset+(offset===108?1:offset===12?8:4));assert.throws(()=>decodeMesh(bad,meta));}
 assert.throws(()=>decodeMesh(b.slice(1),meta));
});
test('job polling, verified chunk retrieval and release preserve actual source metadata',async()=>{
 const b=fixture(),states=[],calls=[];let polls=0;
 const controller=new PreviewController(async(cmd,args)=>{calls.push(cmd);if(cmd==='get_asset_preview')return {kind:'MODEL_3D',status:'loading',handle:'a'.repeat(48),name:'box.step',source:'original'};
 if(cmd==='get_model_status')return ++polls===1?{status:'loading'}:{status:'ready',...meta,size_bytes:b.length,chunk_bytes:65536,mesh_sha256:await digest(b)};
 if(cmd==='read_mesh_chunk')return {offset:0,data:Buffer.from(b).toString('base64'),eof:true};return {released:true};},v=>states.push(v));
 await controller.load('id','MODEL_3D');assert.equal(states.at(-1).name,'box.step');assert.ok(states.at(-1).mesh);assert.equal(calls.at(-1),'release_model_preview');assert.equal(polls,2);
});
test('navigation cancels a pending model and never publishes its late result',async()=>{
 const calls=[],states=[];let done;
 const controller=new PreviewController(async(cmd)=>{calls.push(cmd);if(cmd==='get_asset_preview')return {status:'loading',handle:'b'.repeat(48)};if(cmd==='get_model_status')return new Promise(r=>done=r);return {released:true};},v=>states.push(v));
 const pending=controller.load('id','MODEL_3D');await new Promise(r=>setTimeout(r,180));controller.dispose();assert.ok(calls.includes('release_model_preview'));done({status:'ready'});await pending;assert.equal(states.at(-1).status,'loading');assert.ok(!calls.includes('read_mesh_chunk'));
});
test('converter unavailable and failed conversions remain explicit and release handles',async()=>{
 for(const status of ['converter_missing','unsupported','too_large','error','cancelled']){
  const states=[],calls=[];const c=new PreviewController(async cmd=>{calls.push(cmd);return cmd==='get_asset_preview'?{status:'loading',handle:'a'.repeat(48)}:{status,message:'detail'};},v=>states.push(v));
  await c.load('id','MODEL_3D');assert.equal(states.at(-1).status,status);assert.equal(calls.at(-1),'release_model_preview');
 }
});
test('off-origin geometry is centered, winding kept, bounding sphere fits narrow views',()=>{
 const g=geometryFor(decodeMesh(fixture(),meta));assert.deepEqual(Array.from(g.getAttribute('position').array),[-5,-3,-1,5,-3,-1,-5,3,1]);
 assert.ok(g.getAttribute('normal').array.every(Number.isFinite));assert.equal(g.groups.length,1);
 assert.ok(fitDistance(6,.5)>fitDistance(6,2));g.dispose();assert.deepEqual(directions.front,[0,-1,0]);
});
function canvas(){const c=new EventTarget();c.style={};c.ownerDocument=new EventTarget();c.getRootNode=()=>c.ownerDocument;c.clientWidth=600;c.clientHeight=400;c.setPointerCapture=()=>{};c.releasePointerCapture=()=>{};c.getBoundingClientRect=()=>({left:0,top:0,width:600,height:400});return c;}
function event(type,props){const e=new Event(type,{cancelable:true});Object.assign(e,props);return e;}
test('actual OrbitControls rotate, zoom, pan; views, visibility, context loss and disposal',()=>{
 let scheduled=new Map(),seq=0,renders=0,disposed=0;globalThis.requestAnimationFrame=fn=>{scheduled.set(++seq,fn);return seq;};globalThis.cancelAnimationFrame=id=>scheduled.delete(id);globalThis.devicePixelRatio=3;
 const c=canvas(),renderer={setPixelRatio:n=>assert.equal(n,2),setSize(){},setClearColor(){},render(){renders++},dispose(){disposed++},forceContextLoss(){disposed++}};
 const state=[],s=new ModelScene(c,decodeMesh(fixture(),meta),lost=>state.push(lost),()=>renderer);
 const flush=()=>{const f=[...scheduled.values()];scheduled.clear();f.forEach(fn=>fn());};
 s.resize(600,400);s.standard('iso');flush();assert.equal(renders,1);flush();assert.equal(renders,1);
 const before=s.camera.position.clone();
 c.dispatchEvent(event('pointerdown',{pointerId:1,pointerType:'mouse',button:0,clientX:200,clientY:200}));
 c.ownerDocument.dispatchEvent(event('pointermove',{pointerId:1,pointerType:'mouse',clientX:280,clientY:240}));c.ownerDocument.dispatchEvent(event('pointerup',{pointerId:1,pointerType:'mouse'}));assert.ok(s.camera.position.distanceTo(before)>.1);
 const dist=s.camera.position.distanceTo(s.controls.target);c.dispatchEvent(event('wheel',{deltaY:100,deltaMode:0,clientX:200,clientY:200}));assert.ok(s.camera.position.distanceTo(s.controls.target)>dist);
 s.panMode(true);c.dispatchEvent(event('pointerdown',{pointerId:2,pointerType:'mouse',button:0,clientX:200,clientY:200}));c.ownerDocument.dispatchEvent(event('pointermove',{pointerId:2,pointerType:'mouse',clientX:250,clientY:200}));c.ownerDocument.dispatchEvent(event('pointerup',{pointerId:2,pointerType:'mouse'}));assert.ok(s.controls.target.length()>.1);
 for(const view of Object.keys(directions)){s.standard(view);assert.ok(s.controls.target.length()<1e-6);assert.ok(s.camera.position.clone().normalize().distanceTo({x:directions[view][0]/Math.hypot(...directions[view]),y:directions[view][1]/Math.hypot(...directions[view]),z:directions[view][2]/Math.hypot(...directions[view])})<.001);}
 s.setVisible(false);assert.equal(scheduled.size,0);s.invalidate();assert.equal(scheduled.size,0);s.setVisible(true);assert.equal(scheduled.size,1);
 c.dispatchEvent(new Event('webglcontextlost',{cancelable:true}));assert.equal(scheduled.size,0);assert.deepEqual(state,[true]);c.dispatchEvent(new Event('webglcontextrestored'));assert.deepEqual(state,[true,false]);
 let gpu=0;s.geometry.addEventListener('dispose',()=>gpu++);s.materials.forEach(m=>m.addEventListener('dispose',()=>gpu++));s.destroy();s.destroy();assert.equal(disposed,2);assert.equal(gpu,3);assert.equal(scheduled.size,0);assert.equal(c.style.touchAction,'');
});
test('WebGL creation failure is surfaced for the component empty state',()=>{assert.throws(()=>new ModelScene(canvas(),decodeMesh(fixture(),meta),()=>{},()=>{throw Error('no WebGL')}),/no WebGL/);});
