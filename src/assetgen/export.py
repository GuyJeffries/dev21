"""glTF export plus a manifest of per-asset stats for reviewing changes."""

import json
from pathlib import Path

import bpy

from assetgen.scene import select_only


def mesh_stats(ob: bpy.types.Object) -> dict:
    me = ob.data
    me.calc_loop_triangles()
    lo = [min(v.co[i] for v in me.vertices) for i in range(3)]
    hi = [max(v.co[i] for v in me.vertices) for i in range(3)]
    return {
        "name": ob.name,
        "verts": len(me.vertices),
        "tris": len(me.loop_triangles),
        "materials": len(me.materials),
        "bounds_min": [round(x, 4) for x in lo],
        "bounds_max": [round(x, 4) for x in hi],
    }


def export_glb(ob: bpy.types.Object, path: Path) -> None:
    select_only(ob)
    bpy.ops.export_scene.gltf(filepath=str(path), export_format="GLB", use_selection=True)


def export_set(objs: list[bpy.types.Object], out_dir: Path, seed: int) -> dict:
    """Write one .glb per object and a manifest.json describing them.

    The manifest has no timestamps or absolute paths, so diffing it between
    commits shows exactly what a generator change did to the assets.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    assets = []
    for ob in objs:
        export_glb(ob, out_dir / f"{ob.name}.glb")
        assets.append({**mesh_stats(ob), "file": f"{ob.name}.glb"})
    manifest = {"seed": seed, "assets": assets}
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest
