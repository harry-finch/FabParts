<script lang="ts">
import { onMount } from 'svelte';
import { invoke } from '@tauri-apps/api/core';
import { Search, Library, Layers, Cpu, Folder, Plus, LockKeyhole, Moon, Sun, Monitor, X, RefreshCw, TriangleAlert, PanelRightClose, PanelRightOpen, ChevronRight, ArrowLeft } from '@lucide/svelte';
import Section from '../../fabparts-ux/src/components/Section.svelte';
import Disclosure from '../../fabparts-ux/src/components/Disclosure.svelte';
import StatusBar from '../../fabparts-ux/src/components/StatusBar.svelte';
import { theme, THEMES } from '../../fabparts-ux/src/lib/theme.svelte';
import { i18n, LOCALES } from '../../fabparts-ux/src/lib/i18n.svelte';
import { Controller, initial, defaultQuery, type Snapshot } from './controller';
import { text as t, stateLabel } from './text';
import Details from './Details.svelte';
let view = $state<Snapshot>(initial());
const controller = new Controller(invoke, next => view = next);
let query = $state(defaultQuery());
let inspector = $state(true), full = $state(false), panelWidth = $state(320);
let copyPath = $state('');
let searchInput = $state<HTMLInputElement>();
$effect(() => { const q = {...query}; const timer = setTimeout(() => void controller.load(q), 180); return () => clearTimeout(timer); });
onMount(() => { void controller.start(); const timer = setInterval(() => void controller.heartbeat(), 3000); return () => { clearInterval(timer); controller.dispose(); }; });
function clear() { query = defaultQuery(); }
function keydown(event: KeyboardEvent) {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); full = false; setTimeout(() => searchInput?.focus()); }
  if (event.key === 'Escape' && !document.querySelector('dialog[open]')) full = false;
}
function resize(event: PointerEvent) {
  const start = event.clientX, width = panelWidth;
  const move = (e: PointerEvent) => panelWidth = Math.max(280, Math.min(440, width + start - e.clientX));
  const end = () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', end); };
  window.addEventListener('pointermove', move); window.addEventListener('pointerup', end);
}
</script>
<svelte:window onkeydown={keydown}/>
<div class="app-shell">
  <header class="appbar"><div class="brand"><img src="/logo.svg" alt=""/><strong>FabParts</strong></div><span class="tagline">{t('libraries')}</span><span class="demo-label">TECH-01 <span>{t('copy')}</span></span>
    <div class="bar-right"><div class="mini-segments">{#each LOCALES as locale}<button class:on={i18n.locale === locale.id} onclick={() => i18n.set(locale.id)}>{locale.id.toUpperCase()}</button>{/each}</div>
    <div class="mini-segments">{#each THEMES as choice}<button class:on={theme.choice === choice} onclick={() => theme.set(choice)} aria-label={choice} title={choice}>{#if choice === 'dark'}<Moon size={14}/>{:else if choice === 'light'}<Sun size={14}/>{:else}<Monitor size={14}/>{/if}</button>{/each}</div></div>
  </header>
  <div class="workspace">
    <aside class="sidebar"><div class="sidebar-top"><Library size={17}/><strong>{t('libraries')}</strong></div>
      <Section id="tech-libraries" title={t('libraries')}>
        <button class="nav-row" class:active={query.library === 'all'} onclick={() => { query = {...query,library:'all',offset:0}; full=false; }}><Layers size={14}/><span>{t('all')}</span></button>
        {#each view.libraries as library}<button class="nav-row" class:active={query.library === library.id} onclick={() => { query = {...query,library:library.id,offset:0}; full=false; }}><Folder size={14}/><span>{library.name}</span><small>{library.count}</small></button>{/each}
      </Section>
      <Section id="tech-categories" title={t('categories')}>
        <button class="nav-row" class:active={!query.category} onclick={() => { query.category='';query.offset=0;full=false; }}><Layers size={14}/><span>{t('allCategories')}</span></button>
        {#each view.page.facets.categories as category}<button class="nav-row" class:active={query.category === category} onclick={() => { query.category=category;query.offset=0;full=false; }}><Cpu size={14}/><span>{category}</span></button>{/each}
      </Section>
      <div class="sidebar-bottom"><LockKeyhole size={14}/><div><p>{t('readonly')}</p>{#if view.health}<Disclosure id="tech-engine" label={t('technical')}><p class="engine-metadata">PID {view.health.pid}<br/>Python {view.health.engine_version}<br/>Qt {String(view.health.qt_loaded)}<br/>{view.health.schema}</p></Disclosure>{/if}</div></div>
    </aside>
    <main>
      {#if full && view.phase === 'ready'}
        <section class="detail-page"><div class="detail-toolbar"><button class="btn quiet" onclick={() => full=false}><ArrowLeft size={15}/>{t('back')}</button><span class="crumb">/</span><span>{view.detail?.reference || t('loading')}</span></div>
          <div class="detail-content">{#if view.detail}<Details detail={view.detail} full/>{:else}<div class="empty-state">{t('loading')}</div>{/if}</div>
        </section>
      {:else}
      <section class="library-page">
        <div class="library-toolbar"><h1>{query.library === 'all' ? t('all') : view.libraries.find(l => l.id === query.library)?.name || t('libraries')}</h1><span class="grow"></span><button class="btn" disabled title={t('noWrite')}><Plus size={14}/>{t('add')}</button></div>
        <div class="filterbar"><div class="search"><Search size={15}/><input bind:this={searchInput} bind:value={query.search} oninput={() => query.offset=0} aria-label={t('search')} placeholder={t('search')}/>{#if query.search}<button class="btn quiet icon" aria-label={t('clear')} onclick={() => {query.search='';query.offset=0;}}><X size={13}/></button>{:else}<kbd>⌘ K</kbd>{/if}</div>
          <select class="input" bind:value={query.state} onchange={() => query.offset=0} aria-label={t('state')}><option value="">{t('allStates')}</option>{#each ['DRAFT','IDENTIFIED','DEPRECATED'] as s}<option value={s}>{stateLabel(s)}</option>{/each}</select>
          <select class="input package-filter" bind:value={query.package} onchange={() => query.offset=0} aria-label={t('package')}><option value="">{t('allPackages')}</option>{#each view.page.facets.packages as p}<option value={p}>{p}</option>{/each}</select>
          <button class="btn quiet icon" aria-label={t(inspector ? 'closeInspector' : 'openInspector')} title={t(inspector ? 'closeInspector' : 'openInspector')} onclick={() => inspector=!inspector}>{#if inspector}<PanelRightClose size={16}/>{:else}<PanelRightOpen size={16}/>{/if}</button>
        </div>
        <div class="catalogue" class:no-inspector={!inspector} style:--inspector-width={`${panelWidth}px`}>
          <div class="list-region" aria-busy={view.loading || view.phase === 'starting'}>
            <div class="result-context"><span>{query.category || t('component')}</span><span>{view.page.total} {t('results')}</span></div>
            {#if view.phase === 'failed'}<div class="empty-state" role="alert"><TriangleAlert size={28}/><h2>{t('failed')}</h2><p>{view.error?.message}</p><span class="secondary small">{view.error?.code}</span>{#if ['DATA_DIR_REQUIRED','INVALID_DATA_DIR','STARTUP_FAILED'].includes(view.error?.code || '')}<label class="copy-path">{t('copyDirectory')}<input class="input" bind:value={copyPath} placeholder="/…/catalogue-copy"/></label>{/if}<button class="btn primary" onclick={() => { if (copyPath.trim()) controller.dataDir=copyPath.trim(); void controller.start(); }}><RefreshCw size={14}/>{t('restart')}</button></div>
            {:else if view.phase === 'starting' || view.loading}<div class="empty-state" role="status"><RefreshCw size={26}/><h2>{t(view.phase === 'starting' ? 'starting' : 'loading')}</h2></div>
            {:else if !view.page.components.length}<div class="empty-state"><Library size={28}/><h2>{t('empty')}</h2><p>{t('emptyHint')}</p><button class="btn" onclick={clear}>{t('clear')}</button></div>
            {:else}<div class="table-scroll"><table><thead><tr><th>{t('component')}</th><th>{t('package')}</th><th>{t('state')}</th><th class="library-cell">{t('libraries')}</th></tr></thead><tbody>
              {#each view.page.components as component}<tr class:selected={view.selectedId === component.id}><td><button class="row-select" aria-pressed={view.selectedId === component.id} onclick={() => void controller.select(component.id)} ondblclick={() => {void controller.select(component.id);full=true;}}><span class="part-icon"><Cpu size={18}/></span><span class="part-name"><strong>{component.reference}</strong><span title={component.description}>{component.manufacturer ? component.manufacturer + ' · ' : ''}{component.description || t('unknown')}</span></span></button></td><td class="pkg-cell" title={component.package?.name}>{component.package?.name || '—'}</td><td>{stateLabel(component.state)}</td><td class="library-cell" title={component.libraries.map(l => l.name).join(' · ')}>{component.libraries.map(l => l.name).join(' · ') || '—'}</td></tr>{/each}
            </tbody></table></div>{/if}
            <div class="list-bottom"><span>{view.page.offset + (view.page.components.length ? 1 : 0)}–{view.page.offset + view.page.components.length} / {view.page.total}</span><div class="pagination"><button class="btn quiet" disabled={query.offset === 0 || view.loading} onclick={() => query.offset=Math.max(0,query.offset-query.limit)}>{t('previous')}</button><button class="btn quiet" disabled={query.offset+query.limit >= view.page.total || view.loading} onclick={() => query.offset+=query.limit}>{t('next')}</button></div>{#if view.detail}<button class="btn quiet" onclick={() => full=true}>{t('details')}<ChevronRight size={13}/></button>{/if}</div>
          </div>
          {#if inspector}<aside class="inspector"><button class="resize-handle" onpointerdown={resize} onkeydown={e => { if (e.key === 'ArrowLeft') panelWidth=Math.min(440,panelWidth+20); if (e.key === 'ArrowRight') panelWidth=Math.max(280,panelWidth-20); }} aria-label={t('resize')} title={t('resize')}></button>
            {#if view.detail}<Details detail={view.detail}/><div class="inspector-footer"><button class="btn" onclick={() => full=true}>{t('details')}<ChevronRight size={14}/></button></div>{:else}<div class="empty-state"><Cpu size={24}/><p>{t(view.detailLoading ? 'loading' : 'select')}</p></div>{/if}
          </aside>{/if}
        </div>
      </section>{/if}
    </main>
  </div>
  <StatusBar state={view.phase === 'failed' ? 'failed' : view.phase === 'starting' || view.loading ? 'loading' : 'ready'} version={view.health?.engine_version}><span class="sep"></span><span>{t('copy')}</span>{#snippet right()}<span>TECH-02A · IPC v1</span>{/snippet}</StatusBar>
</div>

<style>
.copy-path{display:flex;flex-direction:column;gap:8px;width:min(460px,90%);text-align:left;font-size:var(--fs-sm)}
.pagination{display:flex;gap:4px}.engine-metadata{overflow-wrap:anywhere}
.nav-row span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
</style>
