"""Stand-in assembler: placement manifest + element library -> instanced Blender scene.

Mirrors what the Unreal assembler will do in Phase 7: import each library mesh once, then
place every instance as an object sharing that mesh. Reading only the handover package
(not the plan) proves the package is enough to rebuild the scene.
"""

import json
import math
from pathlib import Path

import bpy

from arcology.build import MANIFEST_SCHEMA


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
    for inst in manifest["instances"]:
        ob = bpy.data.objects.new(inst["id"], meshes[inst["element"]])
        ob["arcology_id"] = inst["id"]  # object names are length-limited; this isn't
        ob.location = inst["translation"]
        ob.rotation_euler.z = math.radians(inst["rotation_z_deg"])
        coll.objects.link(ob)
        objects.append(ob)
    return objects
