import json

import bpy
import pytest
from mathutils import Vector

from arcology.assemble import assemble
from arcology.plan import element_bounds


def test_scene_rebuilt_from_handover_package_matches_plan(plan, built):
    out, manifest = built
    bpy.ops.wm.read_factory_settings(use_empty=True)
    objects = assemble(out / "manifest.json")
    bpy.context.view_layer.update()

    assert len(objects) == len(manifest["instances"])
    assert {o.data.name for o in objects} == set(manifest["library"])  # shared, not copied
    for ob in objects:
        corners = [ob.matrix_world @ Vector(c) for c in ob.bound_box]
        lo = [min(c[i] for c in corners) for i in range(3)]
        hi = [max(c[i] for c in corners) for i in range(3)]
        expected_lo, expected_hi = element_bounds(plan.element(ob["arcology_id"]))
        assert lo == pytest.approx(list(expected_lo), abs=1e-3), ob["arcology_id"]
        assert hi == pytest.approx(list(expected_hi), abs=1e-3), ob["arcology_id"]


def test_rejects_unknown_manifest_schema(built, tmp_path):
    out, manifest = built
    bad = tmp_path / "manifest.json"
    bad.write_text(json.dumps({**manifest, "schema": "something-else/1"}))
    with pytest.raises(ValueError, match="expected 'arcology-manifest/0'"):
        assemble(bad)
