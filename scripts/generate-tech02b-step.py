"""Run with external FreeCADCmd; writes only original TECH-02B test fixtures."""

import os
from pathlib import Path

import FreeCAD
import Part

root = Path(os.environ["FABPARTS_FIXTURE_OUTPUT"])
root.mkdir(parents=True, exist_ok=True)
box = Part.makeBox(10, 6, 2, FreeCAD.Vector(7, -7, 2))
box.exportStep(str(root / "box.step"))
pieces = [box]
for x in [-3.81, -1.27, 1.27, 3.81]:
    for y in [-4, 4]:
        pieces.append(Part.makeBox(0.5, 1, 3, FreeCAD.Vector(12 + x - 0.25, -4 + y - 0.5, 0)))
Part.makeCompound(pieces).exportStep(str(root / "package.step"))
plate = Part.makeBox(8, 8, 1)
for x in [2, 6]:
    for y in [2, 6]:
        plate = plate.cut(Part.makeCylinder(0.35, 1, FreeCAD.Vector(x, y, 0)))
plate.exportStep(str(root / "details.step"))
print("TECH02B_FIXTURES", FreeCAD.Version(), [p.name for p in root.glob("*.step")])
