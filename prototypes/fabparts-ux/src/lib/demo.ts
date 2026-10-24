// Fixtures for the UX prototype only. No link to the Python domain or real files.
export type Kind = "symbol" | "footprint" | "model" | "datasheet";
export const kinds: Kind[] = ["symbol", "footprint", "model", "datasheet"];
export type Category =
  "mcu" | "ic" | "resistor" | "capacitor" | "connector" | "module";
export const categories: Category[] = [
  "mcu",
  "ic",
  "resistor",
  "capacitor",
  "connector",
  "module",
];
export type Library = "Lab" | "Personnel";
export type Ready = "draft" | "schematic" | "pcb";
export type Sync = "available" | "incomplete" | "syncing" | "error";
export type Resource = {
  name: string;
  source: "official" | "manufacturer" | "user" | "managed";
  accepted: boolean;
  review?: "choice" | "conflict";
  package?: string;
  reference?: string;
};
export type Part = {
  id: string;
  ref: string;
  manufacturer: string;
  category: Category;
  description: [string, string];
  package: string;
  libraries: Library[];
  resources: Partial<Record<Kind, Resource>>;
  sync: Sync;
  version: number;
  // Explicit final confirmation in the demo, never a technical validation.
  confirmed?: boolean;
  properties: [string, string][];
};
export const copy = <T>(v: T): T => JSON.parse(JSON.stringify(v));
export function acceptanceBlock(
  part: Part,
  kind: Kind,
): "packageNeeded" | "conflict" | null {
  const r = part.resources[kind];
  if (r?.review === "conflict") return "conflict";
  if ((kind === "footprint" || kind === "model") && !part.package.trim())
    return "packageNeeded";
  return null;
}
export function eligible(part: Part, kind: Kind): boolean {
  const r = part.resources[kind];
  return (
    !!r &&
    !r.accepted &&
    !r.review &&
    r.source !== "user" &&
    !acceptanceBlock(part, kind)
  );
}
export function acceptResource(part: Part, kind: Kind): Part {
  const next = copy(part),
    r = next.resources[kind];
  if (r && !acceptanceBlock(next, kind)) {
    r.accepted = true;
    r.package = next.package;
    r.reference = next.ref;
    delete r.review;
  }
  return next;
}
export function acceptEligible(part: Part): Part {
  let next = copy(part);
  for (const kind of kinds)
    if (eligible(next, kind)) next = acceptResource(next, kind);
  return next;
}
export function potentialReady(part: Part): Ready {
  const accepted = (kind: Kind) =>
    part.resources[kind]?.accepted &&
    !part.resources[kind]?.review &&
    !acceptanceBlock(part, kind);
  if (!accepted("symbol")) return "draft";
  return part.package.trim() && accepted("footprint") ? "pcb" : "schematic";
}
export function ready(part: Part): Ready {
  return part.confirmed === false ? "draft" : potentialReady(part);
}
export function finish(part: Part, confirm: boolean): Part {
  const next = copy(part);
  next.confirmed = confirm && potentialReady(next) !== "draft";
  next.sync = "incomplete";
  return next;
}
export function changePackage(part: Part, pkg: string): Part {
  const next = copy(part);
  if (next.package === pkg) return next;
  next.package = pkg;
  next.confirmed = false;
  // Keep every existing file and choice visible, including user-provided assets.
  for (const kind of ["footprint", "model"] as Kind[]) {
    const r = next.resources[kind];
    if (r) {
      r.package ??= part.package;
      r.reference ??= part.ref;
      r.accepted = false;
      r.review = part.package ? "conflict" : "choice";
    }
  }
  return next;
}
export function changeIdentity(
  part: Part,
  ref: string,
  manufacturer: string,
): Part {
  const next = copy(part);
  if (next.ref === ref && next.manufacturer === manufacturer) return next;
  if (next.ref !== ref) next.properties = [];
  next.ref = ref;
  next.manufacturer = manufacturer;
  next.confirmed = false;
  for (const r of Object.values(next.resources)) {
    r.reference ??= part.ref;
    r.package ??= part.package;
    r.accepted = false;
    r.review = "conflict";
  }
  return next;
}
export function removeResource(part: Part, kind: Kind): Part {
  const next = copy(part);
  delete next.resources[kind];
  next.confirmed = false;
  return next;
}
export function sameReference(a: string, b: string): boolean {
  return a.trim().toUpperCase() === b.trim().toUpperCase();
}
export function savePart(parts: Part[], part: Part): Part[] {
  const duplicate = parts.find(
    (p) => p.id !== part.id && sameReference(p.ref, part.ref),
  );
  if (duplicate) throw new Error("duplicateReference");
  const next = copy(parts),
    index = next.findIndex((p) => p.id === part.id);
  if (index < 0) next.push(copy(part));
  else next[index] = copy(part);
  return next;
}
// Presentation fixtures only: no KiCad geometry, dimensions or electrical validation.
export const ne555Labels = [
  "GND",
  "TRIG",
  "OUT",
  "RESET",
  "CTRL",
  "THRES",
  "DISCH",
  "VCC",
];
export function contactCount(ref: string, pkg: string): number | null {
  if (sameReference(ref, "NE555")) return 8;
  if (["0603", "0805"].includes(pkg)) return 2;
  const fixtureCounts: Record<string, number> = {
    "LQFP-48": 48,
    "TQFP-32": 32,
    "QFN-56": 56,
    "DIP-8": 8,
    "SOIC-8": 8,
    "VSSOP-10": 10,
    "DIP-28": 28,
    "JST-XH-4": 4,
    "USB-C-16": 16,
  };
  return fixtureCounts[pkg] ?? null;
}
export function illustratedPackage(pkg: string): boolean {
  return [
    "LQFP-48",
    "TQFP-32",
    "QFN-56",
    "DIP-8",
    "SOIC-8",
    "VSSOP-10",
    "DIP-28",
    "0603",
    "0805",
  ].includes(pkg);
}
export function partProperties(part: Part): [string, string][] {
  return [
    ...part.properties
      .filter(([key]) => key !== "pins")
      .map(
        ([key, value]) => [key, value === "—" ? "" : value] as [string, string],
      ),
    ["pins", String(contactCount(part.ref, part.package) ?? "")],
  ];
}
export function resources(
  ref: string,
  pkg: string,
  complete = true,
): Part["resources"] {
  return {
    symbol: {
      name: ref,
      source: "official",
      accepted: complete,
      reference: ref,
    },
    footprint: {
      name: pkg.replaceAll("-", "_"),
      source: "official",
      accepted: complete,
      package: pkg,
    },
    model: {
      name: `${pkg}.step`,
      source: "official",
      accepted: complete,
      package: pkg,
    },
    datasheet: {
      name: `${ref.toLowerCase()}.pdf`,
      source: "manufacturer",
      accepted: complete,
    },
  };
}
const seeds: [
  string,
  string,
  Category,
  string,
  string,
  string,
  Library[],
  string,
][] = [
  [
    "STM32F103C8T6",
    "STMicroelectronics",
    "mcu",
    "LQFP-48",
    "Microcontrôleur ARM Cortex-M3 · 72 MHz",
    "ARM Cortex-M3 microcontroller · 72 MHz",
    ["Lab", "Personnel"],
    "64 KB Flash · 2,0–3,6 V",
  ],
  [
    "ATmega328P-AU",
    "Microchip",
    "mcu",
    "TQFP-32",
    "Microcontrôleur AVR · 8 bits",
    "AVR microcontroller · 8-bit",
    ["Lab"],
    "32 KB Flash · 1,8–5,5 V",
  ],
  [
    "RP2040",
    "Raspberry Pi",
    "mcu",
    "QFN-56",
    "Double cœur Cortex-M0+ · 133 MHz",
    "Dual-core Cortex-M0+ · 133 MHz",
    ["Personnel"],
    "264 KB RAM · 1,8–3,3 V",
  ],
  [
    "ADS1115IDGSR",
    "Texas Instruments",
    "ic",
    "VSSOP-10",
    "Convertisseur analogique-numérique · 16 bits",
    "Analogue-to-digital converter · 16-bit",
    ["Lab", "Personnel"],
    "I²C · 4 entrées / inputs",
  ],
  [
    "LM358DR",
    "Texas Instruments",
    "ic",
    "SOIC-8",
    "Double amplificateur opérationnel",
    "Dual operational amplifier",
    ["Lab"],
    "3–32 V · 1 MHz",
  ],
  [
    "MCP23017-E/SP",
    "Microchip",
    "ic",
    "DIP-28",
    "Extension de ports · 16 entrées/sorties",
    "Port expander · 16 I/O",
    ["Personnel"],
    "I²C · 1,8–5,5 V",
  ],
  [
    "RC0603FR-0710KL",
    "Yageo",
    "resistor",
    "0603",
    "Résistance · 10 kΩ · 1 %",
    "Resistor · 10 kΩ · 1%",
    ["Lab", "Personnel"],
    "0,1 W · 75 V",
  ],
  [
    "RC0805FR-07100RL",
    "Yageo",
    "resistor",
    "0805",
    "Résistance · 100 Ω · 1 %",
    "Resistor · 100 Ω · 1%",
    ["Lab"],
    "0,125 W · 150 V",
  ],
  [
    "GRM188R71C104KA01",
    "Murata",
    "capacitor",
    "0603",
    "Condensateur céramique · 100 nF",
    "Ceramic capacitor · 100 nF",
    ["Lab"],
    "X7R · 16 V · ±10 %",
  ],
  [
    "CL21A106KAYNNNE",
    "Samsung",
    "capacitor",
    "0805",
    "Condensateur céramique · 10 µF",
    "Ceramic capacitor · 10 µF",
    ["Personnel"],
    "X5R · 25 V · ±10 %",
  ],
  [
    "B4B-XH-A",
    "JST",
    "connector",
    "JST-XH-4",
    "Connecteur vertical · 4 contacts",
    "Vertical connector · 4 contacts",
    ["Lab"],
    "2,5 mm · 3 A",
  ],
  [
    "USB4105-GF-A",
    "GCT",
    "connector",
    "USB-C-16",
    "Connecteur USB Type-C · USB 2.0",
    "USB Type-C connector · USB 2.0",
    ["Lab", "Personnel"],
    "16 contacts · 5 A",
  ],
  [
    "ESP32-WROOM-32E",
    "Espressif",
    "module",
    "ESP32-WROOM",
    "Module Wi-Fi et Bluetooth",
    "Wi-Fi and Bluetooth module",
    ["Lab"],
    "4 MB Flash · 3,3 V",
  ],
  [
    "RFM95W-868S2",
    "HopeRF",
    "module",
    "RFM95W",
    "Module radio LoRa · 868 MHz",
    "LoRa radio module · 868 MHz",
    ["Personnel"],
    "SPI · 3,3 V",
  ],
];
export function initialParts(): Part[] {
  return seeds.map(
    ([ref, manufacturer, category, pkg, fr, en, libraries, spec], index) => {
      const r = resources(ref, pkg);
      if ([2, 4, 6, 9].includes(index)) delete r.model;
      if ([5, 13].includes(index)) {
        delete r.footprint;
        delete r.model;
      }
      if (index === 13) r.symbol!.accepted = false;
      return {
        id: `demo-${index}`,
        ref,
        manufacturer,
        category,
        description: [fr, en],
        package: pkg,
        libraries,
        resources: r,
        sync:
          index === 11 ? "error" : index === 13 ? "incomplete" : "available",
        version: 2,
        confirmed: index !== 13,
        properties: [
          ["spec", spec],
          ["pins", String(contactCount(ref, pkg) ?? "")],
        ],
      };
    },
  );
}
export function proposal(ref: string, manufacturer: string): Part {
  const text = ref.trim() || "Composant personnalisé";
  const known = sameReference(text, "NE555");
  const stm = sameReference(text, "STM32F103C8T6");
  const pkg = stm ? "LQFP-48" : "";
  const result: Part = {
    id: `demo-${crypto.randomUUID()}`,
    ref: text,
    manufacturer:
      manufacturer.trim() ||
      (known ? "Texas Instruments" : stm ? "STMicroelectronics" : ""),
    category: stm ? "mcu" : "ic",
    description: known
      ? [
          "Temporisateur de précision · circuit intégré",
          "Precision timer · integrated circuit",
        ]
      : stm
        ? [
            "Microcontrôleur ARM Cortex-M3 · 72 MHz",
            "ARM Cortex-M3 microcontroller · 72 MHz",
          ]
        : ["Identification à compléter", "Identification needed"],
    package: pkg,
    libraries: ["Lab"],
    resources: known || stm ? resources(text, pkg, false) : {},
    sync: "incomplete",
    version: 1,
    confirmed: false,
    properties: [
      [
        "spec",
        known ? "4,5–16 V · 500 kHz" : stm ? "64 KB Flash · 72 MHz" : "—",
      ],
      ["pins", known ? "8" : stm ? "48" : "—"],
    ],
  };
  if (known) {
    delete result.resources.model;
    delete result.resources.footprint;
  }
  return result;
}
export const packageOptions = ["DIP-8", "SOIC-8"];
export function candidate(
  part: Part,
  kind: Kind,
  alternate: boolean,
): Resource {
  return {
    name:
      kind === "datasheet"
        ? `${part.ref}.pdf`
        : kind === "model"
          ? `${part.package || "custom"}.step`
          : kind === "footprint"
            ? `${part.package || "custom"}${alternate ? "_HandSolder" : ""}`
            : `${part.ref}${alternate ? "_alternate" : ""}`,
    source: alternate
      ? "managed"
      : kind === "datasheet"
        ? "manufacturer"
        : "official",
    accepted: false,
    package: part.package,
    reference: part.ref,
  };
}
