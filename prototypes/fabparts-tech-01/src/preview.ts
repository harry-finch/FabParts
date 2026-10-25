import { decodeMesh, verifyMeshHash, type MeshData } from './mesh.ts';
import type { Transport } from './controller';
export type Primitive = {kind:string;points:[number,number][];layer:string;text:string;width:number;filled:boolean;angle:number;size:number};
export type Drawing = {name:string;unit:number;style:number;units:'mm';bounds:number[];primitives:Primitive[];warnings:string[]};
export type Preview = {status:string;message?:string;kind?:string;name?:string;origin?:string;source?:string;sha256?:string;selected?:boolean;storage?:string;drawings?:Drawing[];handle?:string;size_bytes?:number;chunk_bytes?:number;bytes?:Uint8Array;mesh?:MeshData;vertices?:number;triangles?:number;units?:string;warnings?:string[];mesh_sha256?:string};
export const zoomed = (zoom:number, factor:number) => Math.min(8,Math.max(.5,zoom*factor));
export function viewBox(bounds:number[], zoom=1) {const [x,y,w,h]=bounds;return [x+w/2-w/zoom/2,y+h/2-h/zoom/2,w/zoom,h/zoom].join(' ');}
export const layerGroup = (layer:string) => ['Pads','Pad1','PadLabel','Drill'].includes(layer) ? 'F.Cu' : layer;
export const layerColor = (layer:string):string => ({Pad1:'var(--accent-text)',Pads:'var(--accent)',PadLabel:'var(--text-primary)',Drill:'var(--bg-workspace)', 'F.Cu':'var(--accent)', 'F.SilkS':'var(--text-primary)','F.Fab':'var(--info)','F.CrtYd':'var(--text-secondary)',Body:'var(--text-primary)',Pins:'var(--accent-text)'}[layer] || 'var(--text-secondary)');
export class PreviewController {
  private epoch=0; private activeModel:string|undefined; private invoke:Transport; private changed:(value:Preview)=>void;
  constructor(invoke:Transport, changed:(value:Preview)=>void) {this.invoke=invoke;this.changed=changed;}
  dispose() { this.epoch++; const handle=this.activeModel;this.activeModel=undefined;if(handle)void this.invoke("release_model_preview",{handle}).catch(()=>{}); }
  async load(id:string, role:string, asset_id='') {
    this.dispose();const epoch=this.epoch;this.changed({status:'loading'});let handle:string|undefined;
    try {
      let result=await this.invoke<Preview>('get_asset_preview',{query:{id,role,...(asset_id?{asset_id}:{})}});handle=result.handle;
      if(epoch!==this.epoch)return;
      if(role==='MODEL_3D' && handle) {
        this.activeModel=handle; const deadline=Date.now()+65000;
        while(result.status==='loading') {
          if(Date.now()>deadline)throw Error('Délai de conversion 3D dépassé.');
          await new Promise(resolve=>setTimeout(resolve,150));
          if(epoch!==this.epoch)return;
          result={...result,...await this.invoke<Preview>('get_model_status',{handle})};
          if(epoch!==this.epoch)return;
        }
      }
      if(result.status==='ready' && handle) {
        const size=result.size_bytes ?? 0;
        if(!Number.isInteger(size)||size<1||size>16*1024*1024||result.chunk_bytes!==65536) throw Error('Aperçu hors limites.');
        const bytes=new Uint8Array(size);
        for(let offset=0;offset<size;offset+=65536) {
          const chunk=await this.invoke<{offset:number;data:string;eof:boolean}>(role==='MODEL_3D'?'read_mesh_chunk':'read_pdf_chunk',{handle,offset});
          if(epoch!==this.epoch)return;
          const decoded=atob(chunk.data);
          if(chunk.offset!==offset||decoded.length!==Math.min(65536,size-offset)||chunk.eof!==(offset+decoded.length===size)) throw Error('Bloc d’aperçu incohérent.');
          for(let i=0;i<decoded.length;i++)bytes[offset+i]=decoded.charCodeAt(i);
        }
        if(role==='MODEL_3D'){await verifyMeshHash(bytes,result.mesh_sha256??'');result.mesh=decodeMesh(bytes,result);}else result.bytes=bytes;
      }
      if(epoch===this.epoch)this.changed(result);
    } catch(error) {if(epoch===this.epoch)this.changed({status:'error',message:(error as Error)?.message || 'Lecture de l’aperçu impossible.'});}
    finally {if(handle){if(this.activeModel===handle)this.activeModel=undefined;await this.invoke(role==='MODEL_3D'?'release_model_preview':'release_preview',{handle}).catch(()=>{});}}
  }
}

// Body fills must precede pins even when KiCad stores common-unit pins first.
export function paintOrder(primitives:Primitive[]) {
  const z=(p:Primitive)=>p.layer==='Pins'?4:p.layer==='PadLabel'?3:p.layer==='Drill'?2:['Pads','Pad1'].includes(p.layer)?1:0;
  return [...primitives].sort((a,b)=>z(a)-z(b));
}
