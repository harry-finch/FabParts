<!-- Aperçu 3D en lecture seule : cadrage, vues standard et orbite sans animation permanente. -->
<script lang="ts">
import { onMount } from 'svelte';
import { Hand, Scan, ZoomIn, ZoomOut } from '@lucide/svelte';
import { ModelScene, type ViewName } from './model_scene';
import type { MeshData } from './mesh';
import { text as t } from './text';
let {mesh,large=false}:{mesh:MeshData;large?:boolean}=$props();
let canvas:HTMLCanvasElement, host:HTMLDivElement, scene:ModelScene|undefined;
let pan=$state(false);
let error=$state(''), view=$state<ViewName>('iso');
onMount(()=>{
  try {scene=new ModelScene(canvas,mesh,lost=>error=lost?t('modelContextLost'):'');}
  catch {error=t('modelWebglUnavailable');return;}
  let intersecting=true;
  const visibility=()=>scene?.setVisible(intersecting&&!document.hidden);
  const intersection=new IntersectionObserver(entries=>{intersecting=entries[0].isIntersecting;visibility();});intersection.observe(canvas);
  document.addEventListener('visibilitychange',visibility);
  const resize=new ResizeObserver(entries=>{const {width,height}=entries[0].contentRect;scene?.resize(width,height);});resize.observe(canvas);
  const theme=()=>scene?.background(getComputedStyle(host).getPropertyValue('--bg-workspace').trim());
  const observer=new MutationObserver(theme);observer.observe(document.documentElement,{attributes:true,attributeFilter:['class','data-theme','style']});theme();
  scene.resize(canvas.clientWidth,canvas.clientHeight);scene.standard('iso');visibility();
  return ()=>{intersection.disconnect();resize.disconnect();observer.disconnect();document.removeEventListener('visibilitychange',visibility);scene?.destroy();scene=undefined;};
});
</script>
<div class="model-view" class:large bind:this={host}>
<div class="tools">
{#if large}<label>{t('modelView')}<select bind:value={view} onchange={()=>scene?.standard(view)}><option value="iso">{t('modelIso')}</option><option value="top">{t('modelTop')}</option><option value="bottom">{t('modelBottom')}</option><option value="front">{t('modelFront')}</option><option value="back">{t('modelBack')}</option></select></label>{/if}
{#if large}<button title={t('modelPan')} aria-label={t('modelPan')} aria-pressed={pan} disabled={!!error} onclick={()=>{pan=!pan;scene?.panMode(pan);}}><Hand size={14}/></button>{/if}
<button title={t('modelZoomOut')} aria-label={t('modelZoomOut')} disabled={!!error} onclick={()=>scene?.zoom(1.4)}><ZoomOut size={14}/></button>
<button title={t('modelZoomIn')} aria-label={t('modelZoomIn')} disabled={!!error} onclick={()=>scene?.zoom(1/1.4)}><ZoomIn size={14}/></button>
<button title={t('modelFit')} aria-label={t('modelFit')} disabled={!!error} onclick={()=>scene?.fit()}><Scan size={14}/></button>
</div>
{#if error}<p role="alert">{error}</p>{/if}
<canvas bind:this={canvas} aria-label={t('modelCanvas')} title={t('modelHelp')}></canvas>
{#if large}<p>{t('modelHelp')} · Z ↑ · {mesh.units==='mm'?t('modelMillimetres'):t('modelSourceUnits')}</p>{/if}
{#if mesh.warnings.length}<p role="status">{mesh.warnings.join(' ')}</p>{/if}
</div>
<style>
.model-view{min-width:0;background:var(--bg-workspace)}canvas{display:block;width:100%;height:144px;touch-action:none}.large canvas{height:54vh;min-height:250px}.tools{display:flex;gap:4px;align-items:center;flex-wrap:wrap;padding:4px 8px;min-height:30px}.tools label{display:flex;align-items:center;gap:6px;flex:1;font-size:var(--fs-xs);min-width:0}select{max-width:100%;min-width:0;background:var(--bg-input);color:var(--text-primary);border:1px solid var(--border)}button{display:inline-flex;padding:4px;background:var(--bg-panel);border:1px solid var(--border);color:var(--text-primary);cursor:pointer}button[aria-pressed="true"]{background:var(--bg-selected);color:var(--text-primary)}button:disabled{opacity:.35}p{margin:0;padding:6px 8px;font-size:var(--fs-xs);color:var(--text-secondary);overflow-wrap:anywhere}
</style>
