import json
import struct
from dataclasses import replace

import bpy
import pytest
from mathutils import Vector

from arcology.build import (
    MANIFEST_SCHEMA,
    MATERIALS,
    RECIPES,
    build_library,
    build_mesh,
    mesh_from_boxes,
)
from arcology.plan import element_key


def read_glb(path):
    data = path.read_bytes()
    magic, version, length = struct.unpack_from("<4sII", data, 0)
    assert (magic, version, length) == (b"glTF", 2, len(data))
    chunk_len, chunk_type = struct.unpack_from("<I4s", data, 12)
    assert chunk_type == b"JSON"
    return json.loads(data[20 : 20 + chunk_len])


def test_manifest_has_one_row_per_plan_element_at_the_lod(plan, built):
    out, manifest = built
    assert manifest["schema"] == MANIFEST_SCHEMA
    assert [r["id"] for r in manifest["instances"]] == [
        e.id for e in plan.elements if "L2" in e.lod
    ]
    assert all(
        ("array" in r) == (plan.element(r["id"]).array is not None) for r in manifest["instances"]
    )
    assert json.loads((out / "manifest.json").read_text()) == manifest
    files = sorted(p.name for p in (out / "elements").glob("*.glb"))
    assert files == sorted(f"{key}.glb" for key in manifest["library"])


def test_every_recipe_mesh_matches_its_element_extent(plan):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    assert {e.recipe for e in plan.elements} == set(RECIPES)  # the plan exercises every recipe
    for e in {element_key(e, "L0"): e for e in plan.elements}.values():
        me = build_mesh(e.recipe, e.params, "probe")
        lo = [min(v.co[i] for v in me.vertices) for i in range(3)]
        hi = [max(v.co[i] for v in me.vertices) for i in range(3)]
        assert lo == pytest.approx(list(e.extent[0]), abs=1e-3), e.id
        assert hi == pytest.approx(list(e.extent[1]), abs=1e-3), e.id
        assert {m.name for m in me.materials} <= set(MATERIALS), e.id


def test_library_glb_matches_extent(built):
    out, manifest = built
    for key, entry in manifest["library"].items():
        gltf = read_glb(out / entry["file"])
        accessors = [
            gltf["accessors"][p["attributes"]["POSITION"]] for p in gltf["meshes"][0]["primitives"]
        ]
        lo = [min(a["min"][i] for a in accessors) for i in range(3)]
        hi = [max(a["max"][i] for a in accessors) for i in range(3)]
        (x0, y0, z0), (x1, y1, z1) = entry["extent"]
        # glTF is Y-up: Blender (x, y, z) is stored as (x, z, -y).
        assert lo == pytest.approx([x0, z0, -y1], abs=1e-3), key
        assert hi == pytest.approx([x1, z1, -y0], abs=1e-3), key


def test_box_faces_point_outwards():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    boxes = [((-1, -2, 0), (1, 2, 3), "stone"), ((2, 0, 1), (4, 1, 2), "metal")]
    me = mesh_from_boxes("boxes", boxes)
    assert len(me.polygons) == 12
    assert [m.name for m in me.materials] == ["stone", "metal"]
    for poly in me.polygons:
        lo, hi, material = boxes[poly.index // 6]
        centre = (Vector(lo) + Vector(hi)) / 2
        assert poly.normal.dot(poly.center - centre) > 0
        assert me.materials[poly.material_index].name == material


def test_identical_elements_share_one_library_mesh(plan, tmp_path):
    core = plan.element("arcology/tower.central/section.3/core")
    twin = replace(core, id="arcology/twin", translation=(500.0, 0.0, 0.0))
    manifest = build_library(replace(plan, elements=(*plan.elements, twin)), tmp_path, "L2")
    assert manifest["instances"][-1]["element"] == element_key(core, "L2")
    assert sum(r["element"] == element_key(core, "L2") for r in manifest["instances"]) == 2


def test_lod_filters_elements(plan, tmp_path):
    manifest = build_library(plan, tmp_path, "L3")
    expected = {e.id for e in plan.elements if e.kind in ("mass", "crown")}  # envelope + skyline
    assert {r["id"] for r in manifest["instances"]} == expected


def test_library_is_byte_for_byte_reproducible(plan, built, tmp_path):
    out, manifest = built
    build_library(plan, tmp_path, "L2")
    assert (tmp_path / "manifest.json").read_bytes() == (out / "manifest.json").read_bytes()
    for entry in manifest["library"].values():
        assert (tmp_path / entry["file"]).read_bytes() == (out / entry["file"]).read_bytes()
