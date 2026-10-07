"""Render a preview image of a generated set, for eyeballing changes.

Only Cycles on the CPU is used: with no GPU or libEGL, EEVEE kills the whole
process instead of raising an error.
"""

import math
import random
from pathlib import Path

import bpy
from mathutils import Vector

from assetgen.generators import scatter
from assetgen.scene import material


def frame_camera(
    cam: bpy.types.Object,
    objs: list[bpy.types.Object],
    direction: Vector = Vector((1, -1, 0.75)),  # noqa: B008 (mathutils Vector, never mutated)
) -> None:
    """Aim the camera at the objects' bounds and back off until they all fit."""
    pts = [ob.matrix_world @ Vector(corner) for ob in objs for corner in ob.bound_box]
    centre = sum(pts, Vector()) / len(pts)
    radius = max((p - centre).length for p in pts)
    fov = min(cam.data.angle_x, cam.data.angle_y)
    cam.location = centre + direction.normalized() * radius / math.sin(fov / 2) * 1.05
    cam.rotation_euler = (centre - cam.location).to_track_quat("-Z", "Y").to_euler()


def render_preview(
    objs: list[bpy.types.Object],
    path: Path,
    seed: int,
    resolution: tuple[int, int] = (640, 400),
    samples: int = 24,
) -> None:
    """Lay the objects out on a ground plane and render them to a PNG.

    This moves the objects, so export them before calling it.
    """
    extent = 1.5 * math.sqrt(len(objs))
    spots = scatter(random.Random(seed), len(objs), extent=extent, min_dist=2.2)
    for ob, spot in zip(objs, spots, strict=True):
        ob.location = (spot.x, spot.y, 0)

    bpy.ops.mesh.primitive_plane_add(size=2 * extent + 4)
    bpy.context.object.data.materials.append(material("ground", (0.45, 0.5, 0.3)))

    bpy.ops.object.light_add(type="SUN", location=(0, 0, 10))
    sun = bpy.context.object
    sun.data.energy = 3.0
    sun.rotation_euler = (math.radians(40), math.radians(20), 0)

    world = bpy.data.worlds.new("preview_sky")
    # Blender 5 worlds render from their node tree; world.color is ignored.
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.6, 0.7, 0.85, 1.0)

    bpy.ops.object.camera_add()
    cam = bpy.context.object

    scene = bpy.context.scene
    scene.world = world
    scene.camera = cam
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = samples
    scene.render.resolution_x, scene.render.resolution_y = resolution
    scene.render.resolution_percentage = 100
    scene.render.filepath = str(path)

    bpy.context.view_layer.update()  # refresh matrix_world after moving the objects
    frame_camera(cam, objs)
    bpy.ops.render.render(write_still=True)
