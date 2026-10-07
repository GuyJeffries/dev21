"""Stand-in assembler: placement manifest + element library -> instanced Blender scene.

Mirrors what the Unreal assembler will do in Phase 7: import each library mesh once, then
place every copy as an object sharing that mesh. Array rows expand to one object per grid
position. Reading only the handover package (not the plan) proves the package is enough to
rebuild the scene.
"""

import itertools
import json
import math
from collections.abc import Iterator
from pathlib import Path

import bpy

from arcology.build import MANIFEST_SCHEMA


def placements(row: dict) -> Iterator[tuple[str, list[float]]]:
    """(id, translation) of every copy a manifest row stands for."""
    array = row.get("array")
    if array is None:
        yield row["id"], row["translation"]
        return
    axes = array["axes"]
    for index in itertools.product(*(range(a["count"]) for a in axes)):
        names = [
            f"{a['name']}.{a['start'] + i:0{a['digits']}d}"
            for a, i in zip(axes, index, strict=True)
        ]
        offset = [sum(i * a["step"][k] for a, i in zip(axes, index, strict=True)) for k in range(3)]
        yield (
            "/".join([array["prefix"], *names]),
            [row["translation"][k] + offset[k] for k in range(3)],
        )


def assemble(manifest_path: str | Path, collection: str = "arcology") -> list[bpy.types.Object]:
    path = Path(manifest_path)
    manifest = json.loads(path.read_text())
    if manifest.get("schema") != MANIFEST_SCHEMA:
        raise ValueError(f"{path}: expected {MANIFEST_SCHEMA!r}, got {manifest.get('schema')!r}")

    meshes = {}
    for key, entry in manifest["library"].items():
        before = set(bpy.data.objects)
        bpy.ops.import_scene.gltf(filepath=str(path.parent / entry["file"]))
        imported = [o for o in bpy.data.objects if o not in before]
        mesh_objects = [o for o in imported if o.type == "MESH"]
        if len(mesh_objects) != 1:
            raise ValueError(f"{entry['file']}: expected one mesh, found {len(mesh_objects)}")
        meshes[key] = mesh_objects[0].data
        meshes[key].name = key
        for o in imported:
            bpy.data.objects.remove(o)

    coll = bpy.data.collections.new(collection)
    bpy.context.scene.collection.children.link(coll)
    objects = []
    for row in manifest["instances"]:
        mesh, rotation = meshes[row["element"]], math.radians(row["rotation_z_deg"])
        for element_id, translation in placements(row):
            ob = bpy.data.objects.new(element_id, mesh)
            ob["arcology_id"] = element_id  # object names are length-limited; this isn't
            ob.location = translation
            ob.rotation_euler.z = rotation
            coll.objects.link(ob)
            objects.append(ob)
    return objects
