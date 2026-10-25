<script lang="ts">
import { ZoomIn, ZoomOut, Scan } from '@lucide/svelte';
import { type Drawing, zoomed, viewBox, paintOrder, layerGroup, layerColor } from './preview';
let { drawings, large=false }: {drawings:Drawing[];large?:boolean}=$props();
let index=$state(0), zoom=$state(1), hidden=$state<string[]>([]);
let drawing=$derived(drawings[index] || drawings[0]);
let layers=$derived([...new Set(drawing.primitives.map(p=>layerGroup(p.layer)))]);
</script>
<div class="drawing-view" class:large>
<div class="tools">
{#if drawings.length>1}<label>Unité / variante <select bind:value={index} onchange={()=>zoom=1}>{#each drawings as d,i}<option value={i}>{d.name} · {d.unit} / {d.style}</option>{/each}</select></label>{/if}
<button title="Zoom arrière" aria-label="Zoom arrière" onclick={()=>zoom=zoomed(zoom,1/1.5)}><ZoomOut size={14}/></button><button title="Zoom avant" aria-label="Zoom avant" onclick={()=>zoom=zoomed(zoom,1.5)}><ZoomIn size={14}/></button><button title="Recentrer" aria-label="Recentrer" onclick={()=>zoom=1}><Scan size={14}/></button>
</div>
<svg role="img" aria-label={drawing.name} viewBox={viewBox(drawing.bounds,zoom)} preserveAspectRatio="xMidYMid meet">
{#each paintOrder(drawing.primitives).filter(p=>!hidden.includes(layerGroup(p.layer))) as p}
{@const a=p.points[0]}{@const b=p.points[1] || a}
<g fill={p.filled ? layerColor(p.layer) : 'none'} stroke={layerColor(p.layer)} stroke-width={p.width} stroke-linejoin="round" stroke-linecap="round">
{#if p.kind==='text'||p.kind==='annotation'}<text x={a[0]} y={a[1]} transform={`rotate(${p.angle} ${a[0]} ${a[1]})`} font-size={p.size} fill={layerColor(p.layer)} stroke={p.layer==='PadLabel'?'var(--bg-workspace)':'none'} stroke-width={p.layer==='PadLabel'?p.size*.15:0} paint-order="stroke" text-anchor="middle" dominant-baseline="central">{p.text}</text>
{:else if p.kind.startsWith('pad_')}<g transform={`translate(${a[0]} ${a[1]}) rotate(${p.angle})`} stroke="none">
{#if p.kind==='pad_ellipse'}<ellipse cx="0" cy="0" rx={b[0]/2} ry={b[1]/2}/>{:else}<rect x={-b[0]/2} y={-b[1]/2} width={b[0]} height={b[1]} rx={p.kind==='pad_oval'?Math.min(...b)/2:p.kind==='pad_round'?Math.min(...b)*p.size:0}/>{/if}</g>
{:else if p.kind==='rect'}<rect x={Math.min(a[0],b[0])} y={Math.min(a[1],b[1])} width={Math.abs(b[0]-a[0])} height={Math.abs(b[1]-a[1])} fill={p.filled?'var(--bg-panel)':'none'}/>
{:else if p.kind==='ellipse'}<ellipse cx={(a[0]+b[0])/2} cy={(a[1]+b[1])/2} rx={Math.abs(b[0]-a[0])/2} ry={Math.abs(b[1]-a[1])/2}/>
{:else if p.kind==='polygon'}<polygon points={p.points.map(pt=>pt.join(',')).join(' ')}/>
{:else}<polyline points={p.points.map(pt=>pt.join(',')).join(' ')}/>{/if}
</g>{/each}
</svg>
{#if layers.includes('F.Cu')}<details class="layers" open={large}><summary>Couches</summary><div>{#each layers as layer}<label><input type="checkbox" checked={!hidden.includes(layer)} onchange={()=>hidden=hidden.includes(layer)?hidden.filter(l=>l!==layer):[...hidden,layer]}/><span style:color={layerColor(layer)}>{layer}</span></label>{/each}</div></details>{/if}
{#if drawing.warnings.length}<p class="warning" role="status">Aperçu partiel · {drawing.warnings.join(' ')}</p>{/if}
{#if large}<p class="scale">Coordonnées en mm · géométrie du fichier · {Math.round(zoom*100)} %</p>{/if}
</div>
<style>
.drawing-view{position:relative;min-width:0;background:var(--bg-workspace)}svg{display:block;width:100%;height:144px;font-family:var(--font-ui),sans-serif}.large svg{height:54vh;min-height:250px}
.tools{display:flex;align-items:center;gap:4px;flex-wrap:wrap;padding:4px 8px;min-height:30px}.tools label{font-size:var(--fs-xs);display:flex;align-items:center;gap:4px;flex:1;min-width:0}select{max-width:100%;min-width:0;background:var(--bg-input);color:var(--text-primary);border:1px solid var(--border)}button{background:var(--bg-panel);border:1px solid var(--border);color:var(--text-primary);padding:4px;display:inline-flex;cursor:pointer}.layers{padding:4px 8px;font-size:var(--fs-xs);color:var(--text-secondary)}.layers div{display:flex;gap:8px;flex-wrap:wrap;padding:4px 0}.layers label{display:flex;align-items:center;gap:3px}.warning,.scale{margin:0;padding:6px 8px;font-size:var(--fs-xs);color:var(--text-secondary);overflow-wrap:anywhere}
</style>
