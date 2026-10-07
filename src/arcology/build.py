"""Element builder: resolved plan -> element library + placement manifest (Blender).

Each unique (recipe, params, LOD) is built once in the element's own frame and exported as
one .glb. The manifest lists every placement; array elements stay as one row with their
grid, which an assembler expands (Blender now, Unreal instanced meshes later). Instancing
lives here because Blender's exporters don't preserve it (docs/PLAN.md, appendix A).

Recipes are built from boxes, each with a material, so each mesh matches its element's
extent exactly. Boxes may touch, but never share a face pointing the same way (which would
flicker in a rasteriser such as Unreal's).
"""

import json
from collections.abc import Callable
from pathlib import Path

import bpy

from arcology.plan import LODS, Plan, element_key
from arcology.resolve import MULLION_DEPTH

MANIFEST_SCHEMA = "arcology-manifest/0"

MATERIALS = {
    "stone": {"base_color": [0.62, 0.58, 0.52], "roughness": 0.85, "metallic": 0.0},
    "spandrel": {"base_color": [0.16, 0.12, 0.09], "roughness": 0.55, "metallic": 0.6},
    "glass": {"base_color": [0.05, 0.07, 0.09], "roughness": 0.08, "metallic": 0.0},
    "metal": {"base_color": [0.55, 0.42, 0.22], "roughness": 0.35, "metallic": 1.0},
}

type Box = tuple[tuple[float, float, float], tuple[float, float, float], str]

# Box faces as vertex-index quads with outward normals: bottom, top, -Y, +X, +Y, -X.
_FACES = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]


def _material(name: str) -> bpy.types.Material:
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name)
        bsdf = mat.node_tree.nodes["Principled BSDF"]
        spec = MATERIALS[name]
        bsdf.inputs["Base Color"].default_value = (*spec["base_color"], 1.0)
        bsdf.inputs["Roughness"].default_value = spec["roughness"]
        bsdf.inputs["Metallic"].default_value = spec["metallic"]
    return mat


def mesh_from_boxes(name: str, boxes: list[Box]) -> bpy.types.Mesh:
    """One mesh of axis-aligned boxes; degenerate boxes are skipped."""
    verts, faces, slots, face_slots = [], [], [], []
    for (x0, y0, z0), (x1, y1, z1), material in boxes:
        if min(x1 - x0, y1 - y0, z1 - z0) <= 1e-6:
            continue
        if material not in slots:
            slots.append(material)
        base = len(verts)
        verts += [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0)]
        verts += [(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
        faces += [tuple(base + i for i in f) for f in _FACES]
        face_slots += [slots.index(material)] * 6
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    for material in slots:
        me.materials.append(_material(material))
    me.polygons.foreach_set("material_index", face_slots)
    me.update()
    return me


def _mass_box(p: dict) -> list[Box]:
    w, d = p["width"] / 2, p["depth"] / 2
    return [((-w, -d, 0), (w, d, p["height"]), "stone")]


def _pier_strip(p: dict) -> list[Box]:
    w = p["width"] / 2
    return [((-w, 0, 0), (w, p["depth"], p["height"]), "stone")]


def _pier_corner(p: dict) -> list[Box]:
    """L-shaped corner: the end half-piers of the two facades meeting at the corner."""
    arm, dd, h = p["arm"], p["depth"], p["height"]
    boxes = [((-arm, 0, 0), (0, dd, h), "stone")]
    if dd > arm:
        boxes.append(((-dd, 0, 0), (-arm, arm, h), "stone"))
    else:
        boxes.append(((-dd, dd, 0), (0, arm, h), "stone"))
    return boxes


def _window_deco_tall(p: dict) -> list[Box]:
    """A glazed channel between two piers: dark spandrel below, glass above, bronze mullions
    and a transom bar between them. Nothing stone stands between the piers, so stacked
    windows form continuous vertical channels and the piers read as unbroken ribs.
    """
    cw, h, recess, sill = p["width"] / 2, p["height"], p["recess"], p["sill"]
    back = p["front"] + recess
    bar = MULLION_DEPTH
    boxes = [
        ((-cw, p["front"] + recess / 2, 0), (cw, back + p["glass"], sill), "spandrel"),
        ((-cw, back, sill), (cw, back + p["glass"], h), "glass"),
        ((-cw, back - bar, sill), (cw, back, sill + 0.08), "metal"),
    ]
    for i in range(1, p["mullions"] + 1):
        x = -cw + 2 * cw * i / (p["mullions"] + 1)
        boxes.append(((x - 0.04, back - bar, sill + 0.08), (x + 0.04, back, h), "metal"))
    return boxes


def _entrance_deco_main(p: dict) -> list[Box]:
    """Stepped surround, glazed doors, canopy, plinth and a stepped crest above."""
    k, sp, sw = p["frames"], p["frame_step"], p["frame_width"]
    hw0, h, dd = p["width"] / 2, p["height"], p["depth"]
    proj, plinth_top, glass = k * sp, 0.3, 0.05
    boxes = []
    for j in range(k):
        outer, inner = hw0 - j * sw, hw0 - (j + 1) * sw
        top, inner_top, front = h - j * sw, h - (j + 1) * sw, -(k - j) * sp
        boxes += [
            ((-outer, front, 0), (-inner, dd, top), "stone"),
            ((inner, front, 0), (outer, dd, top), "stone"),
            ((-inner, front, inner_top), (inner, dd, top), "stone"),
        ]
    hwk, topk = hw0 - k * sw, h - k * sw
    door = p["door_height"]
    boxes += [
        ((-hw0 - p["apron"], -(proj + p["plinth"]), 0), (hw0 + p["apron"], 0, plinth_top), "stone"),
        ((-hwk, 0, 0), (hwk, dd - glass, plinth_top), "stone"),
        ((-hwk, dd - glass, plinth_top), (hwk, dd, topk), "glass"),
        ((-hwk - 0.4, -(proj + 1.5), door), (hwk + 0.4, dd - glass, door + 0.35), "metal"),
    ]
    for i in range(1, p["mullions"] + 1):
        x = -hwk + 2 * hwk * i / (p["mullions"] + 1)
        boxes.append(
            ((x - 0.06, dd - glass - 0.12, plinth_top), (x + 0.06, dd - glass, topk), "metal")
        )
    for i, share in enumerate((0.5, 0.32, 0.14)):
        z = h + i * p["crest"] / 3
        boxes.append(
            ((-hw0 * share, -(proj - i * sp), z), (hw0 * share, 0, z + p["crest"] / 3), "stone")
        )
    return boxes


# recipe name -> boxes(params), in the element's frame (see plan.py)
RECIPES: dict[str, Callable[[dict], list[Box]]] = {
    "mass.box": _mass_box,
    "pier.strip": _pier_strip,
    "pier.corner": _pier_corner,
    "window.deco_tall": _window_deco_tall,
    "entrance.deco_main": _entrance_deco_main,
}


def build_mesh(recipe: str, params: dict, name: str) -> bpy.types.Mesh:
    return mesh_from_boxes(name, RECIPES[recipe](params))


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
    rows = []
    for e in plan.elements:
        if lod not in e.lod:
            continue
        key = element_key(e, lod)
        if key not in library:
            _export(build_mesh(e.recipe, e.params, key), elements_dir / f"{key}.glb")
            library[key] = {
                "recipe": e.recipe,
                "params": e.params,
                "extent": [list(e.extent[0]), list(e.extent[1])],
                "file": f"elements/{key}.glb",
            }
        row = {
            "id": e.id,
            "element": key,
            "translation": list(e.translation),
            "rotation_z_deg": e.rotation_z_deg,
            "tags": e.tags,
        }
        if e.array is not None:
            row["array"] = e.array
        rows.append(row)

    manifest = {
        "schema": MANIFEST_SCHEMA,
        "plan_schema": plan.schema,
        "seed": plan.seed,
        "lod": lod,
        # Instance transforms are Z-up metres. Library files are standard glTF (Y-up),
        # which glTF importers (Blender's, Unreal's) convert on import. A row with "array"
        # stands for a grid: copy i,j,... sits at translation + sum(index * step).
        "units": "m",
        "up": "Z",
        "materials": MATERIALS,
        "library": dict(sorted(library.items())),
        "instances": rows,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest
