# Third-party notices and provenance

Audit date: 2026-10-24. Original FabParts code is licensed under **GPL-3.0-or-later**, with the complete text in [LICENSE](LICENSE). These notices do not certify that every resource may be published. Existing notices remain in place. GIT-04 records the owner’s confirmation that FabParts is a personal project and that both shared design packs are intended for GPL publication.

The [machine-readable inventory](docs/DEPENDENCY_LICENSES.json) records 30 external Python packages from the installed environment, 427 crates from locked Cargo metadata across targets, and 87 TECH-01 / 74 UX npm package records. It is a metadata inventory, not a list of everything linked into a particular executable. Alternative SPDX licenses (`OR`) and combined obligations (`AND`) must be interpreted separately.

## Material incorporated or embedded by the build

| Material / origin | Where and how used | License evidence / action |
| --- | --- | --- |
| Lucide SVGs, with Feather-derived portions — Lucide contributors and Cole Bemis | `src/kipartmanager/ui/icons/`; included in the historical Python package | Existing [ISC notice](src/kipartmanager/ui/icons/LUCIDE-LICENSE.txt) retained. It identifies Feather MIT portions. Preserve upstream attribution and confirm the exact source revision of the older SVG set. |
| Lucide Svelte 1.61.0 — Lucide Icons and Contributors; Feather portions | npm dependency of both frontends; icons become application output | ISC plus the MIT notice for Feather portions. The complete installed package notice is preserved verbatim in [Lucide-Svelte-LICENSE.txt](third_party/licenses/Lucide-Svelte-LICENSE.txt). [Upstream licensing](https://lucide.dev/license). |
| Inter, packaged as `@fontsource-variable/inter` 5.3.0 — The Inter Project Authors | Imported by frontend styles; fonts are included by the frontend build. No standalone font binary is currently committed | SIL OFL 1.1. The installed package's exact copyright/license text is preserved in [Inter-OFL-1.1.txt](third_party/licenses/Inter-OFL-1.1.txt). Preserve it with distributed fonts; do not treat fonts as relicensed FabParts code. [Inter source license](https://github.com/rsms/inter/blob/master/LICENSE.txt). |
| Fab design starter and shared UI patterns | `.agents/skills/fab-design-system/`, including Svelte/CSS sources; reused by the prototypes | Starter `package.json` declares **GPL-3.0-or-later**. The UX package and its lockfile repeat that declaration. GIT-03: the Product Owner confirms designing this pack with Claude assistance, without known wholesale adoption of an external pack, and chooses GPL-3.0-or-later. This records a declaration, not proof of originality of every element. Inter/Lucide retain their own licenses; branding rights remain to confirm. |
| Professional Workshop UI and other repository skills | `.agents/skills/professional-workshop-ui/`, `.codex/skills/` | GIT-04: the Product Owner confirms Professional Workshop UI was designed with ChatGPT assistance and authorizes its GPL publication alongside FabApps. No concrete conflicting provenance was identified in the other repository guidance; do not treat the prior generic uncertainty as a publication blocker. Third-party notices remain applicable. |
| FabParts / KiPart Manager / FabApps branding | Canonical SVGs under `src/kipartmanager/ui/branding/source/`, generated icons, `logo/`, prototype logos and starter logo | The [branding record](docs/BRANDING.md) records the owner-supplied, approved canonical logo. GIT-04 retains validated branding in the personal project’s public scope. The software license does not grant trademark rights. |
| Screenshots and demonstrations | `docs/images/`, `prototypes/fabparts-ux/screenshots/`, test and prototype fixtures | Development screenshots are excluded from this public snapshot. Any future screenshots need explicit privacy/provenance review. Generic test data and simulated CAD drawings are not a license to redistribute third-party CAD or datasheets. |

The new Inter and Lucide notice files are source-repository notices. Their addition does not make the existing desktop build automatically include them. Before distributing an executable or standalone HTML bundle, check that the matching notices actually accompany the embedded fonts/icons and other bundled code.

The Tauri frontend directly imports CSS, components and modules from the GPL-declared UX package. The GPL-3.0-or-later project decision is consistent with this reuse. Removing the UX folder without replacing these dependencies would break its build.

SVG references to system font families (including Noto Sans) do not themselves ship font files. A future font import must receive its own provenance/license entry.

## Python and packaging

- The historical application depends on PySide6/Shiboken6, SQLAlchemy and Alembic. Local metadata identifies SQLAlchemy, Alembic and Mako as MIT, MarkupSafe as BSD-3-Clause, and `typing_extensions` as PSF-2.0.
- Installed PySide6/Shiboken6 packages declare LGPL-3.0-only / GPL alternatives. The code uses Qt Widgets and Qt PDF; installed WebEngine/other modules are not all demonstrated as application dependencies. A binary release needs module-specific license/source/relinking review, including PDFium/Chromium where distributed. LGPL compliance cannot be inferred from the aggregate PySide package label. See [Qt obligations](https://www.qt.io/development/open-source-lgpl-obligations) and [Qt for Python licenses](https://doc.qt.io/qtforpython-6/licenses.html).
- The TECH-01 sidecar build explicitly excludes PySide6 and Shiboken6. Its obligations must be assessed from its actual frozen contents, separately from the historical GUI. CPython, collected native libraries and runtime hooks also belong in a future artifact-specific inventory.
- PyInstaller 6.16.0 is a packaging tool with a GPL exception for generated applications and some Apache-licensed files; its use does not by itself force FabParts under GPL. Dependency obligations still apply. See the [versioned PyInstaller licensing explanation](https://pyinstaller.org/en/v6.16.0/license.html). The installed hooks package also declares Apache/GPL licensing; review copied runtime hooks when releasing binaries.
- pytest, Ruff, mypy, pip, setuptools and other environment tools are development/build dependencies. `pathspec` declares MPL-2.0. Their presence in a development environment is not proof that they are shipped in FabParts.

## Rust and JavaScript

Tauri and its ecosystem use predominantly MIT/Apache alternatives; serde, serde_json, tokio and libc have their own recorded expressions. The Cargo inventory also includes BSD, ISC, Zlib, Unicode, LLVM-exception and MPL licenses. `cssparser`, `cssparser-macros`, `dtoa-short`, `option-ext` and `selectors` declare MPL-2.0. Some target-specific packages offer an LGPL alternative alongside permissive choices. Do not flatten these into one blanket license.

Svelte and Vite declare MIT, TypeScript Apache-2.0, and the locked Tauri API/CLI packages Apache-2.0 OR MIT. Lightning CSS packages declare MPL-2.0 and are build tooling. Compiler output is not automatically licensed like the compiler; runtime code and resources copied into the output retain their terms. [Mozilla's MPL FAQ](https://www.mozilla.org/en-US/MPL/2.0/FAQ/) explains the file-level source obligations for distributed MPL-covered material.

## KiCad, manufacturer data and SnapMagic

No standalone `.kicad_sym`, `.kicad_mod`, STEP/WRL or datasheet PDF is included in the inspected publishable source set/history. Test files construct minimal examples; catalogue references to external KiCad resources do not copy those libraries into this repository. User Asset Stores and catalogue copies remain outside the candidate history.

Official KiCad library collections use **CC BY-SA 4.0 with a design exception**. The exception permits use in designs; redistribution of a library collection or part of it still requires the applicable attribution and license. Verify per-file notices, including 3D models, before adding any library material. See [KiCad's library license](https://www.kicad.org/libraries/license/).

SnapMagic's help page describes CC BY-SA with a design exception for symbols/footprints, while its service terms impose separate access and distribution restrictions. Neither is blanket permission to bundle provider data in FabParts. The real partner API is not connected, no provider asset was identified in the source candidate, and no partner grant is established. Obtain written permission where required and assess each asset, especially 3D models. See [SnapMagic licensing help](https://support.snapmagic.com/en/articles/2957814-what-is-the-license-for-symbols-and-footprints), [service terms](https://www.snapeda.com/about/terms/) and the [adapter limitations](docs/SNAPMAGIC.md).

Manufacturer datasheets are not automatically covered by KiCad, SnapMagic or FabParts licensing. Linking to a manufacturer and redistributing its PDF are different actions; establish permission before including such files or substantial extracts.

## GIT-03 pack and compatibility review

The Fab design pack contains 39 text files: guidance, Svelte/TypeScript/CSS templates, configuration, and one inline SVG starter logo. The starter imports Inter and Lucide from npm; no font binary, embedded raster, external image payload or downloaded icon collection is present inside the pack. System font names are references only. The starter SVG draws a graphite tile and a circle; this observation does not establish rights over the FabApps identity.

Professional Workshop UI contains eight Markdown guidance files, including CSS/text examples. Lucide and Tabler are recommendations, not copied icon files. The Product Owner clarified in GIT-04 that this pack was designed with ChatGPT assistance and is intended for GPL publication with FabApps. This resolves the requested provenance clarification. Identified third-party material retains its own license.

The dependency metadata review found no demonstrated incompatibility requiring a source-code change for a GPLv3 distribution: permissive MIT/ISC/BSD/Apache alternatives remain available, and LGPL components retain their terms. This is not a universal clearance. MPL-2.0 files require preservation of their notices and review of any “Incompatible With Secondary Licenses” designation before combination/distribution; the metadata inventory alone does not prove its absence. PyInstaller exceptions and Qt modules must still be checked against the exact future executable. See the [GNU compatibility guidance](https://www.gnu.org/licenses/license-list.html#GPLCompatibleLicenses) and [MPL FAQ](https://www.mozilla.org/en-US/MPL/2.0/FAQ/).

The GPL text's Free Software Foundation copyright concerns the license document; it is not the copyright holder of FabParts. No legal identity or blanket exclusive ownership notice has been invented. The Product Owner confirms that FabParts is personal work, not an employer-assigned mission. No concrete contrary evidence has been identified; no generic institutional uncertainty remains a blocker.
