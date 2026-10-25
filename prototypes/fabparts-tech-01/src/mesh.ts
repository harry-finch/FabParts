/** FPM1 is a mesh snapshot, never a STEP/WRL parser. */
export type MeshData = {positions:Float64Array; indices:Uint32Array; colors:Float32Array; sides:Uint8Array; bounds:number[][]; units:string; warnings:string[]};
export function decodeMesh(bytes:Uint8Array, metadata:{vertices?:number;triangles?:number;units?:string;warnings?:string[]}):MeshData {
  if(bytes.byteLength<12||bytes.byteLength>16*1024*1024)throw Error('Maillage hors limites.');
  const view=new DataView(bytes.buffer,bytes.byteOffset,bytes.byteLength);
  if(view.getUint32(0,false)!==0x46504d31)throw Error('Format de maillage inconnu.');
  const vertices=view.getUint32(4,true), triangles=view.getUint32(8,true);
  if(vertices<1||vertices>60000||triangles<1||triangles>60000||vertices!==metadata.vertices||triangles!==metadata.triangles||bytes.length!==12+vertices*24+triangles*25)throw Error('Taille de maillage incohérente.');
  let offset=12;const positions=new Float64Array(vertices*3), indices=new Uint32Array(triangles*3),colors=new Float32Array(triangles*3);
  const bounds=[[Infinity,Infinity,Infinity],[-Infinity,-Infinity,-Infinity]];
  for(let i=0;i<positions.length;i++,offset+=8){const n=view.getFloat64(offset,true);if(!Number.isFinite(n)||Math.abs(n)>1e9)throw Error('Coordonnées 3D invalides.');positions[i]=n;bounds[0][i%3]=Math.min(bounds[0][i%3],n);bounds[1][i%3]=Math.max(bounds[1][i%3],n);}
  for(let i=0;i<indices.length;i++,offset+=4){const n=view.getUint32(offset,true);if(n>=vertices)throw Error('Indice 3D invalide.');indices[i]=n;}
  for(let i=0;i<colors.length;i++,offset+=4){const n=view.getFloat32(offset,true);if(!Number.isFinite(n)||n<0||n>1)throw Error('Couleur 3D invalide.');colors[i]=n;}
  const sides=bytes.slice(offset);if(sides.some(n=>n>1))throw Error('Surface 3D invalide.');
  return {positions,indices,colors,sides,bounds,units:metadata.units??'source',warnings:metadata.warnings??[]};
}
export async function verifyMeshHash(bytes:Uint8Array, expected:string) {
  const digest=await crypto.subtle.digest('SHA-256',bytes.slice().buffer);
  const actual=Array.from(new Uint8Array(digest),b=>b.toString(16).padStart(2,'0')).join('');
  if(actual!==expected)throw Error('Empreinte du maillage différente.');
}
