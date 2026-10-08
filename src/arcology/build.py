"""Element builder: resolved plan -> element library + placement manifest (Blender).

Each unique (recipe, params, LOD) is built once in the element's own frame and exported as
one .glb. The manifest lists every placement; array elements stay as one row with their
grid, which an assembler expands (Blender now, Unreal instanced meshes later). Instancing
lives here because Blender's exporters don't preserve it (docs/PLAN.md, appendix A).

Recipes are built from parts, each with a material: axis-aligned boxes, and prisms (a
polygon in the element's x-z plane extruded along y) for diagonals such as chevrons. Each
mesh matches its element's extent exactly. Parts may touch, but never share a face pointing
the same way (which would flicker in a rasteriser such as Unreal's).
"""

import json
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

import bpy

from arcology.facade import MULLION_DEPTH, NICHE_SURROUND
from arcology.plan import LODS, Plan, element_key
from arcology.rules import carve, mass_boxes, outline

MANIFEST_SCHEMA = "arcology-manifest/0"

MATERIALS = {
    "stone": {"base_color": [0.62, 0.58, 0.52], "roughness": 0.85, "metallic": 0.0},
    "spandrel": {"base_color": [0.16, 0.12, 0.09], "roughness": 0.55, "metallic": 0.6},
    "glass": {"base_color": [0.05, 0.07, 0.09], "roughness": 0.08, "metallic": 0.0},
    "metal": {"base_color": [0.55, 0.42, 0.22], "roughness": 0.35, "metallic": 1.0},
    # The lit back wall of a hall behind an opening, seen through the opening's clear glass.
    "light": {"base_color": [0.95, 0.62, 0.32], "roughness": 0.6, "metallic": 0.0, "emission": 1.2},
    "clear": {
        "base_color": [0.9, 0.95, 1.0],
        "roughness": 0.05,
        "metallic": 0.0,
        "transmission": 1.0,
    },
}

type Box = tuple[tuple[float, float, float], tuple[float, float, float], str]


class Prism(NamedTuple):
    """A simple polygon in the x-z plane (either winding), extruded along y from y0 to y1."""

    points: tuple[tuple[float, float], ...]
    y0: float
    y1: float
    material: str


type Part = Box | Prism

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
        if spec.get("transmission"):
            bsdf.inputs["Transmission Weight"].default_value = spec["transmission"]
        if spec.get("emission"):
            bsdf.inputs["Emission Color"].default_value = (*spec["base_color"], 1.0)
            bsdf.inputs["Emission Strength"].default_value = spec["emission"]
    return mat


def _prism_geometry(prism: Prism, base: int):
    """Vertices and faces with outward normals: front (-y), back (+y), then the sides."""
    pts = list(prism.points)
    area = sum(x0 * z1 - x1 * z0 for (x0, z0), (x1, z1) in zip(pts, pts[1:] + pts[:1], strict=True))
    if area < 0:  # make it counter-clockwise seen from -y (x right, z up), so the front faces -y
        pts.reverse()
    n = len(pts)
    verts = [(x, prism.y0, z) for x, z in pts] + [(x, prism.y1, z) for x, z in pts]
    faces = [tuple(base + i for i in range(n)), tuple(base + n + i for i in reversed(range(n)))]
    faces += [
        (base + i, base + n + i, base + n + (i + 1) % n, base + (i + 1) % n) for i in range(n)
    ]
    return verts, faces


def mesh_from_parts(name: str, parts: list[Part]) -> bpy.types.Mesh:
    """One mesh of boxes and prisms; degenerate parts are skipped."""
    verts, faces, slots, face_slots = [], [], [], []
    for part in parts:
        if isinstance(part, Prism):
            if part.y1 - part.y0 <= 1e-6:
                continue
            new_verts, new_faces = _prism_geometry(part, len(verts))
            material = part.material
        else:
            (x0, y0, z0), (x1, y1, z1), material = part
            if min(x1 - x0, y1 - y0, z1 - z0) <= 1e-6:
                continue
            new_verts = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0)]
            new_verts += [(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
            new_faces = [tuple(len(verts) + i for i in f) for f in _FACES]
        if material not in slots:
            slots.append(material)
        verts += new_verts
        faces += new_faces
        face_slots += [slots.index(material)] * len(new_faces)
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    for material in slots:
        me.materials.append(_material(material))
    me.polygons.foreach_set("material_index", face_slots)
    me.update()
    return me


mesh_from_boxes = mesh_from_parts  # boxes are parts too


def _carved(boxes: list[Box], p: dict) -> list[Box]:
    """`boxes` less the `cuts` in `p` ([x0, y0, z0, x1, y1, z1] each), as boxes that tile
    what is left."""
    cuts = [((c[0], c[1], c[2]), (c[3], c[4], c[5])) for c in p.get("cuts", ())]
    return [(lo, hi, m) for lo0, hi0, m in boxes for lo, hi in carve((lo0, hi0), cuts)]


def _mass(p: dict) -> list[Box]:
    """A mass, or a core less the spaces carved behind openings and recesses; with `notch`, a
    cross of three boxes."""
    return [(lo, hi, "stone") for lo, hi in mass_boxes(p)]


def _pier_inner(p: dict) -> list[Box]:
    """Re-entrant corner: the two facades' end half-piers and the square between them.
    Local x runs along the incoming edge to the corner, local y inward from it."""
    arm, dd, h = p["arm"], p["depth"], p["height"]
    return [
        ((-arm, 0, 0), (0, dd, h), "stone"),
        ((0, -arm, 0), (dd, 0, h), "stone"),
        ((0, 0, 0), (dd, dd, h), "stone"),
    ]


def _pier_strip(p: dict) -> list[Box]:
    """A pier on a bay line; minor piers stand back from the envelope by `front`."""
    w = p["width"] / 2
    return [((-w, p.get("front", 0.0), 0), (w, p["depth"], p["height"]), "stone")]


def _pier_banded(p: dict) -> list[Box]:
    """A pier on a horizontal axis. Up each stretch of the shaft (`bands`: [first floor,
    count] pairs, from the pier's foot) it is glass at the glass line, carrying each floor's
    stone spandrel band across the bay line, so the windows read as continuous ribbons;
    elsewhere (base, sky lobbies, capital), stone standing back to `front`."""
    w, fh, sill, dd = p["width"] / 2, p["floor_height"], p["sill"], p["depth"]
    boxes, z = [], 0.0
    for first, count in p["bands"]:
        z0, z1 = first * fh, (first + count) * fh
        if z0 > z:
            boxes.append(((-w, p["front"], z), (w, dd, z0), "stone"))
        boxes.append(((-w, p["glass"], z0), (w, dd, z1), "glass"))
        for k in range(first, first + count):
            boxes.append(((-w, p["band"], k * fh), (w, p["glass"], k * fh + sill), "stone"))
        z = z1
    if z < p["height"]:
        boxes.append(((-w, p["front"], z), (w, dd, p["height"]), "stone"))
    return boxes


def _pier_fluted(p: dict) -> list[Box]:
    """A pilaster faced with reeds: flutes + 1 ribs standing `reed` proud of its face, with
    a flute between each pair."""
    w, dd, h, reed = p["width"] / 2, p["depth"], p["height"], p["reed"]
    ribs = p["flutes"] + 1
    u = 2 * w / (2 * ribs - 1)
    boxes = [((-w, reed, 0), (w, dd, h), "stone")]
    boxes += [
        ((-w + 2 * i * u, 0, 0), (-w + (2 * i + 1) * u, reed, h), "stone") for i in range(ribs)
    ]
    return boxes


def _pier_corner(p: dict) -> list[Box]:
    """L-shaped corner: the end half-piers of the two facades meeting at the corner."""
    arm, dd, h = p["arm"], p["depth"], p["height"]
    boxes = [((-arm, 0, 0), (0, dd, h), "stone")]
    if dd > arm:
        boxes.append(((-dd, 0, 0), (-arm, arm, h), "stone"))
    else:
        boxes.append(((-dd, dd, 0), (0, arm, h), "stone"))
    return boxes


def _chevrons(p: dict, cw: float, sill: float, face: float, band: float) -> list[Part]:
    """Nested bronze chevrons standing `relief` proud of a panel whose front is at `face`."""
    parts: list[Part] = []
    rise, xw = p["rise"], 0.8 * cw
    for k in range(p["chevrons"]):
        z = 0.2 * sill + k * 1.6 * band
        points = (
            (-xw, z),
            (0, z + rise),
            (xw, z),
            (xw, z + band),
            (0, z + rise + band),
            (-xw, z + band),
        )
        parts.append(Prism(points, face - p["relief"], face, "metal"))
    return parts


def _window_deco_tall(p: dict) -> list[Part]:
    """A glazed channel between two piers: dark spandrel below, glass above, bronze mullions
    and a transom bar between them. Nothing stone stands between the piers, so stacked
    windows form continuous vertical channels and the piers read as unbroken ribs.

    With `band` (window.deco_band, a horizontal axis) the spandrel is a stone band standing
    forward to `band`, which banded piers carry on across the bay lines. A rich window
    (`chevrons`) carries bronze chevrons on its spandrel.
    """
    cw, h, recess, sill = p["width"] / 2, p["height"], p["recess"], p["sill"]
    back = p["front"] + recess
    bar = MULLION_DEPTH
    spandrel = (p["band"], "stone") if "band" in p else (p["front"] + recess / 2, "spandrel")
    if p.get("chevrons") and "band" not in p:  # rich: a bronze spandrel under its chevrons
        spandrel = (spandrel[0], "metal")
    boxes = [
        ((-cw, spandrel[0], 0), (cw, back + p["glass"], sill), spandrel[1]),
        ((-cw, back, sill), (cw, back + p["glass"], h), "glass"),
        ((-cw, back - bar, sill), (cw, back, sill + 0.08), "metal"),
    ]
    for i in range(1, p["mullions"] + 1):
        x = -cw + 2 * cw * i / (p["mullions"] + 1)
        boxes.append(((x - 0.04, back - bar, sill + 0.08), (x + 0.04, back, h), "metal"))
    if p.get("chevrons"):
        boxes += _chevrons(p, cw, sill, spandrel[0], p["chevron_band"])
    return boxes


def _window_deco_capital(p: dict) -> list[Part]:
    """A capital window: a stone panel below shorter glass, a stone head with corbels at
    its corners, and nested bronze chevrons standing on the panel."""
    cw, h, sill, head, c = p["width"] / 2, p["height"], p["sill"], p["head"], p["corbel"]
    panel, back, glass, bar = (
        p["front"] + p["recess"] / 2,
        p["front"] + p["recess"],
        p["glass"],
        MULLION_DEPTH,
    )
    top = h - head
    parts: list[Part] = [
        ((-cw, panel, 0), (cw, back + glass, sill), "stone"),
        ((-cw, panel, top), (cw, back + glass, h), "stone"),
        ((-cw, back, sill), (cw, back + glass, top), "glass"),
        ((-cw, panel, top - c), (-cw + c, back, top), "stone"),
        ((cw - c, panel, top - c), (cw, back, top), "stone"),
        ((-cw, back - bar, sill), (cw, back, sill + 0.08), "metal"),
    ]
    for i in range(1, p["mullions"] + 1):
        x = -cw + 2 * cw * i / (p["mullions"] + 1)
        parts.append(((x - 0.04, back - bar, sill + 0.08), (x + 0.04, back, top), "metal"))
    if p.get("chevrons"):
        parts += _chevrons(p, cw, sill, panel, p["band"])
    return parts


def _window_deco_base(p: dict) -> list[Box]:
    """A base window: a narrower opening between stone jambs, over a low sill and under a
    stone head, so the ground floors read as masonry."""
    cw, h, sill, head, j = p["width"] / 2, p["height"], p["sill"], p["head"], p["jamb"]
    panel, back, glass, bar = (
        p["front"] + p["recess"] / 2,
        p["front"] + p["recess"],
        p["glass"],
        MULLION_DEPTH,
    )
    top, ow = h - head, cw - j
    boxes = [
        ((-cw, panel, 0), (cw, back + glass, sill), "stone"),
        ((-cw, panel, top), (cw, back + glass, h), "stone"),
        ((-cw, panel, sill), (-ow, back + glass, top), "stone"),
        ((ow, panel, sill), (cw, back + glass, top), "stone"),
        ((-ow, back, sill), (ow, back + glass, top), "glass"),
    ]
    for i in range(1, p["mullions"] + 1):
        x = -ow + 2 * ow * i / (p["mullions"] + 1)
        boxes.append(((x - 0.04, back - bar, sill), (x + 0.04, back, top), "metal"))
    return boxes


def _window_channel(p: dict) -> list[Box]:
    """A bay column of a window block at L2: one box, glass up a shaft, stone elsewhere."""
    w = p["width"] / 2
    return [((-w, p["front"], 0), (w, p["depth"], p["height"]), p["material"])]


def _window_channel_banded(p: dict) -> list[Box]:
    """A bay column of a horizontal shaft at L2: a stone band and a glass strip per floor."""
    w, fh, sill = p["width"] / 2, p["floor_height"], p["sill"]
    boxes = []
    for k in range(round(p["height"] / fh)):
        z = k * fh
        boxes.append(((-w, p["front"], z), (w, p["depth"], z + sill), "stone"))
        boxes.append(((-w, p["glass"], z + sill), (w, p["depth"], z + fh), "glass"))
    return boxes


def _merlon_stepped(p: dict) -> list[Box]:
    """A pylon from the roof through the parapet, stepping in `steps` times above it."""
    w, d, base, n, rise = p["width"] / 2, p["depth"], p["base"], p["steps"], p["rise"]
    boxes = [((-w, -p["proud"], 0), (w, d, base + rise), "stone")]
    boxes += [
        (
            (-w * (1 - i / n), -p["proud"], base + i * rise),
            (w * (1 - i / n), d, base + (i + 1) * rise),
            "stone",
        )
        for i in range(1, n)
    ]
    return boxes


def _entrance_deco_main(p: dict) -> list[Box]:
    """Stepped surround, glazed doors, canopy, plinth and a stepped crest above."""
    k, sp, sw = p["frames"], p["frame_step"], p["frame_width"]
    hw0, h, dd = p["width"] / 2, p["height"], p["depth"]
    proj, plinth_top, glass = k * sp, 0.3, 0.05
    boxes = []
    for j in range(k):  # jambs stand on the plinth in front of the envelope, on the floor behind
        outer, inner = hw0 - j * sw, hw0 - (j + 1) * sw
        top, inner_top, front = h - j * sw, h - (j + 1) * sw, -(k - j) * sp
        for x0, x1 in ((-outer, -inner), (inner, outer)):
            boxes += [
                ((x0, front, plinth_top), (x1, 0, top), "stone"),
                ((x0, 0, 0), (x1, dd, top), "stone"),
            ]
        boxes.append(((-inner, front, inner_top), (inner, dd, top), "stone"))
    hwk, topk = hw0 - k * sw, h - k * sw
    door = p["door_height"]
    boxes += [
        ((-hw0 - p["apron"], -(proj + p["plinth"]), 0), (hw0 + p["apron"], 0, plinth_top), "stone"),
        ((-hwk, 0, 0), (hwk, dd - glass, plinth_top), "stone"),
        ((-hwk, dd - glass, plinth_top), (hwk, dd, topk), "glass"),
        (
            (-hwk - 0.4, -(proj + p["canopy"]), door),
            (hwk + 0.4, dd - glass - 0.12, door + 0.35),
            "metal",
        ),
    ]
    for i in range(1, p["mullions"] + 1):
        x = -hwk + 2 * hwk * i / (p["mullions"] + 1)
        boxes.append(
            ((x - 0.06, dd - glass - 0.12, plinth_top), (x + 0.06, dd - glass, topk), "metal")
        )
    for i, share in enumerate((0.5, 0.32, 0.14)):  # each step a third shallower
        z = h + i * p["crest"] / 3
        boxes.append(
            ((-hw0 * share, -proj * (3 - i) / 3, z), (hw0 * share, 0, z + p["crest"] / 3), "stone")
        )
    return boxes


def _ring(p: dict) -> list[Box]:
    """Rings along an outline, each [reach, z0, z1]: positive reach stands outward from
    the envelope (bands, cornices), negative reach runs inward from it (parapets). Each
    edge's strip is trimmed or extended at its end so strips meet without overlapping."""
    boxes = []
    for reach, z0, z1 in p["rings"]:
        r = abs(reach)
        across = (0.0, reach) if reach > 0 else (reach, 0.0)
        for e in outline(p["width"], p["depth"], p.get("notch", 0.0)):
            (ax, ay), (ux, uy), (nx, ny) = e.a, e.direction, e.normal
            grow = r if e.end_convex == (reach > 0) else -r
            pts = [
                (ax + ux * s + nx * q, ay + uy * s + ny * q)
                for s in (0.0, e.length + grow)
                for q in across
            ]
            xs, ys = [pt[0] for pt in pts], [pt[1] for pt in pts]
            boxes.append(((min(xs), min(ys), z0), (max(xs), max(ys), z1), "stone"))
    return boxes


def _crown_stepped(p: dict) -> list[Box]:
    """Ziggurat crown: tiers stepping in on every side, with an optional bronze spire."""
    W, D, th, st, n = p["width"] / 2, p["depth"] / 2, p["tier_height"], p["step"], p["tiers"]
    boxes = [
        (
            (-W + (i + 1) * st, -D + (i + 1) * st, i * th),
            (W - (i + 1) * st, D - (i + 1) * st, (i + 1) * th),
            "stone",
        )
        for i in range(n)
    ]
    if p["spire_height"] > 0:
        sw = p["spire_width"] / 2
        boxes.append(((-sw, -sw, n * th), (sw, sw, n * th + p["spire_height"]), "metal"))
    return boxes


def _bridge_gallery(p: dict) -> list[Box]:
    """Enclosed gallery across a gap: stone deck and roof, glazed sides behind bronze fins,
    and a stepped keel underneath that stops short of the transfer bands at each end."""
    w, span, h, slab, fin = p["width"] / 2, p["span"], p["height"], p["slab"], p["fin"]
    k1, k2 = p["keel"]
    clear = p["band"] + 0.1
    boxes = [
        ((-w, -span, 0), (w, 0, slab), "stone"),
        ((-w, -span, h - slab), (w, 0, h), "stone"),
        ((-w, -span, slab), (-w + 0.12, 0, h - slab), "glass"),
        ((w - 0.12, -span, slab), (w, 0, h - slab), "glass"),
        ((-w / 2, -span + clear, -k1), (w / 2, -clear, 0), "stone"),
        ((-w / 4, -span + clear, -k1 - k2), (w / 4, -clear, -k1), "stone"),
    ]
    fins = max(1, round(span / 3))
    for k in range(fins):
        y = -span * (k + 0.5) / fins
        boxes.append(((-w - fin, y - 0.1, slab), (-w, y + 0.1, h - slab), "metal"))
        boxes.append(((w, y - 0.1, slab), (w + fin, y + 0.1, h - slab), "metal"))
    return boxes


# Treatments (docs/LAYERS.md section 4): each fills a leaf between the piers at its edges.

JOINT, JOINT_DEPTH = 0.06, 0.05  # a field's coursing joints: half height, depth


def _field_stone(p: dict) -> list[Box]:
    """Plain stone coursed every floor by a shallow joint; with `niche` ([width, height,
    bottom, depth]) a niche for a figure or relief, framed by a surround stepping out twice."""
    w, h, f, dd, fh = p["width"] / 2, p["height"], p["front"], p["depth"], p["floor_height"]
    boxes: list[Box] = []
    z = 0.0
    for k in range(1, round(h / fh)):
        boxes.append(((-w, f, z), (w, dd, k * fh - JOINT), "stone"))
        boxes.append(((-w, f + JOINT_DEPTH, k * fh - JOINT), (w, dd, k * fh + JOINT), "stone"))
        z = k * fh + JOINT
    boxes.append(((-w, f, z), (w, dd, h), "stone"))
    if "niche" not in p:
        return boxes
    nw, nh, z0, nd = p["niche"]
    hw = nw / 2
    boxes = _carved(boxes, {"cuts": [[-hw, f - 1.0, z0, hw, f + nd, z0 + nh]]})
    s = NICHE_SURROUND
    margin = min(0.6, z0, h - z0 - nh, w - hw)
    for step in (1, 2):  # the nearer step is the wider
        m, y0 = margin * (3 - step) / 2, f - step * s
        boxes += [
            ((-hw - m, y0, z0 - m), (-hw, y0 + s, z0 + nh + m), "stone"),
            ((hw, y0, z0 - m), (hw + m, y0 + s, z0 + nh + m), "stone"),
            ((-hw, y0, z0 - m), (hw, y0 + s, z0), "stone"),
            ((-hw, y0, z0 + nh), (hw, y0 + s, z0 + nh + m), "stone"),
        ]
    return boxes


def _opening_deco(p: dict) -> list[Box]:
    """One glazed opening: stepped frames receding into the wall, each a sill, two jambs
    and a head; glass at the back; a coarse grid of bronze mullions and transoms in front
    of it; a bronze band on the outer sill."""
    w, h, k, fw = p["width"] / 2, p["height"], p["frames"], p["frame_width"]
    fs, ss, g = p["frame_step"], p["sill_step"], p["glass"]
    boxes: list[Box] = []
    for j in range(k):
        o, i, y = w - j * fw, w - (j + 1) * fw, j * fs
        bottom, top = j * ss, h - j * fw
        boxes += [
            ((-o, y, bottom), (-i, g, top), "stone"),
            ((i, y, bottom), (o, g, top), "stone"),
            ((-i, y, h - (j + 1) * fw), (i, g, top), "stone"),
            ((-i, y, bottom), (i, g, (j + 1) * ss), "stone"),
        ]
    gi, gb, gt, pane = w - k * fw, k * ss, h - k * fw, g - 0.05
    boxes.append(((-gi, pane, gb), (gi, g, gt), "clear"))
    bar = 0.1
    xs = [-gi + 2 * gi * m / (p["mullions"] + 1) for m in range(1, p["mullions"] + 1)]
    boxes += [((x - bar, pane - 0.15, gb), (x + bar, pane, gt), "metal") for x in xs]
    edges = [-gi, *(v for x in xs for v in (x - bar, x + bar)), gi]
    for t in range(1, p["transoms"] + 1):
        z = gb + (gt - gb) * t / (p["transoms"] + 1)
        boxes += [
            ((a, pane - 0.1, z - bar), (b, pane, z + bar), "metal")
            for a, b in zip(edges[::2], edges[1::2], strict=True)
        ]
    boxes.append(((-(w - fw), -p["band"], 0.1), (w - fw, 0.0, ss - 0.1), "metal"))
    return boxes


def _space_hall(p: dict) -> list[Box]:
    """The hall behind an opening: a floor, a slab every few floors, and a lit back wall."""
    w, h, front, depth = p["width"] / 2, p["height"], p["front"], p["depth"]
    wall = depth - 0.3
    boxes: list[Box] = [
        ((-w, wall, 0), (w, depth, h), "light"),
        ((-w, front, 0), (w, wall, 0.3), "stone"),
    ]
    step = p["every"] * p["floor_height"]
    z = step
    while z < h - 1e-6:
        boxes.append(((-w, front, z - 0.4), (w, wall, z), "stone"))
        z += step
    return boxes


def _recess_slab(p: dict) -> list[Box]:
    """A recess's floors: a slab per floor, open to the front, with a balustrade on its edge."""
    w, d, fh, slab = p["width"] / 2, p["depth"], p["floor_height"], p["slab"]
    boxes: list[Box] = []
    for j in range(p["floors"]):
        z = j * fh
        boxes.append(((-w, 0, z), (w, d, z + slab), "stone"))
        boxes.append(((-w, 0, z + slab), (w, p["rail"], z + slab + p["rail_height"]), "stone"))
    return boxes


SPANDREL = 1.0  # spandrel height in a giant order's glazing


def _order_giant(p: dict) -> list[Box]:
    """Giant piers standing `proud` of the wall, each with a narrower face stepping forward
    again, rising through the band; between them deep glazing at the back of the wall, on a
    bay grid of bronze mullions, transoms at every floor and dark spandrels."""
    w, h, dd, fh = p["width"] / 2, p["height"], p["depth"], p["floor_height"]
    gw, back, proud = p["pier_width"] / 2, p["depth"] - p["glass"], p["proud"]
    boxes: list[Box] = []
    for x in p["piers"]:
        boxes.append(((x - gw, -proud / 2, 0), (x + gw, dd, h), "stone"))
        boxes.append(((x - gw / 2, -proud, 0), (x + gw / 2, -proud / 2, h), "stone"))
    walls = [-w, *(v for x in p["piers"] for v in (x - gw, x + gw)), w]
    for x0, x1 in zip(walls[::2], walls[1::2], strict=True):
        boxes.append(((x0, back, 0), (x1, dd, h), "glass"))
        mullions = [m for m in p["mullions"] if x0 < m < x1]
        boxes += [((m - 0.05, back - 0.12, 0), (m + 0.05, back, h), "metal") for m in mullions]
        edges = [x0, *(v for m in mullions for v in (m - 0.05, m + 0.05)), x1]
        for f in range(round(h / fh)):
            for a, b in zip(edges[::2], edges[1::2], strict=True):
                boxes.append(((a, back - 0.04, f * fh), (b, back, f * fh + SPANDREL), "spandrel"))
                if f:
                    boxes.append(((a, back - 0.08, f * fh - 0.06), (b, back, f * fh), "metal"))
    return boxes


# recipe name -> parts(params), in the element's frame (see plan.py)
RECIPES: dict[str, Callable[[dict], list[Part]]] = {
    "mass.box": _mass,
    "mass.notched": _mass,
    "pier.inner": _pier_inner,
    "pier.strip": _pier_strip,
    "pier.fluted": _pier_fluted,
    "pier.banded": _pier_banded,
    "pier.corner": _pier_corner,
    "window.deco_tall": _window_deco_tall,
    "window.deco_band": _window_deco_tall,
    "window.deco_capital": _window_deco_capital,
    "window.deco_base": _window_deco_base,
    "window.channel": _window_channel,
    "window.channel_banded": _window_channel_banded,
    "entrance.deco_main": _entrance_deco_main,
    "crown.stepped": _crown_stepped,
    "bridge.gallery": _bridge_gallery,
    "band.ring": _ring,
    "parapet.ring": _ring,
    "cornice.ring": _ring,
    "merlon.stepped": _merlon_stepped,
    "field.stone": _field_stone,
    "opening.deco": _opening_deco,
    "space.hall": _space_hall,
    "recess.slab": _recess_slab,
    "order.giant": _order_giant,
}


def build_mesh(recipe: str, params: dict, name: str) -> bpy.types.Mesh:
    return mesh_from_parts(name, RECIPES[recipe](params))


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
