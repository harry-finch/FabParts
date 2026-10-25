"""Original GPL-3.0-or-later fixture geometry, in declared source millimetres."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "tests/fixtures/models"
CUBE = """IndexedFaceSet {
 coord Coordinate { point [0 0 0,1 0 0,1 1 0,0 1 0,0 0 1,1 0 1,1 1 1,0 1 1] }
 coordIndex [0 3 2 1 -1,4 5 6 7 -1,0 1 5 4 -1,1 2 6 5 -1,2 3 7 6 -1,3 0 4 7 -1]
}"""
HEADER = (
    "#VRML V2.0 utf8\n# Original TECH-02B fixture; coordinates declared in mm. GPL-3.0-or-later.\n"
)
BODY = f"""DEF Body Shape {{ appearance Appearance {{
 material Material {{diffuseColor 0.15 0.18 0.22}}}}
 geometry DEF Cube {CUBE} }}"""
box = f"Transform {{ translation 7 -7 2 children [Transform {{scale 10 6 2 children [{BODY}]}}] }}"
(ROOT / "box.wrl").write_text(HEADER + box + "\n")
package = (
    HEADER
    + box
    + "\nDEF Pin Shape { appearance Appearance {material Material {diffuseColor 0.7 0.72 0.75}}"
    " geometry USE Cube }\n"
)
# DEF Pin must only be instantiated as a child; top-level DEF is also rendered.
package = package.replace(
    "DEF Pin Shape",
    "Transform { translation 7.94 -8.5 0 children ["
    "Transform {scale 0.5 1 3 children [DEF Pin Shape",
).replace("geometry USE Cube }\n", "geometry USE Cube }]}]}\n")
for x in (-3.81, -1.27, 1.27, 3.81):
    for y in (-4, 4):
        if (x, y) != (-3.81, -4):
            package += (
                f"Transform {{translation {12 + x - 0.25} {-4 + y - 0.5} 0 children ["
                "Transform {scale 0.5 1 3 children [USE Pin]}]}\n"
            )
(ROOT / "package.wrl").write_text(package)
(ROOT / "invalid.wrl").write_text(
    HEADER + "Shape { geometry IndexedFaceSet {coord Coordinate {point [nan 0 0]} } }\n"
)
(ROOT / "dynamic.wrl").write_text(
    HEADER + 'Script {url "https://invalid.invalid/never-fetch.js"}\n'
)
(ROOT / "invalid.step").write_text(
    "ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\nthis is not STEP;\nENDSEC;\nEND-ISO-10303-21;\n"
)
