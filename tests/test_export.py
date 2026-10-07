import json
import struct

import pytest

from assetgen import build_set, export_set
from assetgen.__main__ import main


def read_glb(path):
    """Check a binary glTF header and return its JSON chunk."""
    data = path.read_bytes()
    magic, version, length = struct.unpack_from("<4sII", data, 0)
    assert (magic, version, length) == (b"glTF", 2, len(data)), path.name
    chunk_len, chunk_type = struct.unpack_from("<I4s", data, 12)
    assert chunk_type == b"JSON", path.name
    return json.loads(data[20 : 20 + chunk_len])


def test_one_glb_per_asset(exported):
    out, manifest = exported
    names = [a["name"] for a in manifest["assets"]]
    assert names == ["rock_0", "rock_1", "rock_2", "rock_3", "tree_0", "tree_1", "tree_2"]
    assert sorted(p.name for p in out.glob("*.glb")) == sorted(
        a["file"] for a in manifest["assets"]
    )
    assert json.loads((out / "manifest.json").read_text()) == manifest


def test_glb_matches_blender_mesh(exported):
    out, manifest = exported
    for asset in manifest["assets"]:
        gltf = read_glb(out / asset["file"])
        assert gltf["asset"]["version"] == "2.0"
        assert len(gltf["meshes"]) == len(gltf["nodes"]) == 1, asset["name"]
        assert gltf["nodes"][0].get("translation", [0, 0, 0]) == [0, 0, 0], asset["name"]

        prims = gltf["meshes"][0]["primitives"]
        tris = sum(gltf["accessors"][p["indices"]]["count"] // 3 for p in prims)
        assert tris == asset["tris"], asset["name"]
        assert len(gltf.get("materials", [])) == asset["materials"], asset["name"]

        # glTF is Y-up: Blender (x, y, z) is exported as (x, z, -y).
        positions = [gltf["accessors"][p["attributes"]["POSITION"]] for p in prims]
        lo = [min(acc["min"][i] for acc in positions) for i in range(3)]
        hi = [max(acc["max"][i] for acc in positions) for i in range(3)]
        bmin, bmax = asset["bounds_min"], asset["bounds_max"]
        assert lo == pytest.approx([bmin[0], bmin[2], -bmax[1]], abs=1e-3), asset["name"]
        assert hi == pytest.approx([bmax[0], bmax[2], -bmin[1]], abs=1e-3), asset["name"]


def test_export_is_byte_for_byte_reproducible(exported, tmp_path):
    out, manifest = exported
    assert export_set(build_set(manifest["seed"]), tmp_path, manifest["seed"]) == manifest
    for asset in manifest["assets"]:
        assert (tmp_path / asset["file"]).read_bytes() == (out / asset["file"]).read_bytes()


def test_cli_writes_assets_and_manifest(tmp_path, capsys):
    assert main(["--seed", "3", "--rocks", "1", "--trees", "1", "--out", str(tmp_path)]) == 0
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "manifest.json",
        "rock_0.glb",
        "tree_0.glb",
    ]
    assert "tree_0:" in capsys.readouterr().out
