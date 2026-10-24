# KiPart Manager — Repository Instructions

KiPart Manager is a local-first component, asset, inventory, and KiCad library management application.

## Persistent architectural rules

- The local SQLite database and managed Asset Store are the source of truth.
- Generated KiCad libraries are build artifacts, not primary storage.
- Core functionality must work without Internet access, without a server, and without an AI provider.
- AI and network integrations are optional adapters.
- User-provided assets must never be silently replaced.
- Before generating a symbol, footprint, or 3D model, search appropriate existing resources first, including the official local KiCad libraries.
- Generated assets must be validated before publication.
- Never write raw LLM output directly as a KiCad asset when a structured intermediate representation and deterministic generator can be used.
- Never modify the user's official KiCad libraries.
- Preserve asset provenance, hashes, and validation state.
- Published library versions are immutable.
- Portable paths are required; avoid machine-specific absolute paths in published artifacts.

## Architecture

Target architecture:

UI → Application → Domain → Ports → Infrastructure

The domain layer must not depend on:

- PySide6
- SQLAlchemy
- filesystem implementations
- HTTP clients
- AI providers
- KiCad installations

Expected source layout:

src/kipartmanager/
- domain/
- application/
- ports/
- infrastructure/
- ui/

Tests live under `tests/`.

## Project documentation

Use documentation contextually:

- `docs/PROJECT_SPEC.md` for product requirements and invariants.
- `docs/ARCHITECTURE.md` when changing module boundaries, domain entities, ports, or infrastructure responsibilities.
- `docs/MILESTONES.md` when starting or completing a milestone.
- Do not reread every document before every small edit.

If implementation and documentation disagree on an architectural invariant, stop and surface the discrepancy rather than silently redefining the architecture.

## Technology baseline

Unless a milestone explicitly changes this:

- Python 3.12+
- PySide6
- SQLite
- SQLAlchemy 2
- Alembic
- pytest
- static typing
- TOML configuration
- SHA-256 for asset integrity
- ZIP + JSON manifest for future `.kiparts` bundles

Do not introduce a heavy dependency unless the current milestone genuinely requires it.

## Development discipline

Work only on the requested milestone or task.

You may fully implement, test, debug, and clean up work that is necessary to satisfy the current milestone.

Do not begin functionality assigned to a later milestone merely because it would be convenient.

Prefer small domain-oriented abstractions over speculative frameworks.

Avoid premature genericity.

Do not add network services, AI integrations, server components, KiCad generation, or synchronization before their milestone.

## Testing

Local tests use disposable project data and may be run without asking for approval.

Run affected tests after changes and fix failures caused by the requested work.

At milestone checkpoints, run the complete test suite that currently exists.

Distinguish new failures from pre-existing failures.

Offline behavior is an architectural requirement, not an optional feature.

## Milestone checkpoints

When a milestone has acceptance criteria, satisfy all of them before reporting completion.

At the checkpoint:

- inspect the final diff;
- run required tests;
- report functionality implemented;
- report tests and their results;
- report architectural decisions;
- report known limitations;
- report files added/changed at a useful level;
- stop.

Never automatically continue into the next milestone.

## UI/UX quality

KiPart Manager is a desktop application intended for regular practical use. User-facing interfaces are expected to be visually coherent and intentionally designed, not merely functional default Qt layouts.

When creating or significantly modifying UI:

- use the `pyside-ui-ux` skill;
- preserve a consistent application shell and navigation;
- reuse shared UI components and styling rather than styling screens independently;
- maintain clear hierarchy, spacing, typography, status presentation, and empty states;
- keep layouts usable when resized;
- avoid unnecessary modal dialogs;
- keep domain and application logic separate from presentation code.

Visual and interaction quality are part of the acceptance criteria for user-facing features.

Do not undertake large visual redesigns inside an unrelated milestone unless explicitly requested.

### Established UI conventions

- Follow `docs/UI_GUIDELINES.md` when creating or changing screens.
- Reuse the primitives in `ui/components.py` and the styles/spacing in `ui/theme.py`; do not introduce parallel QSS without a concrete need.
- Preserve the task-oriented sidebar and secondary workspace tabs.
- Keep technical identifiers in contextual/advanced details; distinguish association, selection, qualification and publication.
- Verify affected screens natively at standard, narrower and wider sizes.

## UI/UX — FabApps Design System

FabParts belongs to the FabApps software suite.

When designing or modifying user-facing interfaces:

- Use `fab-design-system` as the authoritative source for shared visual identity, design tokens, typography, colors, and reusable presentation patterns.
- Use `professional-workshop-ui` for technical desktop usability, information hierarchy, workflows, and interaction design.
- Reuse existing design system components and tokens whenever applicable.
- Preserve FabParts' yellow/amber accent and graphite visual identity.
- Do not introduce an independent or conflicting design system.
- Document FabParts-specific UX decisions in `docs/UI_GUIDELINES.md`.
- Include visual inspection and usability verification in UI milestone checkpoints.