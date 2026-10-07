"""Element builder: resolved plan -> element library + placement manifest (Blender).

Each unique (recipe, params, LOD) is built once, centred in X/Y with its base on z=0, and
exported as one .glb. The manifest lists every instance by element key. Together they
are the handover package an assembler turns into a scene (Blender now, Unreal later).
Instancing lives here because Blender's exporters don't preserve it (docs/PLAN.md, App. A).
"""

import hashlib
import json
from collections.abc import Callable
from pathlib import Path

import bpy

from arcology.plan import LODS, Element, Plan

MANIFEST_SCHEMA = "arcology-manifest/0"

MATERIALS = {
    "stone": {"base_color": [0.62, 0.58, 0.52], "roughness": 0.85},
}


def element_key(e: Element, lod: str) -> str:
    blob = json.dumps({"recipe": e.recipe, "params": e.params, "lod": lod}, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def _material(name: str) -> bpy.types.Material:
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name)
        bsdf = mat.node_tree.nodes["Principled BSDF"]
        bsdf.inputs["Base Color"].default_value = (*MATERIALS[name]["base_color"], 1.0)
        bsdf.inputs["Roughness"].default_value = MATERIALS[name]["roughness"]
    return mat


def _box(name: str, params: dict, lod: str) -> bpy.types.Mesh:
    w, d, h = params["width"] / 2, params["depth"] / 2, params["height"]
    verts = [(-w, -d, 0), (w, -d, 0), (w, d, 0), (-w, d, 0)]
    verts += [(x, y, h) for x, y, _ in verts]
    faces = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    me.materials.append(_material("stone"))
    return me


# recipe name -> builder(mesh name, params, lod) returning a mesh at the origin
RECIPES: dict[str, Callable[[str, dict, str], bpy.types.Mesh]] = {"mass.box": _box}


def _export(me: bpy.types.Mesh, path: Path) -> None:
    ob = bpy.data.objects.new(me.name, me)
    bpy.context.scene.collection.objects.link(ob)
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.export_scene.gltf(filepath=str(path), export_format="GLB", use_selection=True)
    bpy.data.objects.remove(ob)


def build_library(plan: Plan, out_dir: str | Path, lod: str = "L2") -> dict:
    """Write elements/<key>.glb for each unique element at `lod`, plus manifest.json."""
    if lod not in LODS:
        raise ValueError(f"lod must be one of {LODS}, got {lod!r}")
    out_dir = Path(out_dir)
    elements_dir = out_dir / "elements"
    elements_dir.mkdir(parents=True, exist_ok=True)
    for stale in elements_dir.glob("*.glb"):
        stale.unlink()

    bpy.ops.wm.read_factory_settings(use_empty=True)
    library: dict[str, dict] = {}
    instances = []
    for e in plan.elements:
        if lod not in e.lod:
            continue
        key = element_key(e, lod)
        if key not in library:
            _export(RECIPES[e.recipe](key, e.params, lod), elements_dir / f"{key}.glb")
            library[key] = {"recipe": e.recipe, "params": e.params, "file": f"elements/{key}.glb"}
        instances.append(
            {
                "id": e.id,
                "element": key,
                "translation": list(e.translation),
                "rotation_z_deg": e.rotation_z_deg,
                "tags": e.tags,
            }
        )

    manifest = {
        "schema": MANIFEST_SCHEMA,
        "plan_schema": plan.schema,
        "seed": plan.seed,
        "lod": lod,
        # Instance transforms are Z-up metres. Library files are standard glTF (Y-up),
        # which glTF importers (Blender's, Unreal's) convert on import.
        "units": "m",
        "up": "Z",
        "materials": MATERIALS,
        "library": dict(sorted(library.items())),
        "instances": instances,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest
