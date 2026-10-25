# FabParts

A local-first electronic component library manager for KiCad, part of the **FabApps** software suite.

**Early development.** The current Tauri desktop application is a read-only prototype. There is no production release or qualified cross-platform installer. Original FabParts code is licensed under GPL-3.0-or-later.

## What is FabParts?

FabParts brings component identities, symbols, footprints, 3D models and datasheets into a local catalogue. It aims to make resource selection, provenance, validation and KiCad library publication easier to inspect and reproduce.

SQLite and a managed Asset Store are the source of truth. Generated KiCad libraries are build outputs. Core workflows do not require Internet access, a server or an AI provider. Network and AI integrations are optional and disabled by default.

## Current status

There are three distinct interfaces in this repository:

| Part | What exists | Important limits |
| --- | --- | --- |
| Historical Python/PySide6 application | Component and inventory management, asset import and integrity checks, local KiCad indexing and resolution, bounded validation, versioned publication and `.kiparts` transfer; local previews and optional assistance | Development software, with documented format and workflow limits. Existing validation is not a guarantee of electrical correctness. |
| Tauri 2 / Svelte 5 prototype | A real Python sidecar reading a controlled SQLite copy; catalogue, search, filters, component details, light/dark layouts and engine restart | Read-only. TECH-02A connects KiCad symbol/footprint geometry and local multipage PDFs; 3D and business writes remain outside this prototype. Native validation covers one macOS ARM64 environment. |
| UX prototype | Interactive demonstrations of proposed workflows using explicit fixtures | Simulated resources and operations; no real catalogue engine. |

The SnapMagic adapter is scaffolding tested with a fake provider. A live partner client, approved access and redistribution rights are not established. Future KiCad synchronization, unified ingestion and 3D preview integration are not delivered by the Tauri prototype.

The historical application is documented in the [legacy desktop guide](docs/LEGACY_DESKTOP.md). The [product specification](docs/PROJECT_SPEC.md), [UX specification](docs/UX_SPEC.md) and [architecture](docs/ARCHITECTURE.md) distinguish implemented behavior from targets.

## Screenshots

Development captures and personal catalogues are excluded from this public snapshot. Approved screenshots may be added in a future change.

## Architecture

```text
Svelte 5 / TypeScript
        ↓ restricted Tauri commands
Rust / Tauri 2 — process lifecycle and IPC
        ↓ local JSONL sidecar protocol
Python — application services and domain
        ↓ storage adapters
SQLite catalogue + managed Asset Store
```

The historical PySide6 interface calls the Python application services directly. The Tauri prototype currently exposes catalogue reads only. Resource management and publication remain in the historical engine.

The domain does not depend on Qt, SQLAlchemy, HTTP clients or a KiCad installation. User assets are preserved, published library versions are immutable, and official KiCad libraries must never be modified. See [AGENTS.md](AGENTS.md) and the [sidecar ADR](docs/adr/0002-headless-readonly-sidecar.md).

## Development

### Prerequisites

- Python 3.12 or newer, with Qt-compatible native libraries for the historical UI and its tests.
- Node.js/npm compatible with the locked frontend packages.
- Rust 1.90.0 and native Tauri build prerequisites for the target platform.
- PyInstaller 6.16.0 when building the packaged Python sidecar.

The verified environment uses Python 3.13.9, Node 26.10.0, npm 11.19.1 and Rust 1.90.0 on macOS ARM64. The pinned Qt installation requires macOS 14 or newer. These observations do not qualify Windows/Linux installers or every Python version allowed by the manifest.

### Python environment

From the repository root:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.lock
.venv/bin/python -m pip install --no-build-isolation --no-deps -e '.[dev]'
.venv/bin/python -m pip check
.venv/bin/python -m kipartmanager --version
```

The initial dependency installation needs network access or a populated local package cache. The lock file records a tested environment, not a universal wheel lock for every OS. On Windows, use the corresponding `.venv\Scripts\python.exe` commands; that platform has not been qualified by this audit.

To experiment with the historical UI, use a dedicated development directory:

```sh
.venv/bin/python -m kipartmanager --data-dir ./local-data/dev
```

This command initializes or migrates the chosen development database. Do not point development runs at a personal or laboratory catalogue. Back up an existing data directory before using a new software revision.

### Tauri prototype and frontend

```sh
npm --prefix prototypes/fabparts-tech-01 ci
npm --prefix prototypes/fabparts-tech-01 run check
npm --prefix prototypes/fabparts-tech-01 test
```

Follow the [native prototype guide](prototypes/fabparts-tech-01/README.md) for a controlled catalogue copy, sidecar build and native launch. The prototype requires that copy explicitly; no user database is shipped and no Svelte demo silently replaces it.

For the separate fixture-based UX prototype:

```sh
npm --prefix prototypes/fabparts-ux ci
npm --prefix prototypes/fabparts-ux run dev
```

### Checks

```sh
QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q
.venv/bin/ruff check src tests scripts prototypes/fabparts-tech-01/scripts
.venv/bin/ruff format --check src tests scripts prototypes/fabparts-tech-01/scripts
.venv/bin/mypy src tests
npm --prefix prototypes/fabparts-tech-01 test
npm --prefix prototypes/fabparts-tech-01 run check
npm --prefix prototypes/fabparts-ux test
npm --prefix prototypes/fabparts-ux run check
rustup run 1.90.0 cargo test --locked --offline --manifest-path prototypes/fabparts-tech-01/src-tauri/Cargo.toml
```

Cargo's offline mode requires dependencies to have been fetched beforehand. Tauri also requires the generated frontend and sidecar even when running Rust unit tests: run `npm --prefix prototypes/fabparts-tech-01 run build`, then prepare the sidecar with `rustup run 1.90.0 sh ./prototypes/fabparts-tech-01/scripts/build-sidecar.sh` first (see the native prototype guide). That binary is a local build artifact and must remain untracked. The existing environment passed these checks during the publication audit. A fresh installation and desktop rebuild were not repeated for documentation-only changes. Do not commit local data, credentials, dependencies or generated executables.

## Roadmap

TECH-02A connects real 2D and PDF previews; see its [checkpoint](docs/FABPARTS_2_TECH_02A.md). Later work concerns 3D previews, component ingestion and explicit resource workflows, each requiring its own milestone. KiCad integration and packaging will be expanded through separately reviewed milestones. This is a direction, not a release schedule or a promise of complete provider coverage.

See the [milestone record](docs/MILESTONES.md) for the historical engine and [UX specification](docs/UX_SPEC.md) for FabParts 2.0 targets.

## Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md). Keep changes scoped, preserve offline behavior and provenance, and include relevant tests. Contributions to original FabParts code must be available under GPL-3.0-or-later and authorized by their rights holders. For sensitive reports, read [SECURITY.md](SECURITY.md).

## License

Original FabParts code is free software: you may redistribute it and/or modify it under the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version (**GPL-3.0-or-later**).

It is distributed without any warranty, including the implied warranties of merchantability or fitness for a particular purpose. See the complete [GNU GPLv3](LICENSE).

Third-party code, fonts and icons retain their own licenses and attribution. This grant does not assert ownership of unresolved materials or grant trademark rights. See [third-party notices](THIRD_PARTY_NOTICES.md) and the [dependency inventory](docs/DEPENDENCY_LICENSES.json).

## FabApps

FabParts is intended to be part of FabApps, a family of practical desktop tools for makers and fablabs. It shares workshop-oriented interaction patterns and a graphite/amber identity. The Product Owner confirms this is a personal project and authorizes publication of the shared Fab design and Professional Workshop UI packs under GPL-3.0-or-later. Third-party resources retain their notices.

## Repository history

This public repository starts from an intentionally curated snapshot. Earlier internal development history, checkpoint reports and unapproved screenshots are retained privately; this first commit does not reconstruct the original milestone history. Future development branches start from this public `main`.
