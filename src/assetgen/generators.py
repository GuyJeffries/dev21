"""Seeded generators for low-poly props.

Every asset is built at the origin: centred in X/Y and resting on z=0, so a game
engine can drop it straight onto the ground. Rocks sink slightly below z=0 so
they don't look like they're floating.
"""

import math
import random

import bpy
from mathutils import Matrix, Vector, noise

from assetgen.scene import material, reset, select_only

# Fraction of a rock's height that sits below the ground plane.
ROCK_SINK = 0.2

# Triangle budgets per asset kind; tests fail if a generator change exceeds them.
TRI_BUDGET = {"rock": 150, "tree": 120}


def _rest_on_ground(ob: bpy.types.Object, sink: float = 0.0) -> None:
    """Move the mesh so its bounds are centred in X/Y and its base is at -sink * height."""
    me = ob.data
    xs, ys, zs = zip(*(v.co for v in me.vertices), strict=True)
    height = max(zs) - min(zs)
    shift = Vector((-(min(xs) + max(xs)) / 2, -(min(ys) + max(ys)) / 2, -min(zs) - sink * height))
    me.transform(Matrix.Translation(shift))
    me.update()


def make_rock(rng: random.Random, name: str) -> bpy.types.Object:
    size = rng.uniform(0.4, 0.8)
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=3, radius=size, location=(0, 0, 0))
    ob = bpy.context.object
    ob.name = ob.data.name = name

    offset = Vector((rng.uniform(0, 100), rng.uniform(0, 100), rng.uniform(0, 100)))
    for v in ob.data.vertices:
        v.co *= 1.0 + 0.35 * noise.noise(v.co * 1.7 + offset)
        v.co.z *= 0.6

    decimate = ob.modifiers.new("decimate", "DECIMATE")
    decimate.ratio = 0.35
    bpy.ops.object.modifier_apply(modifier=decimate.name)

    _rest_on_ground(ob, sink=ROCK_SINK)
    bpy.ops.object.shade_flat()
    ob.data.materials.append(material(f"{name}_stone", (0.35, 0.33, 0.3)))
    return ob


def make_tree(rng: random.Random, name: str) -> bpy.types.Object:
    height = rng.uniform(1.6, 2.6)
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=7, radius=0.12, depth=height, location=(0, 0, height / 2)
    )
    trunk = bpy.context.object
    trunk.data.materials.append(material(f"{name}_bark", (0.25, 0.15, 0.08)))

    parts = [trunk]
    for i in range(rng.randint(2, 4)):
        bpy.ops.mesh.primitive_cone_add(
            vertices=8, radius1=0.9 - i * 0.18, depth=0.9, location=(0, 0, height * 0.55 + i * 0.45)
        )
        cone = bpy.context.object
        cone.rotation_euler.z = rng.uniform(0, math.pi)
        cone.data.materials.append(material(f"{name}_leaf{i}", (0.1, 0.35 + 0.05 * i, 0.12)))
        parts.append(cone)

    bpy.ops.object.select_all(action="DESELECT")
    for part in parts:
        part.select_set(True)
    bpy.context.view_layer.objects.active = trunk
    bpy.ops.object.join()

    tree = trunk
    tree.name = tree.data.name = name
    select_only(tree)
    # The joined mesh still carries the trunk's offset; bake it in so the origin is the base.
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    _rest_on_ground(tree)
    bpy.ops.object.shade_flat()
    return tree


def build_set(seed: int, rocks: int = 4, trees: int = 3) -> list[bpy.types.Object]:
    """Reset the scene and generate a seeded set of props, all at the origin."""
    reset()
    rng = random.Random(seed)
    objs = [make_rock(rng, f"rock_{i}") for i in range(rocks)]
    objs += [make_tree(rng, f"tree_{i}") for i in range(trees)]
    return objs


def scatter(
    rng: random.Random, n: int, extent: float, min_dist: float, max_tries: int = 1000
) -> list[Vector]:
    """Pick n 2D points in [-extent, extent]^2, each at least min_dist from the others."""
    pts: list[Vector] = []
    for _ in range(max_tries * max(n, 1)):
        if len(pts) == n:
            return pts
        p = Vector((rng.uniform(-extent, extent), rng.uniform(-extent, extent)))
        if all((p - q).length >= min_dist for q in pts):
            pts.append(p)
    if len(pts) == n:
        return pts
    raise ValueError(f"could not place {n} points {min_dist} apart within ±{extent}")
