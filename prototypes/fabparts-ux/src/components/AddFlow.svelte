<script lang="ts">
import { untrack } from "svelte";
import {
  ArrowLeft,
  ArrowRight,
  Upload,
  FileText,
  Check,
  X,
  Search,
  Info,
  TriangleAlert,
  Files,
} from "@lucide/svelte";
import {
  proposal,
  kinds,
  copy,
  changePackage,
  changeIdentity,
  potentialReady,
  finish,
  sameReference,
  packageOptions,
  categories,
  type Part,
  type Kind,
  type Library,
} from "../lib/demo";
import { t, i18n } from "../lib/i18n.svelte";
import ResourceWorkspace from "./ResourceWorkspace.svelte";
import Readiness from "./Readiness.svelte";
import Preview from "./Preview.svelte";
import Disclosure from "./Disclosure.svelte";
let {
  existing,
  initialLibrary = "Lab",
  resume,
  oncancel,
  onsave,
  onexisting,
}: {
  existing: Part[];
  initialLibrary?: Library;
  resume?: Part | null;
  oncancel: () => void;
  onsave: (part: Part) => void;
  onexisting: (part: Part) => void;
} = $props();
const initial = untrack(() => (resume ? copy(resume) : null));
const initialFiles = initial
  ? kinds
      .filter((kind) => initial.resources[kind]?.source === "user")
      .map((kind) => ({ kind, name: initial.resources[kind]!.name }))
  : [];
let analysed = !!initial;
let analysedFiles: { name: string; kind: Kind }[] = copy(initialFiles);
let step = $state(initial ? 2 : 0),
  ref = $state(initial?.ref || ""),
  manufacturer = $state(initial?.manufacturer || ""),
  files = $state<{ name: string; kind: Kind }[]>(copy(initialFiles)),
  libraries = $state<Library[]>(
    initial?.libraries || [untrack(() => initialLibrary)],
  ),
  draft = $state<Part>(initial || proposal("", ""));
let loading = $state(false),
  error = $state(""),
  fail = $state(false),
  dragging = $state(false);
let input = $state<HTMLInputElement>();
const duplicate = $derived(
  existing.find((p) => p.id !== draft.id && sameReference(p.ref, draft.ref)),
);
const ambiguous = $derived(draft.ref.toUpperCase() === "NE555");
function toggleLibrary(lib: Library) {
  libraries = libraries.includes(lib)
    ? libraries.filter((l) => l !== lib)
    : [...libraries, lib];
}
function addFiles(list: FileList | null) {
  if (!list) return;
  for (const f of Array.from(list)) {
    const ext = f.name.split(".").pop()?.toLowerCase();
    const kind: Kind | undefined =
      ext === "pdf"
        ? "datasheet"
        : ext === "kicad_sym"
          ? "symbol"
          : ext === "kicad_mod"
            ? "footprint"
            : ["step", "stp", "wrl"].includes(ext || "")
              ? "model"
              : undefined;
    if (kind) {
      files = [
        ...files.filter((x) => x.name !== f.name),
        { name: f.name, kind },
      ];
      error = "";
    } else error = "unsupported";
  }
}
function sample(mode: string) {
  if (mode === "ref") {
    ref = "NE555";
    manufacturer = "";
    files = [];
  } else if (mode === "pdf") {
    manufacturer = "";
    ref = "STM32F103C8T6";
    files = [{ name: "stm32f103-datasheet.pdf", kind: "datasheet" }];
  } else {
    ref = "SENSOR-LAB-01";
    manufacturer = "Lab";
    files = [
      { name: "sensor.kicad_sym", kind: "symbol" },
      { name: "sensor.kicad_mod", kind: "footprint" },
      { name: "sensor.step", kind: "model" },
    ];
  }
}
async function analyse(manual = false) {
  if (!ref.trim() && !files.length) {
    error = "identityRequired";
    return;
  }
  if (!libraries.length) {
    error = "libraryRequired";
    return;
  }
  if (new Set(files.map((f) => f.kind)).size !== files.length) {
    error = "multipleRole";
    return;
  }
  error = "";
  loading = true;
  await new Promise((r) => setTimeout(r, 850));
  loading = false;
  if (fail && !manual) {
    error = "analysisError";
    return;
  }
  const reference = ref.trim() || files[0].name.replace(/\.[^.]+$/, "");
  draft = analysed
    ? changeIdentity(draft, reference, manufacturer)
    : proposal(reference, manufacturer);
  draft.libraries = [...libraries];
  for (const old of analysedFiles) {
    if (
      !files.some((f) => f.kind === old.kind && f.name === old.name) &&
      draft.resources[old.kind]?.name === old.name
    )
      delete draft.resources[old.kind];
  }
  for (const f of files) {
    if (analysedFiles.some((old) => old.kind === f.kind && old.name === f.name))
      continue;
    draft.resources[f.kind] = {
      name: f.name,
      source: "user",
      accepted: false,
      review: "choice",
      reference: draft.ref,
      package: draft.package,
    };
    draft.confirmed = false;
  }
  analysed = true;
  analysedFiles = copy(files);
  step = 1;
}
function goStep(next: number) {
  if (next === 0) {
    ref = draft.ref;
    manufacturer = draft.manufacturer;
  }
  step = next;
  error = "";
}
function choosePackage(pkg: string) {
  draft = changePackage(draft, pkg);
}
function save(confirm = false) {
  draft.libraries = [...libraries];
  if (!draft.ref.trim()) {
    error = "identityRequired";
    return;
  }
  if (!libraries.length) {
    error = "libraryRequired";
    return;
  }
  if (duplicate) {
    error = "duplicateReference";
    return;
  }
  if (confirm && potentialReady(draft) === "draft") return;
  onsave(finish(draft, confirm));
}
function addMembership() {
  if (!duplicate || !libraries.length) {
    error = "libraryRequired";
    return;
  }
  const next = copy(duplicate);
  next.libraries = [...new Set([...next.libraries, ...libraries])];
  onsave(next);
}
</script>
<section class="add-flow">
 <header class="page-heading">
<button class="btn quiet" onclick={()=>step>0?goStep(step-1):oncancel()}>
<ArrowLeft size={14}/>{step>0?t('ux.previousStep'):t('ux.back')}</button>
<h1>{initial?t('ux.resume'):t('ux.add')}</h1>
<span class="secondary">{t('ux.demoShort')}</span>
</header>
 <nav class="steps" aria-label={t('ux.add')}>{#each ['stepInput','stepIdentify','stepReview'] as label,i}<button class:active={step===i} disabled={i>step||loading} onclick={()=>goStep(i)}>
<span>{step>i?'✓':i+1}</span>{t(`ux.${label}` as 'ux.stepInput')}{#if i<2}<ArrowRight size={12}/>{/if}</button>{/each}</nav>
 <div class="flow-body">
  {#if step===0}
   <div class="intro">
<h2>{t('ux.inputTitle')}</h2>
<p>{t('ux.inputHint')}</p>
</div>
   <div class="input-columns">
    <div class="form-section">
<h3>{t('ux.stepInput')}</h3>
<label>{t('ux.reference')}<input class="input" bind:value={ref} placeholder="NE555, STM32F103C8T6…" disabled={loading}/>
</label>
<label>
<span>{t('ux.manufacturer')} <span class="secondary">· {t('ux.optionalField')}</span>
</span>
<input class="input" bind:value={manufacturer} placeholder="Texas Instruments, STMicroelectronics…" disabled={loading}/>
</label>
      <div class="memberships">
<span>{t('ux.libraryTarget')}</span>
<div>{#each ['Lab','Personnel'] as lib}<label>
<input type="checkbox" checked={libraries.includes(lib as Library)} onchange={()=>toggleLibrary(lib as Library)}/>{lib==='Personnel'?t('ux.personal'):lib}</label>{/each}</div>
</div>
      <Disclosure id="analysis-scenario" label={t('ux.scenario')}>
<label class="check">
<input type="checkbox" bind:checked={fail}/>{t('ux.simulateFailure')}</label>
</Disclosure>
    </div>
    <div class="form-section">
<h3>{t('ux.files')}</h3>
     <div class="drop" class:dragging role="region" aria-label={t('ux.drop')} ondragover={(e)=>{e.preventDefault();dragging=true;}} ondragleave={()=>dragging=false} ondrop={(e)=>{e.preventDefault();dragging=false;addFiles(e.dataTransfer?.files||null);}}>
<Upload size={24}/>
<strong>{t('ux.drop')}</strong>
<span>{t('ux.formats')}</span>
<button class="btn" onclick={()=>input?.click()} disabled={loading}>{t('ux.browse')}</button>
</div>
     <input bind:this={input} class="sr-only" tabindex="-1" type="file" multiple accept=".pdf,.kicad_sym,.kicad_mod,.step,.stp,.wrl" onchange={(e)=>addFiles(e.currentTarget.files)} aria-label={t('ux.browse')}/>
     {#each files as file,i}<div class="file-row">
<FileText size={14}/>
<span>{file.name}</span>
<select class="input" aria-label={file.name} bind:value={file.kind}>{#each ['symbol','footprint','model','datasheet'] as k}<option value={k}>{t(`ux.${k}` as 'ux.symbol')}</option>{/each}</select>
<button class="btn quiet icon" aria-label={t('ux.removeFile')} onclick={()=>files=files.filter((_,n)=>n!==i)}>
<X size={13}/>
</button>
</div>{/each}
     <p class="small secondary">{t('ux.fileNote')}</p>
    </div>
   </div>
<div class="samples">
<h3>{t('ux.samples')}</h3>
<div>
<button class="btn" onclick={()=>sample('ref')}>{t('ux.sampleRef')}</button>
<button class="btn" onclick={()=>sample('pdf')}>
<FileText size={14}/>{t('ux.samplePdf')}</button>
<button class="btn" onclick={()=>sample('files')}>
<Files size={14}/>{t('ux.sampleFiles')}</button>
</div>
</div>
  {:else if step===1}
   <div class="intro">
<h2>{t('ux.identifyTitle')}</h2>
<p>{ambiguous?t('ux.ambiguousHint'):draft.package?t('ux.knownHint'):t('ux.unknownHint')}</p>
</div>
   <div class="input-columns">
    <div class="form-section">
<h3>{t('ux.component')}</h3>
     <label>{t('ux.reference')}<input class="input" value={draft.ref} oninput={(e)=>draft=changeIdentity(draft,e.currentTarget.value,draft.manufacturer)}/>
</label>
<label>{t('ux.manufacturer')}<input class="input" value={draft.manufacturer} oninput={(e)=>draft=changeIdentity(draft,draft.ref,e.currentTarget.value)}/>
</label>
<label>{t('ux.description')}<input class="input" bind:value={draft.description[i18n.locale==='fr'?0:1]}/>
</label>
<label>{t('ux.category')}<select class="input" bind:value={draft.category}>{#each categories as cat}<option value={cat}>{t(`ux.${cat}`)}</option>{/each}</select>
</label>
<span class="secondary small">{t('ux.matching')} · {t('ux.simulated')}</span>
    </div>
    <div class="form-section">
<h3 title={t('ux.packageHint')}>{t('ux.package')} <Info size={12}/>
</h3>
     {#if ambiguous}<div class="package-choices">{#each packageOptions as pkg}<button class:selected={draft.package===pkg} aria-pressed={draft.package===pkg} onclick={()=>choosePackage(pkg)}>
<Preview kind="model" {pkg} reference={draft.ref}/>
<strong>{pkg}</strong>
<span>{pkg==='DIP-8'?t('ux.throughHole'):t('ux.smd')}</span>
</button>{/each}</div>{:else}<Preview kind="model" pkg={draft.package} reference={draft.ref}/>
<label>{t('ux.package')}<input class="input" value={draft.package} oninput={(e)=>choosePackage(e.currentTarget.value)} placeholder="LQFP-48, SOIC-8…"/>
</label>{/if}
     <p class="small secondary">{t('ux.packageSource')}</p>
<button class="btn quiet" onclick={()=>choosePackage('')}>{t('ux.later')}</button>
    </div>
   </div>
   {#if duplicate}<div class="duplicate">
<strong>{t('ux.existing')} · {duplicate.ref}</strong>
<p>{t('ux.existingHint')}</p>
<div class="row">
<button class="btn" onclick={()=>onexisting(duplicate)}>{t('ux.seeExisting')}</button>
<button class="btn" onclick={addMembership}>{t('ux.addMembership')}</button>
<button class="btn quiet" onclick={()=>{draft=changeIdentity(draft,draft.ref+' · variante',draft.manufacturer);}}>{t('ux.variant')}</button>
</div>
</div>{/if}
  {:else}
   <div class="intro review-intro">
<div>
<h2>{draft.ref} <span class="secondary">· {draft.manufacturer} · {draft.package||t('ux.packageNeeded')}</span>
</h2>
<p>{t('ux.reviewHint')}</p>
</div>
<button class="btn" onclick={()=>goStep(1)}>{draft.package?t('ux.modify'):t('ux.choosePackage')}</button>
</div>
   <ResourceWorkspace part={draft} onupdate={(p)=>draft=p}/>
   <div class="review-bottom">
<div>
<span class="small secondary">{t('ux.confirmHint')}</span> <Readiness state={potentialReady(draft)}/>

</div>
<span class="small secondary">{t('ux.draftHint')}</span>
</div>
   <div class="memberships">
<span>{t('ux.libraryTarget')}</span>
<div>{#each ['Lab','Personnel'] as lib}<label>
<input type="checkbox" checked={libraries.includes(lib as Library)} onchange={()=>toggleLibrary(lib as Library)}/>{lib==='Personnel'?t('ux.personal'):lib}</label>{/each}</div>
</div>
   {#if potentialReady(draft)==='draft'}<p class="small secondary">{t('ux.confirmBlocked')}</p>{/if}
   <p class="small secondary"><Info size={12}/>{t('ux.notValidation')}</p>
  {/if}
  {#if error}<div class="notice error" role="alert">
<TriangleAlert size={15}/>{t(`ux.${error}` as 'ux.analysisError')}{#if error==='analysisError'}<button class="btn" onclick={()=>analyse(true)}>{t('ux.manual')}</button>{/if}</div>{/if}
  {#if loading}<div class="notice" role="status">
<Search size={16}/>
<div>
<strong>{t('ux.analysing')}</strong>
<p>{t('ux.analysisHint')}</p>
</div>
</div>{/if}
 </div>
 <footer class="flow-footer">
<button class="btn" onclick={()=>step>0?goStep(step-1):oncancel()} disabled={loading}>{step>0?t('ux.previousStep'):t('ux.cancel')}</button>
<span class="secondary small">{t('ux.demoShort')} · {t('ux.noEngine')}</span>
<div class="grow">
</div>{#if step===0}<button class="btn primary" disabled={loading} onclick={()=>analyse()}>
<Search size={14}/>{t('ux.analyse')}</button>{:else if step===1}<button class="btn primary" disabled={!!duplicate||!draft.ref.trim()} onclick={()=>{step=2;error='';}}>{t('ux.next')}<ArrowRight size={14}/>
</button>{:else}<button class="btn" onclick={()=>save(false)} disabled={!!duplicate||!draft.ref.trim()||!libraries.length}>{t('ux.saveDraft')}</button><button class="btn primary" disabled={!!duplicate||!draft.ref.trim()||!libraries.length||potentialReady(draft)==='draft'} title={potentialReady(draft)==='draft'?t('ux.confirmBlocked'):t('ux.notValidation')} onclick={()=>save(true)}><Check size={14}/>{t('ux.save')}</button>{/if}</footer>
</section>
<style>
.add-flow {
  display: grid;
  grid-template-rows: auto auto 1fr auto;
  min-height: 0;
  height: 100%;
}
.page-heading {
  display: flex;
  align-items: center;
  gap: 12px;
  height: 48px;
  padding: 0 12px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-panel);
}
h1,
h2 {
  font-size: var(--fs-lg);
  font-weight: 600;
  margin: 0;
}
.page-heading > span {
  margin-left: auto;
}
.steps {
  display: flex;
  padding: 0 24px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-panel);
  gap: 24px;
}
.steps button {
  display: flex;
  align-items: center;
  gap: 8px;
  border: 0;
  border-bottom: 2px solid transparent;
  background: none;
  color: var(--text-secondary);
  height: 42px;
  font-size: var(--fs-sm);
}
.steps button.active {
  color: var(--text-primary);
  border-color: var(--accent);
}
.steps button:disabled {
  opacity: 0.5;
}
.steps button span {
  display: grid;
  place-items: center;
  width: 18px;
  height: 18px;
  border: 1px solid var(--border-strong);
  border-radius: 50%;
  font-size: var(--fs-xs);
}
.flow-body {
  overflow: auto;
  padding: 16px 24px;
  max-width: 1180px;
  width: 100%;
  margin: 0 auto;
}
.intro {
  margin-bottom: 24px;
}
.intro p {
  margin: 8px 0 0;
  color: var(--text-secondary);
  font-size: var(--fs-sm);
}
.input-columns {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 32px;
}
.form-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 0;
}
h3 {
  font-size: var(--fs-xs);
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--text-section);
  margin: 0 0 4px;
  display: flex;
  gap: 8px;
  align-items: center;
}
.form-section label {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: var(--fs-sm);
  color: var(--text-secondary);
}
.form-section label input {
  color: var(--text-primary);
}
.memberships {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  font-size: var(--fs-sm);
  margin: 8px 0;
}
.memberships > span {
  color: var(--text-secondary);
}
.memberships > div {
  display: flex;
  gap: 20px;
}
.memberships label,
.form-section label.check {
  flex-direction: row;
  display: flex;
  align-items: center;
  gap: 6px;
}
.drop {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  justify-content: center;
  height: 180px;
  border: 1px dashed var(--border-strong);
  color: var(--text-secondary);
  background: var(--bg-panel);
}
.drop.dragging {
  border-color: var(--accent);
  background: var(--bg-selected);
}
.drop span {
  font-size: var(--fs-xs);
}
.samples {
  border-top: 1px solid var(--border);
  margin-top: 32px;
  padding-top: 16px;
}
.samples > div {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}
.file-row {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.file-row > span {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: var(--fs-sm);
}
.file-row select {
  max-width: 110px;
}
.secondary {
  color: var(--text-secondary);
}
.small {
  font-size: var(--fs-sm);
}
.small :global(svg) {
  vertical-align: middle;
  margin-right: 6px;
}
.package-choices {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.package-choices button {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 0 0 12px;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  color: var(--text-primary);
}
.package-choices button.selected {
  border-color: var(--accent);
  background: var(--bg-selected);
}
.package-choices button :global(.preview) {
  width: 100%;
  height: 145px;
}
.package-choices strong,
.package-choices span {
  padding: 0 12px;
}
.package-choices span {
  font-size: var(--fs-xs);
  color: var(--text-secondary);
}
.review-intro {
  display: flex;
  justify-content: space-between;
  align-items: start;
  gap: 16px;
  margin-bottom: 12px;
}
.review-intro h2 span {
  font-weight: 400;
}
.flow-body :global(.preview-button),
.flow-body :global(.missing) {
  height: 112px;
}
.review-bottom {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 16px;
}
.flow-footer {
  flex-wrap: wrap;
  display: flex;
  gap: 12px;
  align-items: center;
  padding: 12px 16px;
  border-top: 1px solid var(--border);
  background: var(--bg-panel);
}
.grow {
  flex: 1;
}
.notice {
  display: flex;
  align-items: center;
  gap: 12px;
  border-left: 2px solid var(--info);
  padding: 12px;
  margin-top: 16px;
  color: var(--info);
}
.notice p {
  margin: 4px 0 0;
  font-size: var(--fs-sm);
}
.error {
  color: var(--danger-text);
  border-color: var(--danger);
}
.duplicate {
  border-top: 1px solid var(--border);
  padding-top: 16px;
  margin-top: 16px;
}
.duplicate p {
  color: var(--text-secondary);
}
.row {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
@media (max-width: 1000px) {
  .flow-body {
    padding: 16px;
  }
  .steps {
    gap: 12px;
    padding: 0 12px;
  }
  .input-columns {
    gap: 20px;
  }
  .flow-footer > span {
    display: none;
  }
}
@media (max-width: 750px) {
  .input-columns {
    grid-template-columns: 1fr;
  }
  .steps {
    gap: 4px;
  }
  .steps button {
    font-size: var(--fs-xs);
  }
  .steps :global(svg) {
    display: none;
  }
  .flow-body :global(.preview-button),
  .flow-body :global(.missing) {
    height: 112px;
  }
  .review-bottom {
    align-items: start;
    flex-direction: column;
  }
}
</style>
