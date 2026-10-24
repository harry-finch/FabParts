<script lang="ts">
import {
  Search,
  Plus,
  Library,
  Layers,
  Cpu,
  CircuitBoard,
  Box,
  FileText,
  ChevronRight,
  ArrowLeft,
  X,
  Check,
  Settings2,
  Monitor,
  Sun,
  Moon,
  Undo2,
  Redo2,
  SlidersHorizontal,
  Info,
  TriangleAlert,
  RefreshCw,
  PanelRightClose,
  PanelRightOpen,
  SquarePen,
  Folder,
  Plug,
  MemoryStick,
  Component,
  Minus,
  ExternalLink,
  CircleHelp,
} from "@lucide/svelte";
import Section from "./components/Section.svelte";
import Disclosure from "./components/Disclosure.svelte";
import Dialog from "./components/Dialog.svelte";
import StatusBar from "./components/StatusBar.svelte";
import Readiness from "./components/Readiness.svelte";
import SyncState from "./components/SyncState.svelte";
import Preview from "./components/Preview.svelte";
import AddFlow from "./components/AddFlow.svelte";
import ResourceWorkspace from "./components/ResourceWorkspace.svelte";
import { t, i18n, LOCALES } from "./lib/i18n.svelte";
import { theme, THEMES } from "./lib/theme.svelte";
import { catalogue } from "./lib/catalogue.svelte";
import {
  copy,
  kinds,
  categories,
  ready,
  partProperties,
  changePackage,
  changeIdentity,
  sameReference,
  type Part,
  type Library as LibraryName,
  type Ready,
} from "./lib/demo";
let page = $state<"library" | "add" | "detail">("library"),
  selectedId = $state("demo-0"),
  search = $state(""),
  library = $state<LibraryName | "all">("all"),
  category = $state("all"),
  preparation = $state<Ready | "all">("all"),
  pkg = $state("all");
let inspector = $state(true),
  panelWidth = $state(304),
  scenario = $state("normal"),
  dialog = $state<"settings" | "sync" | "help" | "edit" | "roundtrip" | null>(
    null,
  ),
  edit = $state<Part | null>(null),
  notice = $state("");
let resume = $state<Part | null>(null);
let identityError = $state(false);
let searchInput = $state<HTMLInputElement>();
const categoryIcons = {
  mcu: Cpu,
  ic: Component,
  resistor: Minus,
  capacitor: Layers,
  connector: Plug,
  module: MemoryStick,
};
const filtered = $derived(
  scenario === "empty"
    ? []
    : catalogue.parts.filter(
        (p) =>
          (library === "all" || p.libraries.includes(library)) &&
          (category === "all" || p.category === category) &&
          (preparation === "all" || ready(p) === preparation) &&
          (pkg === "all" || p.package === pkg) &&
          [
            p.ref,
            p.manufacturer,
            ...p.description,
            t(`ux.${p.category}`),
            p.package,
            ...p.properties.map((x) => x[1]),
          ]
            .join(" ")
            .toLowerCase()
            .includes(search.toLowerCase().trim()),
      ),
);
const selected = $derived(catalogue.parts.find((p) => p.id === selectedId));
const packages = $derived(
  [...new Set(catalogue.parts.map((p) => p.package))].sort(),
);
const syncing = $derived(catalogue.parts.some((p) => p.sync === "syncing"));
const errors = $derived(
  catalogue.parts.filter((p) => p.sync === "error").length,
);
const localeIndex = $derived(i18n.locale === "fr" ? 0 : 1);
$effect(() => {
  if (page === "library" && !filtered.some((p) => p.id === selectedId))
    selectedId = filtered[0]?.id || "";
});
function clear() {
  search = "";
  category = "all";
  preparation = "all";
  pkg = "all";
  library = "all";
  scenario = "normal";
}
function detail(p: Part) {
  selectedId = p.id;
  page = "detail";
  notice = "";
}
function save(p: Part) {
  catalogue.save(p);
  selectedId = p.id;
  category = "all";
  preparation = "all";
  pkg = "all";
  search = "";
  scenario = "normal";
  if (library !== "all" && !p.libraries.includes(library))
    library = p.libraries[0];
  page = "detail";
  notice = "saved";
}
function update(p: Part) {
  p.version++;
  catalogue.save(p);
}
function saveIdentity() {
  if (!edit?.ref.trim() || !edit.libraries.length) return;
  if (
    catalogue.parts.some(
      (p) => p.id !== edit!.id && sameReference(p.ref, edit!.ref),
    )
  ) {
    identityError = true;
    return;
  }
  let next = copy(edit);
  if (selected) {
    const reconciled = changePackage(
      changeIdentity(selected, next.ref, next.manufacturer),
      next.package,
    );
    next.resources = reconciled.resources;
    next.confirmed = reconciled.confirmed;
    next.properties = reconciled.properties;
  }
  identityError = false;
  update(next);
  dialog = null;
  edit = null;
}
function toggleEditLibrary(l: LibraryName) {
  if (edit)
    edit.libraries = edit.libraries.includes(l)
      ? edit.libraries.filter((x) => x !== l)
      : [...edit.libraries, l];
}
function setScenario(s: string) {
  scenario = s;
  page = "library";
  dialog = null;
  if (s === "load")
    setTimeout(() => {
      if (scenario === "load") scenario = "normal";
    }, 1800);
}
function keydown(e: KeyboardEvent) {
  const input = (e.target as HTMLElement).closest(
    "input,textarea,select,[contenteditable=true]",
  );
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
    e.preventDefault();
    page = "library";
    setTimeout(() => searchInput?.focus());
    return;
  }
  if (input || document.querySelector("dialog[open]")) return;
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") {
    e.preventDefault();
    e.shiftKey ? catalogue.redo() : catalogue.undo();
  }
  if (e.key === "?") dialog = "help";
  if (e.key === "Escape" && page === "detail") page = "library";
}
function startResize(e: PointerEvent) {
  const start = e.clientX,
    width = panelWidth;
  const move = (ev: PointerEvent) =>
    (panelWidth = Math.min(420, Math.max(280, width + start - ev.clientX)));
  const end = () => {
    window.removeEventListener("pointermove", move);
    window.removeEventListener("pointerup", end);
  };
  window.addEventListener("pointermove", move);
  window.addEventListener("pointerup", end);
}
</script>
<svelte:window onkeydown={keydown}/>
<div class="app-shell">
 <header class="appbar">
  <div class="brand">
<img src="/logo.svg" alt=""/>
<strong>FabParts</strong>
<span class="tagline">{t('ux.tagline')}</span>
</div>
  <span class="demo-label">{t('ux.demoShort')} <span>02</span>
</span>
  <div class="bar-right">
   <button class="btn quiet sync-button" onclick={()=>dialog='sync'}>{#if syncing}<RefreshCw size={14}/>{:else if errors}<TriangleAlert size={14}/>{:else}<Check size={14}/>{/if}KiCad <span class="subtle">· {t('ux.simulated')}</span>{#if errors}<span class="counter">{errors}</span>{/if}</button>
   <div class="mini-segments" aria-label={t('app.language')}>{#each LOCALES as l}<button class:on={i18n.locale===l.id} aria-pressed={i18n.locale===l.id} onclick={()=>i18n.set(l.id)}>{l.id.toUpperCase()}</button>{/each}</div>
   <div class="mini-segments" aria-label={t('app.theme')}>{#each THEMES as th}{@const Icon={system:Monitor,light:Sun,dark:Moon}[th]}<button class:on={theme.choice===th} aria-pressed={theme.choice===th} title={t(`app.themes.${th}`)} aria-label={t(`app.themes.${th}`)} onclick={()=>theme.set(th)}>
<Icon size={12}/>
</button>{/each}</div>
   <button class="btn quiet icon" title={t('ux.settings')} aria-label={t('ux.settings')} onclick={()=>dialog='settings'}>
<Settings2 size={16}/>
</button>
   <button class="btn quiet icon" title={t('ux.help')} aria-label={t('ux.help')} onclick={()=>dialog='help'}>
<CircleHelp size={16}/>
</button>
  </div>
 </header>
 <div class="workspace">
  <aside class="sidebar">
   <div class="sidebar-top">
<Library size={15}/>
<strong>{t('ux.libraries')}</strong>
</div>
   <Section id="libraries" title={t('ux.libraries')}>
    {#each ['all','Lab','Personnel'] as lib}{@const Icon=lib==='all'?Layers:Folder}<button class="nav-row" class:active={library===lib} aria-pressed={library===lib} onclick={()=>{library=lib as typeof library;page='library';scenario='normal';}}>
<Icon size={14}/>
<span>{lib==='all'?t('ux.allShort'):lib==='Personnel'?t('ux.personal'):lib}</span>
<small>{lib==='all'?catalogue.parts.length:catalogue.parts.filter(p=>p.libraries.includes(lib as LibraryName)).length}</small>
</button>{/each}
   </Section>
   <Section id="categories" title={t('ux.categories')}>
    <button class="nav-row" class:active={category==='all'} onclick={()=>{category='all';page='library';}}>
<Layers size={14}/>
<span>{t('ux.allCategories')}</span>
</button>
    {#each categories as cat}{@const Icon=categoryIcons[cat]}<button class="nav-row" class:active={category===cat} aria-pressed={category===cat} onclick={()=>{category=cat;page='library';}}>
<Icon size={14}/>
<span>{t(`ux.${cat}`)}</span>
<small>{catalogue.parts.filter(p=>p.category===cat&&(library==='all'||p.libraries.includes(library))).length}</small>
</button>{/each}
   </Section>
   <div class="sidebar-bottom">
<Info size={15}/>
<p>{t('ux.demo')}<span>{t('ux.noEngine')}</span>
</p>
</div>
  </aside>
  <main>
   {#if page==='add'}<AddFlow existing={catalogue.parts} initialLibrary={library==='all'?'Lab':library} {resume} oncancel={()=>page='library'} onsave={save} onexisting={detail}/>
   {:else if page==='detail'&&selected}
    <section class="detail-page">
     <div class="detail-toolbar">
<button class="btn quiet" onclick={()=>page='library'}>
<ArrowLeft size={14}/>{t('ux.back')}</button>
<span class="crumb">/</span>
<span>{selected.ref}</span>
<div class="grow">
</div>
<button class="btn" onclick={()=>{edit=copy(selected);identityError=false;dialog='edit';}}>
<SquarePen size={14}/>{t('ux.modify')}</button>
</div>
     <div class="detail-content">
      <div class="identity-heading">
<div>
<span class="eyebrow">{t(`ux.${selected.category}`)}</span>
<h1>{selected.ref}</h1>
<p>{selected.manufacturer} <span>·</span> {selected.description[localeIndex]}</p>
</div>
<div class="identity-state">
<Readiness state={ready(selected)}/>
<SyncState state={selected.sync}/>
</div>
</div>
      {#if notice}<div class="success-notice" role="status">
<Check size={14}/>{t('ux.saved')}<button class="btn quiet icon" aria-label={t('common.close')} onclick={()=>notice=''}>
<X size={12}/>
</button>
</div>{/if}
      <div class="detail-columns">
<div class="detail-resources">
<h2 class="section-heading">{t('ux.resources')} <span>{t('ux.simulated')}</span>
</h2>
{#if ready(selected)==='draft'}<div class="resume-row"><span>{t('ux.draftHint')}</span><button class="btn primary" onclick={()=>{resume=copy(selected);page='add';}}>{t('ux.resume')}<ChevronRight size={14}/></button></div>{/if}
<ResourceWorkspace part={selected} onupdate={update}/>
<p class="secondary footnote">
<Info size={13}/>{t('ux.notValidation')}</p>
</div>
       <aside class="properties">
<Section id="identity" title={t('ux.characteristics')}>
<dl>
<dt>{t('ux.package')}</dt>
<dd>{selected.package||t('ux.packageNeeded')}</dd>{#each partProperties(selected) as [key,value]}<dt>{t(`ux.${key}` as 'ux.spec')}</dt>
<dd>{value||t('ux.unknownValue')}</dd>{/each}</dl>
{#if !selected.package}<button class="btn" onclick={()=>{edit=copy(selected);identityError=false;dialog='edit';}}>{t('ux.choosePackage')}</button>{/if}
</Section>
        <Section id="membership" title={t('ux.libraries')}>
<div class="members">{#each selected.libraries as lib}<span>
<Folder size={13}/>{lib==='Personnel'?t('ux.personal'):lib}</span>{/each}</div>
</Section>
        <Section id="sync" title="KiCad">
<SyncState state={selected.sync}/>{#if selected.sync==='error'}<p class="secondary small">{t('ux.previous')}</p>
<button class="btn" onclick={()=>catalogue.sync(selected.id)}>
<RefreshCw size={13}/>{t('ux.retry')}</button>{/if}<button class="btn quiet" onclick={()=>dialog='roundtrip'}>
<ExternalLink size={13}/>{t('ux.editKicad')}</button>
</Section>
        <div class="advanced">
<Disclosure id="technical" label={t('ux.technical')}>
<p>{t('ux.association')}</p>
<dl>
<dt>{t('ux.version')}</dt>
<dd>v{selected.version}</dd>
</dl>
<strong>{t('ux.history')}</strong>
<p>{t('ux.historyText')}</p>
<button class="btn" onclick={()=>catalogue.sync(selected.id,true)}>{t('ux.simulateSyncError')}</button>
</Disclosure>
</div>
       </aside>
      </div>
     </div>
    </section>
   {:else}
    <section class="library-page">
     <div class="library-toolbar">
<h1>{library==='all'?t('ux.all'):library==='Personnel'?t('ux.personal'):library}</h1>
<span class="subtle tabular">{t('ux.count',{n:catalogue.parts.filter(p=>library==='all'||p.libraries.includes(library)).length})}</span>
<div class="grow">
</div>
<button class="btn quiet icon" aria-label={t('ux.undo')} title={`${t('ux.undo')} (⌘Z)`} disabled={!catalogue.past.length} onclick={()=>catalogue.undo()}>
<Undo2 size={15}/>
</button>
<button class="btn quiet icon" aria-label={t('ux.redo')} title={t('ux.redo')} disabled={!catalogue.future.length} onclick={()=>catalogue.redo()}>
<Redo2 size={15}/>
</button>
<button class="btn primary" onclick={()=>{resume=null;page='add';}}>
<Plus size={15}/>{t('ux.add')}</button>
</div>
     <div class="filterbar">
<div class="search">
<Search size={15}/>
<input bind:this={searchInput} bind:value={search} placeholder={t('ux.search')} aria-label={t('ux.search')}/>{#if search}<button class="btn quiet icon" aria-label={t('ux.clear')} onclick={()=>search=''}>
<X size={13}/>
</button>{:else}<kbd>⌘ K</kbd>{/if}</div>
<select class="input" aria-label={t('ux.state')} bind:value={preparation}>
<option value="all">{t('ux.allStates')}</option>{#each ['draft','schematic','pcb'] as s}<option value={s}>{t(`ux.${s}` as 'ux.draft')}</option>{/each}</select>
<select class="input package-filter" aria-label={t('ux.package')} bind:value={pkg}>
<option value="all">{t('ux.allPackages')}</option>{#each packages as p}<option value={p}>{p}</option>{/each}</select>
<button class="btn quiet icon" title={inspector?t('ux.closeDetail'):t('ux.openDetail')} aria-label={inspector?t('ux.closeDetail'):t('ux.openDetail')} onclick={()=>inspector=!inspector}>{#if inspector}<PanelRightClose size={16}/>{:else}<PanelRightOpen size={16}/>{/if}</button>
</div>
     <div class="catalogue" class:no-inspector={!inspector} style:--inspector-width={`${panelWidth}px`}>
      <div class="list-region">
       <div class="result-context">
<span>{category==='all'?t('ux.components'):t(`ux.${category}` as 'ux.ic')}</span>
<span>{t('ux.selectedCount',{n:filtered.length})}</span>
</div>
       {#if scenario==='load'}<div class="empty-state" role="status">
<RefreshCw size={28}/>
<h2>{t('ux.loading')}</h2>
</div>
       {:else if scenario==='failure'}<div class="empty-state" role="alert">
<TriangleAlert size={28}/>
<h2>{t('ux.loadError')}</h2>
<p>{t('ux.loadErrorText')}</p>
<button class="btn" onclick={()=>setScenario('load')}>{t('ux.retry')}</button>
</div>
       {:else if !filtered.length}<div class="empty-state">
<Library size={30}/>
<h2>{t(scenario==='empty'?'ux.emptyTitle':'ux.noResults')}</h2>
<p>{t(scenario==='empty'?'ux.emptyText':'ux.noResultsText')}</p>
<button class="btn" onclick={()=>{if(scenario==='empty'){resume=null;page='add';}else clear();}}>{t(scenario==='empty'?'ux.add':'ux.clear')}</button>
</div>
       {:else}
        <div class="table-scroll">
<table>
<thead>
<tr>
<th>{t('ux.component')}</th>
<th>{t('ux.package')}</th>
<th>{t('ux.state')}</th>
<th class="library-cell">{t('ux.libraries')}</th>
</tr>
</thead>
<tbody>{#each filtered as part}{@const Icon=categoryIcons[part.category]}<tr class:selected={part.id===selectedId}>
<td>
<button class="row-select" aria-pressed={part.id===selectedId} onclick={()=>selectedId=part.id} ondblclick={()=>detail(part)}>
<span class="part-icon">
<Icon size={18}/>
</span>
<span class="part-name">
<strong>{part.ref}</strong>
<span title={part.description[localeIndex]}>{part.manufacturer} · {part.description[localeIndex]}</span>
</span>
</button>
</td>
<td class="pkg-cell">{part.package||t('ux.packageNeeded')}</td>
<td>
<Readiness state={ready(part)}/>
</td>
<td class="library-cell">{part.libraries.map(l=>l==='Personnel'?t('ux.personal'):l).join(' · ')}</td>
</tr>{/each}</tbody>
</table>
</div>
        <div class="list-bottom">
<span class="secondary">{t('ux.demo')}</span>{#if selected}<button class="btn quiet" onclick={()=>detail(selected)}>{t('ux.openDetail')}<ChevronRight size={13}/>
</button>{/if}</div>
       {/if}
      </div>
      {#if inspector}<aside class="inspector">
<button class="resize-handle" onpointerdown={startResize} onkeydown={(e)=>{if(e.key==='ArrowLeft')panelWidth=Math.min(420,panelWidth+20);if(e.key==='ArrowRight')panelWidth=Math.max(280,panelWidth-20);}} aria-label={t('ux.resize')} title={t('ux.resize')}>
</button>
       {#if selected&&scenario==='normal'}
        <div class="inspector-heading">
<span class="eyebrow">{t(`ux.${selected.category}`)}</span>
<h2>{selected.ref}</h2>
<p>{selected.manufacturer}</p>
<p>{selected.description[localeIndex]}</p>
<div class="members">{#each selected.libraries as lib}<span>
<Folder size={12}/>{lib==='Personnel'?t('ux.personal'):lib}</span>{/each}</div>
</div>
        <Section id="selection-readiness" title={t('ux.readyLabel')}>
<Readiness state={ready(selected)}/>
<SyncState state={selected.sync}/>{#if selected.sync==='error'}<p class="secondary small">{t('ux.previous')}</p>
<button class="btn" onclick={()=>catalogue.sync(selected.id)}>{t('ux.retry')}</button>{/if}<dl>
<dt title={t('ux.packageHint')}>{t('ux.package')}</dt>
<dd>{selected.package||t('ux.packageNeeded')}</dd>
</dl>
</Section>
        <Section id="selection-resources" title={t('ux.resources')}>
         {#each kinds as kind}{@const r=selected.resources[kind]}<button class="resource-row" onclick={()=>detail(selected)}>
<span class="resource-thumb">{#if r}<Preview compact {kind} pkg={r.package??selected.package} reference={r.reference??selected.ref}/>{:else}<Box size={20}/>{/if}</span>
<span class="resource-info">
<strong>{t(`ux.${kind}`)}</strong>
<span>{r?t(`ux.${r.source==='manufacturer'?'manufacturerSource':r.source}`):t('ux.missing')}</span>
</span>{#if r?.accepted}<Check class="success" size={14}/>{:else}<span class="secondary">{t(r?'ux.review':'ux.missing')}</span>{/if}<ChevronRight size={12}/>
</button>{/each}
        </Section>
        <div class="inspector-footer">
<button class="btn" onclick={()=>detail(selected)}>{t('ux.openDetail')}<ChevronRight size={14}/>
</button>
<span>{t('ux.simulated')}</span>
</div>
       {:else}<div class="empty-state">
<Cpu size={24}/>
<h2>{t('ux.select')}</h2>
<p>{t('ux.selectHint')}</p>
</div>{/if}
      </aside>{/if}
     </div>
    </section>
   {/if}
  </main>
 </div>
 <StatusBar>
<span class="sep">
</span>
<span>{t('ux.count',{n:catalogue.parts.length})}</span>
<span class="sep">
</span>
<span>{t('ux.noEngine')}</span>{#snippet right()}<span>{t('ux.demo')} · 02</span>{/snippet}</StatusBar>
</div>
{#if catalogue.storageFailed}<div class="storage-warning" role="alert">{t('ux.storage')}</div>{/if}
{#if dialog==='settings'}
 <Dialog title={t('ux.settings')} onclose={()=>dialog=null}>
<h3>{t('ux.scenario')}</h3>
<div class="scenario-list">{#each ['normal','empty','load','failure'] as s}<button class="btn" onclick={()=>setScenario(s)}>{t(`ux.${s}` as 'ux.normal')}</button>{/each}</div>
<h3>{t('ux.demoShort')}</h3>
<p class="secondary">{t('ux.resetHint')}</p>
<button class="btn" onclick={()=>{catalogue.reset();clear();page='library';dialog=null;}}>{t('ux.reset')}</button>
<p class="secondary">{t('ux.fileNote')}</p>
</Dialog>
{:else if dialog==='sync'}
 <Dialog title={t('ux.syncTitle')} width={620} onclose={()=>dialog=null}>
<p>{t('ux.syncExplain')}</p>{#each catalogue.parts.filter(p=>p.sync==='error'||p.sync==='syncing'||p.id===selectedId) as p}<div class="activity">
<strong>{p.ref}</strong>
<SyncState state={p.sync}/>{#if p.sync==='error'}<span>{t('ux.previous')}</span>
<button class="btn" onclick={()=>catalogue.sync(p.id)}>{t('ux.retry')}</button>{/if}</div>{/each}</Dialog>
{:else if dialog==='help'}
 <Dialog title={t('ux.help')} onclose={()=>dialog=null}>
<p>{t('ux.helpText')}</p>
<h3>{t('ux.demoShort')}</h3>
<p>{t('ux.notValidation')}</p>
<p>{t('ux.shortcuts')}</p>
</Dialog>
{:else if dialog==='roundtrip'}
 <Dialog title={t('ux.roundtripTitle')} onclose={()=>dialog=null}>
<p>{t('ux.roundtripText')}</p>
<p class="secondary">{t('ux.roundtripLimit')}</p>
</Dialog>
{:else if dialog==='edit'&&edit}
 <Dialog title={t('ux.editTitle')} width={580} onclose={()=>{dialog=null;edit=null;}}>
<div class="edit-form">
<label>{t('ux.reference')}<input class="input" bind:value={edit.ref}/>
</label>
<label>{t('ux.manufacturer')}<input class="input" bind:value={edit.manufacturer}/>
</label>
<label>{t('ux.package')}<input class="input" bind:value={edit.package}/>
</label>
<label>{t('ux.category')}<select class="input" bind:value={edit.category}>{#each categories as cat}<option value={cat}>{t(`ux.${cat}`)}</option>{/each}</select>
</label>
<label>{t('ux.description')}<input class="input" bind:value={edit.description[localeIndex]}/>
</label>
<div class="members">{#each ['Lab','Personnel'] as lib}<label>
<input type="checkbox" checked={edit.libraries.includes(lib as LibraryName)} onchange={()=>toggleEditLibrary(lib as LibraryName)}/>{lib==='Personnel'?t('ux.personal'):lib}</label>{/each}</div>
<p class="secondary small">{t('ux.rename')}</p>
{#if identityError}<p class="error" role="alert">{t('ux.duplicateReference')}</p>{/if}
</div>{#snippet footer()}<button class="btn" onclick={()=>dialog=null}>{t('ux.cancel')}</button>
<button class="btn primary" disabled={!edit?.ref.trim()||!edit?.libraries.length} onclick={saveIdentity}>{t('ux.saveChanges')}</button>{/snippet}</Dialog>
{/if}
