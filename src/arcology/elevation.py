"""Elevation sheets: flat south elevations drawn straight from the plan with Pillow, no
Blender (docs/LAYERS.md section 9).

Each facade's layer tree is drawn on its face: leaves coloured by treatment (cells by role),
outlined by layer (face boundaries heaviest, then panels, then bands). Masses, crowns and
bridges are drawn as flat silhouettes behind, far to near, so the elevation reads as the
building seen square from the south. It shows the contrast structure at a glance: where
the facade is one uniform texture and where something else happens.
"""

from dataclasses import replace
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from arcology.metrics import layers
from arcology.plan import Plan, Region, element_bounds
from arcology.resolve import resolve
from arcology.rules import outline
from arcology.spec import Spec

# Leaf fills: cells by role, strong where the leaf is luxury and pale where functional, then
# each other treatment. New roles and treatments add a colour here.
FILLS = {
    "luxury.shaft": (78, 102, 140),
    "functional.shaft": (205, 213, 224),
    "luxury.lobby": (40, 128, 100),
    "functional.lobby": (196, 226, 212),
    "luxury.base": (150, 105, 55),
    "functional.base": (232, 216, 190),
    "luxury.capital": (190, 150, 30),
    "functional.capital": (240, 230, 190),
    "portal": (180, 40, 40),
}
UNKNOWN = (255, 0, 255)  # a treatment without a colour shows up loudly
MASS, CROWN, SPIRE, BRIDGE = (227, 222, 211), (214, 207, 192), (176, 141, 87), (120, 120, 128)
OUTLINE = {"face": ((40, 40, 40), 2), "panel": ((70, 70, 70), 1), "band": ((150, 150, 150), 1)}
GROUND = (110, 110, 100)


def leaf_kind(leaf: Region) -> str:
    """The FILLS key a leaf is drawn with."""
    if leaf.treatment == "cells":
        return f"{leaf.tags.get('grade', 'functional')}.{leaf.tags['role']}"
    return leaf.treatment


def _fill(leaf: Region) -> tuple[int, int, int]:
    return FILLS.get(leaf_kind(leaf), UNKNOWN)


def _south_faces(m):
    """(face id, x of bay 0, depth y) for each south-facing facade of mass `m`, far first."""
    mx, my, _ = m.translation
    p = m.params
    faces = [
        (f"{m.id}/facade.{edge.name}", mx + edge.a[0], my + edge.a[1])
        for edge in outline(p["width"], p["depth"], p.get("notch", 0.0))
        if edge.side == "south"
    ]
    return sorted(faces, key=lambda f: -f[2])


def _shapes(plan: Plan):
    """Everything drawn, as (depth, kind, payload), far to near once sorted. A mass is drawn
    with its own faces, so recessed faces at its notches aren't painted over."""
    shapes = []
    for e in plan.elements:
        lo, hi = element_bounds(e)
        if e.kind == "mass":
            shapes.append((lo[1], "mass", ((lo[0], lo[2], hi[0], hi[2]), _south_faces(e))))
        elif e.kind == "bridge":
            shapes.append((lo[1], "bridge", (lo[0], lo[2], hi[0], hi[2])))
        elif e.kind == "crown":
            shapes.append((lo[1], "crown", e))
    return sorted(shapes, key=lambda s: -s[0])


def elevation(plan: Plan, lo: tuple[float, float], hi: tuple[float, float], size) -> Image.Image:
    """The plan's south elevation, framed to the world rectangle lo..hi (x, z) in `size`."""
    w, h = size
    scale = min(w / (hi[0] - lo[0]), h / (hi[1] - lo[1]))
    ox = (w - (hi[0] - lo[0]) * scale) / 2

    def px(x: float, z: float) -> tuple[float, float]:
        return ox + (x - lo[0]) * scale, h - (z - lo[1]) * scale

    def rect(x0, z0, x1, z1, fill=None, line=None, width=1):
        (a, b), (c, d) = px(x0, z1), px(x1, z0)
        draw.rectangle((a, b, c, d), fill=fill, outline=line, width=width)

    image = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(image)
    by_id = {r.id: r for r in plan.regions}
    children: dict[str, list[Region]] = {}
    for r in plan.regions:
        if r.parent:
            children.setdefault(r.parent, []).append(r)
    bay, fh = plan.bay_width, plan.floor_height

    def region_rect(r: Region, x0: float):
        return x0 + r.bays[0] * bay, r.floors[0] * fh, x0 + r.bays[1] * bay, r.floors[1] * fh

    def face(face_id: str, x0: float) -> None:
        stack, ordered = [by_id[face_id]], []
        while stack:  # the face's tree, parents first
            node = stack.pop()
            ordered.append(node)
            stack += children.get(node.id, [])
        for r in ordered:
            if r.treatment:
                rect(*region_rect(r, x0), fill=_fill(r))
        for layer in ("band", "panel", "face"):  # outlines, finest first
            colour, width = OUTLINE[layer]
            for r in ordered:
                if r.layer == layer:
                    rect(*region_rect(r, x0), line=colour, width=width)

    for _, kind, payload in _shapes(plan):
        if kind == "mass":
            silhouette, faces = payload
            rect(*silhouette, fill=MASS)
            for face_id, x0, _ in faces:
                face(face_id, x0)
        elif kind == "bridge":
            rect(*payload, fill=BRIDGE)
        else:
            _crown(payload, rect)
    gx, gz = px(lo[0], 0.0)
    draw.line((0, gz, w, gz), fill=GROUND, width=1)
    return image


def _crown(e, rect) -> None:
    p = e.params
    x, _, z = e.translation
    if "rings" in p:  # a flat termination: a parapet ring
        lo, hi = e.extent
        rect(x + lo[0], z + lo[2], x + hi[0], z + hi[2], fill=CROWN)
        return
    for i in range(p["tiers"]):
        half = p["width"] / 2 - (i + 1) * p["step"]
        rect(
            x - half, z + i * p["tier_height"], x + half, z + (i + 1) * p["tier_height"], fill=CROWN
        )
    if p["spire_height"] > 0:
        top = z + p["tiers"] * p["tier_height"]
        sw = p["spire_width"] / 2
        rect(x - sw, top, x + sw, top + p["spire_height"], fill=SPIRE)


def _frame(plans: list[Plan]):
    """One world rectangle (x, z) holding every plan's elevation, so scales compare."""
    boxes = [element_bounds(e) for p in plans for e in p.elements]
    lo = (min(b[0][0] for b in boxes), 0.0)
    hi = (max(b[1][0] for b in boxes), max(b[1][2] for b in boxes))
    pad = 0.03 * (hi[0] - lo[0])
    return (lo[0] - pad, lo[1]), (hi[0] + pad, hi[1] + pad)


def _caption(plan: Plan) -> str:
    stats = layers(plan)
    parts = [
        f"{k.removeprefix('cells.')} {v:.0%}"
        for k, v in stats["area"].items()
        if v >= 0.005 and k != "portal"
    ]
    return f"seed {plan.seed}   luxury {stats['luxury']['building']:.0%}   " + "  ".join(parts)


def _legend(width: int, font) -> Image.Image:
    """Each role as a pair of swatches, luxury then functional, then the other treatments."""
    strip = Image.new("RGB", (width, 26), "white")
    draw = ImageDraw.Draw(strip)
    x = 8
    roles = dict.fromkeys(k.split(".", 1)[1] for k in FILLS if "." in k)
    swatches = [(r, [FILLS[f"luxury.{r}"], FILLS[f"functional.{r}"]]) for r in roles]
    swatches += [(k, [c]) for k, c in FILLS.items() if "." not in k]
    for name, colours in swatches:
        for colour in colours:
            draw.rectangle((x, 7, x + 14, 19), fill=colour, outline=(60, 60, 60))
            x += 15
        draw.text((x + 4, 6), name, fill="black", font=font)
        x += 18 + int(draw.textlength(name, font=font))
    note = "strong: luxury, pale: functional; outlines: face (heavy), panel, band (light)"
    draw.text((x + 10, 6), note, fill="dimgray", font=font)
    return strip


def elevation_sheet(
    spec: Spec,
    seeds,
    out_dir: str | Path,
    *,
    tile: tuple[int, int] = (480, 420),
    cols: int = 4,
) -> list[Plan]:
    """South elevations of each seed under one scale, with each leaf treatment's share of the
    facade area as the caption. Writes elevation_sheet.jpg."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    plans = [resolve(replace(spec, seed=s)) for s in seeds]
    lo, hi = _frame(plans)
    font = ImageFont.load_default(size=13)
    strip, legend = 20, _legend(cols * tile[0], font)
    rows = -(-len(plans) // cols)
    sheet = Image.new("RGB", (cols * tile[0], legend.height + rows * (tile[1] + strip)), "white")
    sheet.paste(legend, (0, 0))
    draw = ImageDraw.Draw(sheet)
    for i, plan in enumerate(plans):
        x, y = (i % cols) * tile[0], legend.height + (i // cols) * (tile[1] + strip)
        sheet.paste(elevation(plan, lo, hi, tile), (x, y))
        draw.text((x + 6, y + tile[1] + 3), _caption(plan), fill="black", font=font)
    sheet.save(out_dir / "elevation_sheet.jpg", "JPEG", quality=85, optimize=True)
    return plans
