import test from 'node:test';
import assert from 'node:assert/strict';
import {WorkspaceController} from '../src/workspace.ts';
function setup(overrides={}){
 const calls=[],states=[];
 const responses={workspace_info:()=>({mode:'personal',path:'/owned/active',backups:'/owned/backups',schema:'0008',restart_required:false}),
 backup_workspace:()=>({path:'/owned/backups/verified'}),choose_workspace_backup:()=>({handle:'opaque',files:4,schema:'0008',created_at:'2026-10-25T12:00:00Z'}),
 restore_workspace:()=>({restart_required:true,retained_backup:'/owned/backups/previous'}),...overrides};
 const controller=new WorkspaceController(async(command,args)=>{calls.push({command,args});return responses[command](args);},state=>states.push(state));
 return{controller,calls,states};
}
test('backup and restore use host commands, opaque capability, restart gate',async()=>{
 const {controller,calls}=setup();await controller.load();await controller.backup();await controller.select('en');await controller.restore('en');
 assert.equal(controller.state.restart,true);assert.equal(controller.state.backup,'/owned/backups/previous');
 assert.deepEqual(calls.at(-1),{command:'restore_workspace',args:{handle:'opaque',locale:'en'}});
 const count=calls.length;await controller.backup();await controller.select('fr');await controller.restore('fr');assert.equal(calls.length,count);
 assert.ok(calls.every(c=>!c.args||!('path' in c.args)));
});
test('cancellation never enables restore or reports success',async()=>{
 const {controller,calls}=setup({choose_workspace_backup:()=>({cancelled:true})});
 await controller.select('fr');await controller.restore('fr');assert.equal(controller.state.selection,null);assert.equal(controller.state.message,'');assert.equal(calls.length,1);
});
test('failure preserves existing context and cannot announce a backup',async()=>{
 const {controller}=setup({backup_workspace:()=>{throw{code:'DISK_FULL'};}});
 await controller.load();await controller.backup();assert.equal(controller.state.error,'DISK_FULL');assert.equal(controller.state.message,'');assert.equal(controller.state.info.path,'/owned/active');
});
test('double click cannot begin overlapping operations',async()=>{
 let release;const {controller,calls}=setup({backup_workspace:()=>new Promise(resolve=>release=resolve)});
 const first=controller.backup();await controller.backup();assert.equal(calls.length,1);release({path:'/verified'});await first;assert.equal(controller.state.busy,false);
});
test('restore cancellation retains chosen backup but never requests restart',async()=>{
 const {controller}=setup({restore_workspace:()=>({cancelled:true})});await controller.select('fr');await controller.restore('fr');assert.equal(controller.state.restart,false);assert.ok(controller.state.selection);assert.equal(controller.state.message,'');
});
