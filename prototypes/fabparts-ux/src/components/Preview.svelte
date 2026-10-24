<script lang="ts">
import {
  contactCount,
  illustratedPackage,
  ne555Labels,
  sameReference,
  type Kind,
} from "../lib/demo";
import { t } from "../lib/i18n.svelte";
let {
  kind,
  pkg = "LQFP-48",
  reference = "U1",
  zoom = 1,
  compact = false,
}: {
  kind: Kind;
  pkg?: string;
  reference?: string;
  zoom?: number;
  compact?: boolean;
} = $props();
const count = $derived(contactCount(reference, pkg));
const pins = $derived(
  Array.from({ length: count ? Math.ceil(count / 2) : 0 }, (_, i) => i),
);
const is555 = $derived(sameReference(reference, "NE555"));
const hasDrawing = $derived(
  kind === "datasheet" ||
    (kind === "symbol" ? !!count : illustratedPackage(pkg)),
);
const pads = $derived.by(() => {
  if (!count) return [];
  const quad = /^(LQFP|TQFP|QFN)-/.test(pkg),
    sides = quad ? 4 : 2,
    perSide = count / sides;
  return Array.from({ length: count }, (_, i) => {
    const side = Math.floor(i / perSide),
      step = i % perSide;
    const pos = ((step + 0.5) * 100) / perSide;
    if (quad && side === 1)
      return { n: i + 1, x: 110 + pos, y: 140, vertical: true };
    if (quad && side === 3)
      return { n: i + 1, x: 210 - pos, y: 30, vertical: true };
    return {
      n: i + 1,
      x: side === 0 ? 103 : 217,
      y: side === 0 ? 35 + pos : 135 - pos,
      vertical: false,
    };
  });
});
const passive = $derived(pkg === "0603" || pkg === "0805");
const capacitor = $derived(
  reference.startsWith("GRM") || reference.startsWith("CL"),
);
</script>
<div class="preview" class:compact class:pdf={kind==='datasheet'}>
  <svg data-contacts={hasDrawing?count:undefined} viewBox="0 0 320 170" role="img" aria-label={`${t(`ux.${kind}`)} · ${t('ux.illustration')}`}>
    <g transform={`translate(160,85) scale(${zoom}) translate(-160,-85)`}>
      {#if !hasDrawing}
        <text x="160" y="78" class="label">{t('ux.unillustrated')}</text>
        <text x="160" y="98" class="small">{pkg||t('ux.packageNeeded')}</text>
      {:else if passive && kind==='symbol'}
        <text x="160" y="44" class="small">{capacitor?'C1':'R1'}</text>
        {#if capacitor}
          <path class="pin" d="M80 85 H152 M168 85 H240"/>
          <path class="silk" d="M152 62 V108 M168 62 V108"/>
        {:else}
          <path class="pin" d="M80 85 H130 M190 85 H240"/>
          <rect class="body" x="130" y="73" width="60" height="24"/>
        {/if}
        <circle class="point" cx="80" cy="85" r="2"/><circle class="point" cx="240" cy="85" r="2"/>
        <text x="160" y="130" class="small">{reference}</text>
      {:else if passive && kind==='footprint'}
        <rect class="courtyard" x="96" y="43" width="128" height="84"/>
        <rect class="pad" x="105" y="57" width="36" height="56" rx="2"/>
        <rect class="pad" x="179" y="57" width="36" height="56" rx="2"/>
        <path class="silk" d="M145 62 H175 M145 108 H175"/>
        <text class="pad-number" x="123" y="87">1</text><text class="pad-number" x="197" y="87">2</text>
        <text class="small" x="160" y="146">{pkg}</text>
      {:else if passive && kind==='model'}
        <path class="side" d="M88 68 L190 110 L235 87 V104 L190 127 L88 85 Z"/>
        <path class="top" d="M88 68 L133 45 L235 87 L190 110 Z"/>
        <path class="leg" d="M88 68 L133 45 L148 51 L103 74 V91 L88 85 Z M175 104 L220 81 L235 87 V104 L190 127 V110 Z"/>
        <text x="160" y="86" class="model-label" transform="rotate(22,160,86)">{pkg}</text>
      {:else if kind==='symbol'}
        <rect class="body" x="108" y="24" width="104" height="122" />
        <text x="160" y="16" class="small">{reference}</text>
        {#if !is555}<text x="160" y="84" class="small">{pkg}</text>{/if}
        {#each pins as i}
          {@const y=32+(i+.5)*106/pins.length}
          <g data-contact={i+1}>
            <path class="pin" d={`M76 ${y} H108`}/><circle class="point" cx="76" cy={y} r="2"/>
            <text x="96" y={y-3} class="pin-label">{i+1}</text>
            {#if is555}<text x="115" y={y+3} class="signal left">{ne555Labels[i]}</text>{/if}
          </g>
          <g data-contact={count!-i}>
            <path class="pin" d={`M212 ${y} H244`}/><circle class="point" cx="244" cy={y} r="2"/>
            <text x="224" y={y-3} class="pin-label">{count!-i}</text>
            {#if is555}<text x="205" y={y+3} class="signal right">{ne555Labels[count!-i-1]}</text>{/if}
          </g>
        {/each}
      {:else if kind==='footprint'}
        <rect class="courtyard" x="77" y="13" width="166" height="144"/>
        <path class="silk" d="M108 34 H212 V136 H108 V45 L119 34"/>
        {#each pads as pad}
          <g data-contact={pad.n}>
            {#if pkg.startsWith('DIP-')}
              {#if pad.n===1}<rect class="pad" x={pad.x-6} y={pad.y-6} width="12" height="12"/>{:else}<circle class="pad" cx={pad.x} cy={pad.y} r={Math.min(6,40/pins.length)}/>{/if}
              <circle class="drill" cx={pad.x} cy={pad.y} r={Math.min(2.5,18/pins.length)}/>
            {:else}<rect class="pad" x={pad.x-(pad.vertical?3:12)} y={pad.y-(pad.vertical?9:Math.min(5,40/pins.length))} width={pad.vertical?6:24} height={pad.vertical?18:Math.min(10,80/pins.length)} rx="1"/>{/if}
            <text class="pad-number" x={pkg.startsWith('DIP-')?pad.x+(pad.x<160?-12:12):pad.x} y={pad.y+2}>{pad.n}</text>
          </g>
        {/each}
        <path class="cross" d="M151 85 H169 M160 76 V94"/>
        <text class="small" x="160" y="116">{pkg}</text>
      {:else if kind==='model'}
        {#if pkg==='DIP-8'||pkg==='SOIC-8'}
          {#each [0,1,2,3] as i}
            <path data-contact={i+1} class="leg" d={pkg==='DIP-8'?`M${101+i*25} ${75+i*10} l-10 5 v29 l7 3 V91 Z`:`M${101+i*25} ${75+i*10} l-13 6 v8 l-7 3 l8 4 l7 -4 v-6 l13 -6 Z`}/>
            <path data-contact={8-i} class="leg" d={pkg==='DIP-8'?`M${144+i*25} ${45+i*10} l9 -4 l5 3 v29 l-6 3 V55 Z`:`M${144+i*25} ${45+i*10} l13 -6 l9 5 v7 l10 5 l-9 4 l-9 -6 v-7 l-12 6 Z`}/>
          {/each}
          <path class="side" d="M87 57 L196 103 L239 81 V95 L196 117 L87 71 Z"/>
          <path class="top" d="M87 57 L130 35 L239 81 L196 103 Z"/>
          <circle class="mark" cx="105" cy="57" r="3"/>
          <text x="164" y="73" class="model-label" transform="rotate(23,164,73)">{pkg}</text>
        {:else}
        <g transform="matrix(.9 .32 -.65 .4 65 -1)">
          {#each pads as pad}<rect data-contact={pad.n} class="leg" x={pad.x-(pad.vertical?3:12)} y={pad.y-(pad.vertical?10:3)} width={pad.vertical?6:24} height={pad.vertical?20:6}/>{/each}
          <path class="side" d="M110 35 H210 V135 H110 Z" transform="translate(0,12)"/>
          <rect class="top" x="110" y="35" width="100" height="100"/>
          <circle class="mark" cx="121" cy="46" r="3"/>
          <text x="160" y="87" class="model-label">{pkg}</text>
        </g>
        {/if}
      {:else}
        <rect class="paper" x="87" y="9" width="146" height="153"/>
        <text class="pdf-heading" x="101" y="32">{reference}</text>
        <text class="pdf-sub" x="101" y="45">DATASHEET · DEMO</text>
        <path class="pdf-line" d="M101 57 H219 M101 64 H210 M101 71 H219 M101 84 H155 M101 91 H155 M101 98 H155 M101 105 H151 M101 123 H219 M101 130 H219 M101 137 H205"/>
        <rect class="pdf-diagram" x="178" y="81" width="27" height="26"/>
        <path class="pdf-line" d="M169 85 H178 M169 93 H178 M169 101 H178 M205 85 H214 M205 93 H214 M205 101 H214"/>
      {/if}
    </g>
  </svg>
  <span class="preview-caption">{t('ux.illustration')}</span>
</div>
<style>
.preview {
  position: relative;
  min-height: 125px;
  height: 100%;
  overflow: hidden;
  background: var(--bg-workspace);
  display: grid;
  place-items: center;
}
svg {
  width: 100%;
  height: 100%;
  max-height: 220px;
  min-height: 125px;
}
text {
  font-family: var(--mono);
  text-anchor: middle;
  fill: var(--text-primary);
}
.body {
  fill: var(--bg-panel);
  stroke: var(--text-secondary);
  stroke-width: 1.4;
}
.label {
  font-size: 10px;
}
.small {
  fill: var(--text-secondary);
  font-size: 8px;
}
.pin {
  stroke: var(--accent-text);
  stroke-width: 1.3;
}
.point {
  fill: var(--bg-workspace);
  stroke: var(--accent-text);
}
.signal {
  font-size: 8px;
}
.signal.left {
  text-anchor: start;
}
.signal.right {
  text-anchor: end;
}
.pin-label {
  font-size: 7px;
  fill: var(--accent-text);
}
.courtyard {
  fill: none;
  stroke: var(--text-muted);
  stroke-dasharray: 4 4;
}
.silk {
  fill: none;
  stroke: var(--info);
  stroke-width: 1.3;
}
.pad {
  fill: var(--danger);
  fill-opacity: 0.65;
  stroke: var(--danger);
}
.drill {
  fill: var(--bg-workspace);
}
.pad-number {
  font-size: 6px;
  fill: var(--text-primary);
}
.cross {
  stroke: var(--text-muted);
  fill: none;
}
.leg {
  fill: var(--text-secondary);
  stroke: var(--border-strong);
}
.top {
  fill: var(--bg-elevated);
  stroke: var(--text-muted);
}
.side {
  fill: var(--bg-control);
  stroke: var(--border-strong);
}
.mark {
  fill: var(--text-secondary);
}
.model-label {
  font-size: 9px;
  fill: var(--text-secondary);
}
.paper {
  fill: var(--bg-panel);
  stroke: var(--border-strong);
}
.pdf-heading {
  text-anchor: start;
  font-size: 10px;
}
.pdf-sub {
  text-anchor: start;
  font-size: 6px;
  fill: var(--text-secondary);
}
.pdf-line {
  stroke: var(--text-muted);
  stroke-width: 1;
  opacity: 0.5;
}
.pdf-diagram {
  fill: var(--bg-elevated);
  stroke: var(--text-secondary);
}
.preview-caption {
  position: absolute;
  bottom: 4px;
  left: 8px;
  color: var(--text-secondary);
  font-size: var(--fs-xs);
}
.compact {
  min-height: 0;
  height: 42px;
}
.compact svg {
  height: 42px;
  min-height: 0;
  max-height: 42px;
}
</style>
