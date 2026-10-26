import test from 'node:test';
import assert from 'node:assert/strict';
import {ReviewController} from '../src/validation.ts';
const subject={kind:'Part',id:'a'};
const report=(patch={})=>({kind:'Part',id:'a',name:'Example',state:'WARNING',eligible:false,readiness:'SCHEMATIC',report:{created_at:'now',level:'WARNING',ruleset:'M5-1',warnings_accepted:false,counts:{PASS:2,WARNING:1,ERROR:0}},findings:[],total_findings:3,offset:0,members:[],member_offset:0,total_members:0,handle:'opaque',...patch});
function setup(invoke=async()=>report()){
 const calls=[],states=[];
 const controller=new ReviewController(async(command,args)=>{calls.push({command,args});return invoke(command,args);},state=>states.push(state));
 return{controller,calls,states};
}
test('a warning requires displayed report, examination and explicit confirmation',async()=>{
 const {controller,calls}=setup();await controller.select(subject);await controller.accept();assert.equal(calls.length,1);
 controller.confirm(true);await controller.accept();assert.equal(calls.length,1);
 controller.examine();await controller.accept();assert.equal(calls.length,1);
 controller.confirm(true);await controller.accept();assert.deepEqual(calls.at(-1),{command:'accept_validation_warnings',args:{subject,handle:'opaque'}});
 assert.equal(controller.state.confirmed,false);assert.equal(controller.state.reviewOpen,false);
});
test('every report page must be displayed before accepting warnings',async()=>{
 const {controller}=setup(async(command,args)=>report({total_findings:201,offset:args.query?.offset||0}));
 await controller.select(subject);controller.examine();controller.confirm(true);assert.equal(controller.state.confirmed,false);
 await controller.refresh(100);await controller.refresh(200);assert.equal(controller.state.allPages,true);controller.examine();controller.confirm(true);assert.equal(controller.state.confirmed,true);
});
test('a changed report resets the pages and confirmation',async()=>{
 let revision='one';const {controller}=setup(async(command,args)=>report({report:{...report().report,created_at:revision},total_findings:101,offset:args.query?.offset||0}));
 await controller.select(subject);await controller.refresh(100);controller.examine();controller.confirm(true);assert.ok(controller.state.confirmed);
 revision='two';await controller.refresh();assert.equal(controller.state.confirmed,false);assert.equal(controller.state.allPages,false);
});
test('stale reports never send a warning acceptance',async()=>{
 const {controller,calls}=setup(async()=>report({state:'STALE',readiness:'INCOMPLETE'}));await controller.select(subject);controller.examine();controller.confirm(true);await controller.accept();assert.equal(calls.length,1);
});
test('errors remove previous readiness and cannot show false success',async()=>{
 let fail=false;const {controller}=setup(async()=>{if(fail)throw{code:'REPORT_CHANGED'};return report();});await controller.select(subject);fail=true;await controller.validate();assert.equal(controller.state.data,null);assert.equal(controller.state.error,'REPORT_CHANGED');assert.equal(controller.state.confirmed,false);
});
test('late replies for another subject and disposed panels are ignored',async()=>{
 const pending=[];const {controller}=setup(()=>new Promise(resolve=>pending.push(resolve)));
 const old=controller.select(subject);const next=controller.select({kind:'Part',id:'b'});pending[1](report({id:'b'}));await next;pending[0](report());await old;assert.equal(controller.state.data.id,'b');
 const last=controller.refresh();controller.dispose();pending[2](report({id:'c'}));await last;assert.equal(controller.state.data.id,'b');
});
test('double clicks and repeated accepted-warning actions cannot write again',async()=>{
 let release;const {controller,calls}=setup(async(command)=>command==='run_validation'?new Promise(resolve=>release=resolve):report());await controller.select(subject);
 const first=controller.validate();await controller.validate();assert.equal(calls.filter(c=>c.command==='run_validation').length,1);release(report({report:{...report().report,warnings_accepted:true}}));await first;controller.examine();controller.confirm(true);await controller.accept();assert.equal(calls.length,2);
});
test('explicit warning review on an ERROR report cannot invent PCB eligibility',async()=>{
 const {controller,calls}=setup(async()=>report({state:'ERROR',readiness:'INCOMPLETE',report:{...report().report,level:'ERROR',counts:{PASS:1,WARNING:1,ERROR:2}}}));
 await controller.select(subject);controller.examine();controller.confirm(true);await controller.accept();
 assert.equal(calls.at(-1).command,'accept_validation_warnings');assert.equal(controller.state.data.eligible,false);
});
