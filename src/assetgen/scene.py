"""Small Blender scene helpers shared by the generators and the preview renderer."""

import bpy


def reset() -> None:
    """Start from an empty factory scene so output depends only on the seed."""
    bpy.ops.wm.read_factory_settings(use_empty=True)


def material(
    name: str, rgb: tuple[float, float, float], roughness: float = 0.8
) -> bpy.types.Material:
    mat = bpy.data.materials.new(name)
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*rgb, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    return mat


def select_only(ob: bpy.types.Object) -> None:
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
