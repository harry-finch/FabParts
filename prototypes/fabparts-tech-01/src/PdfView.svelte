<script lang="ts">
import { onMount } from 'svelte';
import { ChevronLeft, ChevronRight, ZoomIn, ZoomOut, Scan } from '@lucide/svelte';
import { getDocument, PDFWorker, type PDFDocumentProxy, type RenderTask } from 'pdfjs-dist';
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url';
import { zoomed } from './preview';
import { visibleTimeout } from './pdf_render';
let { bytes, large=false }: {bytes:Uint8Array;large?:boolean}=$props();
let canvas:HTMLCanvasElement, container:HTMLDivElement;
let doc=$state<PDFDocumentProxy>(), page=$state(1), count=$state(0), zoom=$state(1), width=$state(300), error=$state(''), rendering=$state(false), attempt=$state(0);
onMount(()=>{
let disposed=false;
// An explicit local worker prevents PDF.js falling back to main-thread parsing
// for Tauri's opaque custom origin. No CDN wrapper or remote URL is used.
let port:Worker;
try {port=new Worker(workerUrl,{type:'module'});} catch {error='Worker PDF indisponible dans cette WebView.';return;}
const worker=PDFWorker.create({port});
const task=getDocument({worker,data:bytes.slice(),enableXfa:false,useWasm:false,stopAtErrors:true,maxImageSize:16000000,canvasMaxAreaInBytes:32000000,cMapUrl:new URL('/pdfjs/cmaps/',location.href).href,cMapPacked:true,standardFontDataUrl:new URL('/pdfjs/standard_fonts/',location.href).href});
task.onPassword=()=>{error='PDF protégé par mot de passe : format non pris en charge.';void task.destroy();};
const stopTimer=visibleTimeout(()=>{error='Délai de lecture PDF dépassé.';void task.destroy();port.terminate();},10000);
task.promise.then(value=>{if(disposed)return;if(value.numPages>2000){error='PDF limité à 2 000 pages.';void task.destroy();return;}doc=value;count=value.numPages;}).catch(()=>{if(!disposed&&!error)error='PDF corrompu ou non pris en charge.';}).finally(()=>stopTimer());
const observer=new ResizeObserver(entries=>width=entries[0].contentRect.width);observer.observe(container);
return ()=>{disposed=true;stopTimer();observer.disconnect();void task.destroy();worker.destroy();port.terminate();};
});
$effect(()=>{
const document=doc, number=page, scale=zoom, available=width;void attempt;if(!document)return;
let cancelled=false, render:RenderTask|undefined;rendering=true;error='';
const stopTimer=visibleTimeout(()=>{if(!cancelled){cancelled=true;render?.cancel();error='Délai de rendu PDF dépassé.';rendering=false;}},10000);
void document.getPage(number).then(async pdfPage=>{
if(cancelled)return;const natural=pdfPage.getViewport({scale:1});
const bounded=Math.min((available-24)/natural.width*scale,Math.sqrt(8000000/(natural.width*natural.height)));
const viewport=pdfPage.getViewport({scale:bounded});canvas.width=Math.ceil(viewport.width);canvas.height=Math.ceil(viewport.height);
render=pdfPage.render({canvas,viewport});await render.promise;
}).catch(e=>{if(!cancelled&&e?.name!=='RenderingCancelledException')error='Erreur de rendu PDF.';}).finally(()=>{stopTimer();if(!cancelled)rendering=false;});
return ()=>{cancelled=true;stopTimer();render?.cancel();};
});
</script>
<div class="pdf-view" class:large bind:this={container}>
<div class="tools"><button aria-label="Page précédente" disabled={!doc||page===1} onclick={()=>page--}><ChevronLeft size={14}/></button><span>{page} / {count||'…'}</span><button aria-label="Page suivante" disabled={!doc||page===count} onclick={()=>page++}><ChevronRight size={14}/></button><button aria-label="Zoom arrière PDF" onclick={()=>zoom=zoomed(zoom,1/1.4)}><ZoomOut size={14}/></button><button aria-label="Zoom avant PDF" onclick={()=>zoom=zoomed(zoom,1.4)}><ZoomIn size={14}/></button><button aria-label="Ajuster la largeur" onclick={()=>zoom=1}><Scan size={14}/></button></div>
{#if error}<p role="alert">{error}{#if doc}<button onclick={()=>attempt++}>Réessayer</button>{/if}</p>{/if}<div class="page" aria-busy={!doc||rendering}><canvas class:pending={rendering} bind:this={canvas} aria-label={`Page PDF ${page}`}></canvas></div>{#if (!doc||rendering)&&!error}<p role="status">Chargement du PDF…</p>{/if}
</div>
<style>
.pdf-view{min-width:0;background:var(--bg-workspace)}.tools{display:flex;align-items:center;gap:4px;padding:4px 8px;flex-wrap:wrap;min-height:30px;font-size:var(--fs-xs)}button{background:var(--bg-panel);border:1px solid var(--border);color:var(--text-primary);padding:4px;display:inline-flex;cursor:pointer}button:disabled{opacity:.35}.page{height:144px;overflow:auto;padding:8px;text-align:center}.large .page{height:60vh}canvas{background:white;vertical-align:top}canvas.pending{visibility:hidden}p{font-size:var(--fs-xs);padding:8px;margin:0;color:var(--text-secondary)}
</style>
