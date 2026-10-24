---
name: kicad-library-workflow
description: Inspect, index, parse, reference, or publish KiCad symbols, footprints, 3D models, and library metadata.
---

# KiCad library workflow

Use for tasks involving KiCad library assets or file formats.

Core rules:

- Never modify official KiCad libraries in place.
- Prefer stable KiCad identifiers and portable paths.
- Distinguish an official KiCad reference from a managed local copy.
- Preserve provenance.
- Do not copy official assets into managed storage unless the requested publication/export mode requires materializing the dependency.
- A user-provided asset must not be silently replaced by an official asset.
- Existing official KiCad resources must be considered before generation.

When reading or writing a KiCad format:

1. Inspect representative real files from the relevant supported KiCad version when available.
2. Use official KiCad format/documentation semantics rather than guessing syntax.
3. Keep parsing and serialization isolated from domain logic.
4. Create small deterministic fixtures for tests.
5. Test malformed or unsupported input explicitly.
6. Prefer round-trip or semantic-equivalence tests where appropriate.

Do not implement asset generation unless the current milestone explicitly requests it.
