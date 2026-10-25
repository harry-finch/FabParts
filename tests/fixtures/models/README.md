# Original TECH-02B qualification corpus

All files were generated for FabParts, GPL-3.0-or-later. No manufacturer data.
Generators: `scripts/generate-tech02b-wrl.py` and `scripts/generate-tech02b-step.py`.
STEP files: FreeCAD 1.1.1, AP214, millimetres. WRL: VRML97, coordinates explicitly
chosen in millimetres **for these fixtures only**; arbitrary WRL units remain unknown.

| Fixture | Bounds / dimensions | Expected |
|---|---|---|
| box.wrl / box.step | (7,-7,2)…(17,-1,4), 10×6×2 | Same off-origin box, correct winding |
| package.wrl / package.step | (7,-8.5,0)…(17,0.5,4), 10×9×4 | Body + 8 pins, nine solids; WRL two materials, nested transforms, DEF/USE |
| details.step | (0,0,0)…(8,8,1) | Plate with four radius 0.35 holes |
| invalid.wrl | Invalid coordinate | Explicit failure |
| dynamic.wrl | Forbidden Script URL | Reject without opening network |
| invalid.step | Invalid syntax | Conversion failure |

Tests generate oversized, concave, non-planar, degenerate and rotated meshes in
memory; a disposable slow converter verifies timeout, cancellation and cleanup.
No large fixture or test executable is shipped as a production dependency.
`tests.model_preview_corpus` creates a new disposable catalogue, including missing
assets, multiple associated 3D assets and the existing 2D/PDF regression corpus.
