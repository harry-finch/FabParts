/** Géométrie neutre, cadrage et rendu à la demande ; aucun accès aux fichiers. */
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import type { MeshData } from './mesh';
export type ViewName='iso'|'top'|'bottom'|'front'|'back';
export const directions:Record<ViewName,[number,number,number]>={iso:[1,-1,1],top:[0,0,1],bottom:[0,0,-1],front:[0,-1,0],back:[0,1,0]};
export function geometryFor(mesh:MeshData) {
  const center=mesh.bounds[0].map((v,i)=>(v+mesh.bounds[1][i])/2);
  const positions=new Float32Array(mesh.indices.length*3), colors=new Float32Array(positions.length);
  const order=Array.from(mesh.sides.keys()).sort((a,b)=>mesh.sides[a]-mesh.sides[b]);
  for(let i=0;i<mesh.indices.length;i++)for(let a=0;a<3;a++){
    const source=order[Math.floor(i/3)]*3+i%3;
    positions[i*3+a]=mesh.positions[mesh.indices[source]*3+a]-center[a];
    colors[i*3+a]=mesh.colors[order[Math.floor(i/3)]*3+a];
  }
  const geometry=new THREE.BufferGeometry();
  geometry.setAttribute('position',new THREE.BufferAttribute(positions,3));
  geometry.setAttribute('color',new THREE.BufferAttribute(colors,3));
  geometry.computeVertexNormals();geometry.computeBoundingSphere();
  const front=mesh.sides.filter(s=>s===0).length;
  if(front)geometry.addGroup(0,front*3,0);
  if(front<mesh.sides.length)geometry.addGroup(front*3,(mesh.sides.length-front)*3,1);
  return geometry;
}
export function fitDistance(radius:number, aspect:number, fov=35) {
  const half=THREE.MathUtils.degToRad(fov/2), horizontal=Math.atan(Math.tan(half)*Math.max(aspect,.05));
  return Math.max(radius,1e-8)/Math.sin(Math.min(half,horizontal))*1.12;
}
export type Renderer=Pick<THREE.WebGLRenderer,'setPixelRatio'|'setSize'|'setClearColor'|'render'|'dispose'|'forceContextLoss'>;
export class ModelScene {
  renderer:Renderer; controls:OrbitControls; camera=new THREE.PerspectiveCamera(35,1,.01,1000);
  scene=new THREE.Scene(); geometry:THREE.BufferGeometry; materials:THREE.MeshLambertMaterial[];
  radius:number; disposed=false; visible=true; lost=false; frame:number|null=null;
  onError:(lost:boolean)=>void; canvas:HTMLCanvasElement;
  private request=()=>this.invalidate();
  private contextLost=(event:Event)=>{event.preventDefault();this.lost=true;this.cancelFrame();this.onError(true);};
  private contextRestored=()=>{this.lost=false;this.onError(false);this.invalidate();};
  constructor(canvas:HTMLCanvasElement, mesh:MeshData, onError:(lost:boolean)=>void,
    factory:(canvas:HTMLCanvasElement)=>Renderer=c=>new THREE.WebGLRenderer({canvas:c,antialias:true,alpha:false,powerPreference:'low-power'})) {
    this.canvas=canvas;this.onError=onError;this.renderer=factory(canvas);
    this.geometry=geometryFor(mesh);this.radius=Math.max(this.geometry.boundingSphere?.radius??1,1e-8);
    this.materials=[new THREE.MeshLambertMaterial({vertexColors:true,side:THREE.FrontSide}),new THREE.MeshLambertMaterial({vertexColors:true,side:THREE.DoubleSide})];
    this.scene.add(new THREE.Mesh(this.geometry,this.materials));
    this.scene.add(new THREE.AmbientLight(0xffffff,.8));
    const light=new THREE.DirectionalLight(0xffffff,1.3);light.position.set(2,-3,5);this.scene.add(light);
    this.camera.up.set(0,0,1);
    this.controls=new OrbitControls(this.camera,canvas);this.controls.enableDamping=false;
    this.controls.minDistance=this.radius*.15;this.controls.maxDistance=this.radius*100;
    this.controls.addEventListener('change',this.request);
    canvas.addEventListener('webglcontextlost',this.contextLost);canvas.addEventListener('webglcontextrestored',this.contextRestored);
    this.renderer.setPixelRatio(Math.min(globalThis.devicePixelRatio||1,2));
    this.camera.near=this.radius*.001;this.camera.far=this.radius*250;
    this.standard('iso');
  }
  resize(width:number,height:number){if(this.disposed||width<1||height<1)return;this.camera.aspect=width/height;this.camera.updateProjectionMatrix();this.renderer.setSize(width,height,false);this.invalidate();}
  background(css:string){this.renderer.setClearColor(css);this.invalidate();}
  standard(view:ViewName){const distance=fitDistance(this.radius,this.camera.aspect);this.controls.target.set(0,0,0);this.camera.position.copy(new THREE.Vector3(...directions[view]).normalize().multiplyScalar(distance));this.camera.lookAt(0,0,0);this.controls.update();this.invalidate();}
  fit(){const direction=this.camera.position.clone().sub(this.controls.target).normalize();this.controls.target.set(0,0,0);this.camera.position.copy(direction.multiplyScalar(fitDistance(this.radius,this.camera.aspect)));this.controls.update();this.invalidate();}
  zoom(factor:number){this.camera.position.sub(this.controls.target).multiplyScalar(factor).add(this.controls.target);this.controls.update();this.invalidate();}
  panMode(enabled:boolean){this.controls.mouseButtons.LEFT=enabled?THREE.MOUSE.PAN:THREE.MOUSE.ROTATE;}
  setVisible(visible:boolean){this.visible=visible;if(visible)this.invalidate();else this.cancelFrame();}
  invalidate(){if(!this.disposed&&!this.lost&&this.visible&&this.frame===null)this.frame=requestAnimationFrame(()=>{this.frame=null;if(!this.disposed&&!this.lost&&this.visible)this.renderer.render(this.scene,this.camera);});}
  private cancelFrame(){if(this.frame!==null){cancelAnimationFrame(this.frame);this.frame=null;}}
  destroy(){if(this.disposed)return;this.disposed=true;this.cancelFrame();this.controls.removeEventListener('change',this.request);this.controls.dispose();this.canvas.removeEventListener('webglcontextlost',this.contextLost);this.canvas.removeEventListener('webglcontextrestored',this.contextRestored);this.geometry.dispose();this.materials.forEach(m=>m.dispose());this.scene.clear();this.renderer.dispose();this.renderer.forceContextLoss();}
}
