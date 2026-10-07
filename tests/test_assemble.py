import json

import bpy
import pytest
from mathutils import Vector

from arcology.assemble import assemble, placements
from arcology.build import build_library
from arcology.plan import element_bounds, instances


def _world_bounds(ob):
    corners = [ob.matrix_world @ Vector(c) for c in ob.bound_box]
    return [min(c[i] for c in corners) for i in range(3)], [
        max(c[i] for c in corners) for i in range(3)
    ]


def test_assembler_and_plan_agree_on_every_copy(plan, built):
    _, manifest = built
    from_manifest = {i: t for row in manifest["instances"] for i, t in placements(row)}
    from_plan = {
        c.id: list(c.translation)
        for e in plan.elements
        if "L2" in e.lod
        for c in instances(plan, e)
    }
    assert from_manifest.keys() == from_plan.keys()
    for element_id, translation in from_plan.items():
        assert from_manifest[element_id] == pytest.approx(translation, abs=1e-6), element_id


def test_scene_rebuilt_from_handover_package_matches_plan(plan, built):
    out, manifest = built
    bpy.ops.wm.read_factory_settings(use_empty=True)
    objects = assemble(out / "manifest.json")
    bpy.context.view_layer.update()

    expected = {c.id: c for e in plan.elements if "L2" in e.lod for c in instances(plan, e)}
    assert sorted(o["arcology_id"] for o in objects) == sorted(expected)
    assert {o.data.name for o in objects} == set(manifest["library"])  # shared, not copied
    for ob in objects:
        lo, hi = _world_bounds(ob)
        expected_lo, expected_hi = element_bounds(expected[ob["arcology_id"]])
        assert lo == pytest.approx(list(expected_lo), abs=1e-3), ob["arcology_id"]
        assert hi == pytest.approx(list(expected_hi), abs=1e-3), ob["arcology_id"]


def test_windows_land_where_the_plan_says_at_l0(plan, tmp_path):
    build_library(plan, tmp_path, "L0")
    bpy.ops.wm.read_factory_settings(use_empty=True)
    objects = {o["arcology_id"]: o for o in assemble(tmp_path / "manifest.json")}
    bpy.context.view_layer.update()
    windows = [c for e in plan.elements if e.kind == "window" for c in instances(plan, e)]
    assert len(objects) == sum(e.count for e in plan.elements if "L0" in e.lod)
    for w in windows[::997]:  # a spread of windows across every facade
        lo, hi = _world_bounds(objects[w.id])
        expected_lo, expected_hi = element_bounds(w)
        assert lo == pytest.approx(list(expected_lo), abs=1e-3), w.id
        assert hi == pytest.approx(list(expected_hi), abs=1e-3), w.id


def test_rejects_unknown_manifest_schema(built, tmp_path):
    out, manifest = built
    bad = tmp_path / "manifest.json"
    bad.write_text(json.dumps({**manifest, "schema": "something-else/1"}))
    with pytest.raises(ValueError, match="expected 'arcology-manifest/0'"):
        assemble(bad)
