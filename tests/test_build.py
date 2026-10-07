import json
import struct
from dataclasses import replace

import bpy
import pytest
from mathutils import Vector

from arcology.build import MANIFEST_SCHEMA, RECIPES, build_library, element_key


def read_glb(path):
    data = path.read_bytes()
    magic, version, length = struct.unpack_from("<4sII", data, 0)
    assert (magic, version, length) == (b"glTF", 2, len(data))
    chunk_len, chunk_type = struct.unpack_from("<I4s", data, 12)
    assert chunk_type == b"JSON"
    return json.loads(data[20 : 20 + chunk_len])


def test_manifest_lists_every_element_once(plan, built):
    out, manifest = built
    assert manifest["schema"] == MANIFEST_SCHEMA
    assert [i["id"] for i in manifest["instances"]] == [e.id for e in plan.elements]
    assert json.loads((out / "manifest.json").read_text()) == manifest
    files = sorted(p.name for p in (out / "elements").glob("*.glb"))
    assert files == sorted(f"{key}.glb" for key in manifest["library"])


def test_library_glb_matches_recipe_params(plan, built):
    out, manifest = built
    for key, entry in manifest["library"].items():
        gltf = read_glb(out / entry["file"])
        (prim,) = gltf["meshes"][0]["primitives"]
        pos = gltf["accessors"][prim["attributes"]["POSITION"]]
        w, d, h = (entry["params"][k] for k in ("width", "depth", "height"))
        # glTF is Y-up: Blender (x, y, z) is stored as (x, z, -y). Base centred at the origin.
        assert pos["min"] == pytest.approx([-w / 2, 0, -d / 2], abs=1e-3), key
        assert pos["max"] == pytest.approx([w / 2, h, d / 2], abs=1e-3), key
        assert [m["name"] for m in gltf["materials"]] == ["stone"]


def test_identical_elements_share_one_library_mesh(plan, tmp_path):
    twin = replace(plan.elements[-1], id="arcology/twin", translation=(500.0, 0.0, 0.0))
    manifest = build_library(replace(plan, elements=(*plan.elements, twin)), tmp_path, "L2")
    assert len(manifest["instances"]) == len(plan.elements) + 1
    assert len(manifest["library"]) == len(plan.elements)
    assert manifest["instances"][-1]["element"] == element_key(plan.elements[-1], "L2")


def test_lod_filters_elements(plan, tmp_path):
    hero_only = replace(plan.elements[-1], id="arcology/hero_only", lod=("L0",))
    manifest = build_library(replace(plan, elements=(*plan.elements, hero_only)), tmp_path, "L2")
    assert "arcology/hero_only" not in [i["id"] for i in manifest["instances"]]


def test_box_faces_point_outwards():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    me = RECIPES["mass.box"]("box", {"width": 12.0, "depth": 6.0, "height": 8.0}, "L2")
    centre = Vector((0, 0, 4))
    assert len(me.polygons) == 6
    assert all(p.normal.dot(p.center - centre) > 0 for p in me.polygons)


def test_library_is_byte_for_byte_reproducible(plan, built, tmp_path):
    out, manifest = built
    build_library(plan, tmp_path, "L2")
    assert (tmp_path / "manifest.json").read_bytes() == (out / "manifest.json").read_bytes()
    for entry in manifest["library"].values():
        assert (tmp_path / entry["file"]).read_bytes() == (out / entry["file"]).read_bytes()
