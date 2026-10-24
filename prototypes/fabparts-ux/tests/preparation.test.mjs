import { test } from "node:test";
import assert from "node:assert/strict";
import {
  proposal,
  initialParts,
  changePackage,
  changeIdentity,
  acceptEligible,
  acceptResource,
  candidate,
  removeResource,
  ready,
  potentialReady,
  finish,
  savePart,
  contactCount,
  ne555Labels,
  copy,
  illustratedPackage,
} from "../src/lib/demo.ts";

test("NE555: eight contacts before and after either package choice", () => {
  for (const pkg of ["", "DIP-8", "SOIC-8"])
    assert.equal(contactCount("NE555", pkg), 8);
  assert.deepEqual(ne555Labels, [
    "GND",
    "TRIG",
    "OUT",
    "RESET",
    "CTRL",
    "THRES",
    "DISCH",
    "VCC",
  ]);
});

test("only known presentation fixtures receive contact counts and drawings", () => {
  const expected = [48, 32, 56, 10, 8, 28, 2, 2, 2, 2, 4, 16, null, null];
  initialParts().forEach((p, i) =>
    assert.equal(contactCount(p.ref, p.package), expected[i]),
  );
  assert.equal(contactCount("CUSTOM-555", "DIP-999"), null);
  assert.equal(illustratedPackage("USB-C-16"), false);
});

test("an unrelated reference is never silently rewritten as NE555", () => {
  const p = proposal("CUSTOM-555", "Lab");
  assert.equal(p.ref, "CUSTOM-555");
  assert.deepEqual(p.resources, {});
  assert.equal(proposal("STM32F103-unknown", "").package, "");
});

test("NE555 missing-footprint journey saves and resumes one draft without losing choices", () => {
  const p = acceptEligible(changePackage(proposal("NE555", ""), "DIP-8"));
  assert.equal(p.resources.symbol.accepted, true);
  assert.equal(p.resources.datasheet.accepted, true);
  assert.equal(p.resources.footprint, undefined);
  assert.equal(p.resources.model, undefined);
  assert.equal(potentialReady(p), "schematic");
  const saved = finish(p, false),
    catalogue = savePart([], saved);
  const resumed = copy(catalogue[0]);
  assert.equal(ready(resumed), "draft");
  assert.equal(resumed.package, "DIP-8");
  assert.equal(resumed.resources.symbol.accepted, true);
  assert.equal(savePart(catalogue, resumed).length, 1);
});

test("symbol and footprint allow explicit PCB confirmation; 3D and datasheet are optional", () => {
  let p = changePackage(proposal("NE555", ""), "DIP-8");
  p.resources.footprint = candidate(p, "footprint", false);
  delete p.resources.datasheet;
  p = acceptEligible(p);
  assert.equal(ready(p), "draft");
  assert.equal(ready(finish(p, true)), "pcb");
  assert.equal(p.resources.model, undefined);
});

test("missing footprint allows explicit schematic confirmation, never PCB", () => {
  const p = acceptEligible(proposal("NE555", ""));
  assert.equal(ready(finish(p, true)), "schematic");
  assert.equal(ready(finish(proposal("unknown", ""), true)), "draft");
});

test("batch acceptance excludes supplied files, conflicts, choices and absent resources", () => {
  const p = changePackage(proposal("NE555", ""), "DIP-8");
  p.resources.symbol = {
    name: "mine.kicad_sym",
    source: "user",
    accepted: false,
  };
  p.resources.footprint = {
    ...candidate(p, "footprint", false),
    review: "conflict",
  };
  p.resources.datasheet.review = "choice";
  const before = copy(p),
    after = acceptEligible(p);
  assert.deepEqual(after, before);
  assert.deepEqual(p, before);
  assert.equal(acceptResource(p, "symbol").resources.symbol.accepted, true);
  assert.equal(
    acceptResource(p, "footprint").resources.footprint.accepted,
    false,
  );
});

test("footprint acceptance is blocked until a package is selected", () => {
  let p = proposal("CUSTOM", "");
  p.resources.footprint = {
    name: "mine.kicad_mod",
    source: "user",
    accepted: false,
  };
  assert.equal(
    acceptResource(p, "footprint").resources.footprint.accepted,
    false,
  );
  p = changePackage(p, "DIP-8");
  assert.equal(acceptEligible(p).resources.footprint.accepted, false);
  const reviewed = acceptResource(p, "footprint");
  assert.equal(reviewed.resources.footprint.name, "mine.kicad_mod");
  assert.equal(reviewed.resources.footprint.source, "user");
  assert.equal(reviewed.resources.footprint.accepted, true);
});

test("package changes retain files and provenance, invalidate associations and final confirmation", () => {
  let p = changePackage(proposal("NE555", ""), "DIP-8");
  p.resources.footprint = {
    name: "mine.kicad_mod",
    source: "user",
    accepted: true,
    package: "DIP-8",
  };
  p.resources.model = candidate(p, "model", false);
  p = finish(acceptEligible(p), true);
  const changed = changePackage(p, "SOIC-8");
  assert.equal(ready(changed), "draft");
  assert.equal(changed.resources.footprint.name, "mine.kicad_mod");
  assert.equal(changed.resources.footprint.source, "user");
  assert.equal(changed.resources.footprint.package, "DIP-8");
  assert.equal(changed.resources.footprint.review, "conflict");
  assert.equal(acceptEligible(changed).resources.footprint.accepted, false);
  assert.equal(acceptEligible(changed).resources.model.accepted, false);
  assert.equal(changed.resources.symbol.accepted, true);
});

test("identity changes cannot keep old proposals accepted", () => {
  const p = finish(acceptEligible(proposal("NE555", "")), true);
  const next = changeIdentity(p, "OTHER", "Lab");
  assert.equal(next.resources.symbol.reference, "NE555");
  assert.equal(next.resources.symbol.review, "conflict");
  assert.equal(ready(acceptEligible(next)), "draft");
});

test("removing a required proposal revokes readiness and batch acceptance does not recreate it", () => {
  const p = finish(acceptEligible(proposal("NE555", "")), true);
  const next = acceptEligible(removeResource(p, "symbol"));
  assert.equal(next.resources.symbol, undefined);
  assert.equal(ready(next), "draft");
  assert.ok(p.resources.symbol);
});

test("same reference is rejected across IDs, but a saved draft updates in place", () => {
  const p = proposal("NE555", ""),
    other = proposal(" ne555 ", "");
  assert.throws(() => savePart([p], other), /duplicateReference/);
  const saved = savePart([p], { ...p, package: "SOIC-8" });
  assert.equal(saved.length, 1);
  assert.equal(saved[0].package, "SOIC-8");
});
