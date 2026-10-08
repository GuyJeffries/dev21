"""Review renders for pull requests (Blender + Pillow).

Contact sheet: many seeds at L2, one camera fitted to the box enclosing every building
(spires included), so relative size reads correctly across seeds. Detail sheet: close-ups
at L0 of the entrance, a bridge, the central tower's first setback and its crown for a few
seeds, where windows, joints and ornament are big enough to judge.

Every tile is rendered from the handover package (library + manifest) through the stand-in
assembler, so the sheets also exercise that path. Output is compressed JPEG sized for limited
bandwidth, plus the metrics as JSON and Markdown.
"""

import json
import math
from collections import Counter
from dataclasses import replace
from pathlib import Path

import bpy
from mathutils import Vector
from PIL import Image, ImageDraw, ImageFont

from arcology.assemble import assemble
from arcology.build import build_library
from arcology.facade import TREATMENTS
from arcology.metrics import (
    EXCEPTION_CAP,
    LUXURY_SHARE,
    ORNAMENT_CAP,
    PODIUM_SHARE,
    SLENDERNESS,
    SPIRE_SHARE,
    TAPER,
    failures,
    measure,
)
from arcology.plan import Plan, element_bounds, plan_bounds
from arcology.resolve import resolve
from arcology.rules import CENTRAL
from arcology.spec import Spec, spec_with

SKY = (0.62, 0.70, 0.82)
GROUND = (0.36, 0.38, 0.33)


# Default view: from the south-east, slightly above.
VIEW = (-1.0, 1.0, -0.45)


def _all_bounds(plan: Plan):
    """Bounds of everything in the plan, crowns and spires included."""
    boxes = [element_bounds(e) for e in plan.elements]
    return (
        tuple(min(b[0][i] for b in boxes) for i in range(3)),
        tuple(max(b[1][i] for b in boxes) for i in range(3)),
    )


def shared_camera(plans: list[Plan]) -> dict:
    """One framing for the whole sheet: the box enclosing everything in every plan."""
    bounds = [_all_bounds(p) for p in plans]
    lo = tuple(min(b[0][i] for b in bounds) for i in range(3))
    hi = tuple(max(b[1][i] for b in bounds) for i in range(3))
    return {"lo": lo, "hi": hi, "view": VIEW, "lens": 35, "ground": max(hi[0] - lo[0], hi[2]) * 60}


def detail_cameras(plan: Plan) -> dict[str, dict]:
    """Close-up framings: the main entrance; the central tower's base section seen whole
    from the south (the mid-range view, where bands, panels and treatments read); the
    sister-tower cluster at its transfer floor (else a pavilion bridge, else the tower's
    base corner); the central tower's first setback (capital, cornice, merlons), if it has
    one; its crown."""
    bay, fh = plan.bay_width, plan.floor_height
    ground = (plan_bounds(plan)[1][0] - plan_bounds(plan)[0][0]) * 8
    entrance = next(e for e in plan.elements if e.kind == "entrance")
    (x0, y0, _), (x1, y1, z1) = element_bounds(entrance)
    views = {
        "entrance": {
            "lo": (x0 - 2 * bay, y0, 0.0),
            "hi": (x1 + 2 * bay, y1, z1 + 2 * fh),
            "view": (-0.35, 1.0, -0.12),
        }
    }
    (fx0, fy0, fz0), (fx1, _, fz1) = element_bounds(plan.element(f"{CENTRAL}/section.0"))
    views["face"] = {
        "lo": (fx0 - bay, fy0 - bay, fz0),
        "hi": (fx1 + bay, fy0 + bay, fz1 + fh),
        "view": (-0.3, 1.0, -0.1),
    }
    bridges = [e for e in plan.elements if e.kind == "bridge"]
    inner = [b for b in bridges if b.tags["from"].startswith("arcology/tower.central")]
    if inner:
        # The cluster round the transfer floor: central base, sister towers, bridges, bands.
        datum = inner[0].translation[2]
        boxes = [element_bounds(b) for b in inner]
        boxes += [element_bounds(plan.element(b.tags["to"])) for b in inner]
        lo = (min(b[0][0] for b in boxes), min(b[0][1] for b in boxes), datum - 5 * fh)
        hi = (max(b[1][0] for b in boxes), max(b[1][1] for b in boxes), datum + 5 * fh)
        views["cluster"] = {"lo": lo, "hi": hi, "view": (-0.6, 1.0, -0.55)}
    elif bridges:
        (bx0, by0, bz0), (bx1, by1, bz1) = element_bounds(bridges[0])
        lo = (bx0 - 4 * bay, by0 - 4 * bay, bz0 - 3 * fh)
        hi = (bx1 + 4 * bay, by1 + 4 * bay, bz1 + 3 * fh)
        views["bridge"] = {"lo": lo, "hi": hi, "view": (-0.6, 1.0, -0.4)}
    else:
        base = min(
            (e for e in plan.elements if e.kind == "mass" and e.tags.get("role") == "tower"),
            key=lambda e: e.floor,
        )
        (tx0, ty0, tz0), (tx1, ty1, _) = element_bounds(base)
        views["tower corner"] = {
            "lo": (tx1 - 4 * bay, ty0, tz0),
            "hi": (tx1, ty0 + 4 * bay, tz0 + 8 * fh),
            "view": (-1.0, 1.0, -0.25),
        }
    sections = [e for e in plan.elements if e.kind == "mass" and e.tags.get("tower") == CENTRAL]
    if len(sections) > 1:
        # The south-east corner where the base section steps back to the next.
        (_, sy0, _), (sx1, _, sz1) = element_bounds(sections[0])
        views["setback"] = {
            "lo": (sx1 - 6 * bay, sy0, sz1 - 5 * fh),
            "hi": (sx1, sy0 + 6 * bay, sz1 + 3 * fh),
            "view": (-1.0, 1.0, -0.3),
        }
    crown = next(e for e in plan.elements if e.kind == "crown" and e.tags["tower"] == CENTRAL)
    (cx0, cy0, cz0), (cx1, cy1, cz1) = element_bounds(crown)
    views["crown"] = {
        "lo": (cx0, cy0, cz0 - 4 * fh),
        "hi": (cx1, cy1, cz1),
        "view": (-1.0, 1.0, -0.15),
    }
    return {name: {**v, "lens": 50, "ground": ground} for name, v in views.items()}


def _stage(camera: dict, size: tuple[int, int], samples: int) -> None:
    lo, hi = Vector(camera["lo"]), Vector(camera["hi"])
    extent = max(hi - lo)
    scene = bpy.context.scene
    scene.render.resolution_x, scene.render.resolution_y = size  # before fitting the camera
    scene.render.resolution_percentage = 100

    # Ground far beyond the view, so its edge never shows as a false horizon.
    bpy.ops.mesh.primitive_plane_add(size=camera["ground"])
    ground = bpy.data.materials.new("ground")
    ground.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (*GROUND, 1)
    bpy.context.object.data.materials.append(ground)

    # Sun from the front-left: south faces lit, east faces in shade, so steps read clearly.
    bpy.ops.object.light_add(type="SUN")
    sun = bpy.context.object
    sun.data.energy = 2.6
    sun.rotation_euler = (math.radians(50), 0, math.radians(-40))

    world = bpy.data.worlds.new("sky")
    background = world.node_tree.nodes["Background"]
    background.inputs["Color"].default_value = (*SKY, 1)
    background.inputs["Strength"].default_value = 0.55

    # Look along the view direction, then let Blender fit the box exactly.
    bpy.ops.object.camera_add()
    cam = bpy.context.object
    cam.data.lens = camera["lens"]
    view = Vector(camera["view"]).normalized()
    cam.rotation_euler = view.to_track_quat("-Z", "Y").to_euler()
    corners = [(x, y, z) for x in (lo.x, hi.x) for y in (lo.y, hi.y) for z in (lo.z, hi.z)]
    fitted, _ = cam.camera_fit_coords(
        bpy.context.evaluated_depsgraph_get(), [c for corner in corners for c in corner]
    )
    cam.location = fitted - view * extent * 0.06  # a little margin
    cam.data.clip_start = 1.0
    cam.data.clip_end = camera["ground"] * 2  # the default 100 m would cut the building off

    scene.world = world
    scene.camera = cam
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = samples


def render_tile(manifest_path: Path, image_path: Path, camera: dict, size, samples: int) -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    assemble(manifest_path)
    _stage(camera, size, samples)
    bpy.context.scene.render.filepath = str(Path(image_path).resolve())
    bpy.ops.render.render(write_still=True)


def _label(result: dict) -> tuple[str, str]:
    towers = f"  +{result['towers']} towers" if result["towers"] else ""
    height = f"{result['height_m']:.0f} m (tip {result['tip_m']:.0f})"
    top = f"seed {result['seed']}  {height}  {result['floors']} fl{towers}"
    failed = failures(result)
    bottom = (
        "checks: FAIL " + ", ".join(failed)
        if failed
        else f"checks ok  {result['windows']:,} windows"
    )
    return top, bottom


def _montage(
    labels: list[tuple[str, str, bool]],
    tiles: list[Path | None],
    out: Path,
    size,
    cols: int,
    *,
    compact: bool = False,
) -> None:
    """Tiles in a grid, each with two caption lines (one if `compact`); the second, or the
    only one, is red when `bad`. A None tile leaves its cell blank."""
    tw, th = size
    strip = 17 if compact else 34
    rows = math.ceil(len(tiles) / cols)
    sheet = Image.new("RGB", (cols * tw, rows * (th + strip)), "white")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default(size=11 if compact else 13)
    for i, ((top, bottom, bad), tile) in enumerate(zip(labels, tiles, strict=True)):
        if tile is None:
            continue
        x, y = (i % cols) * tw, (i // cols) * (th + strip)
        sheet.paste(Image.open(tile).convert("RGB"), (x, y))
        colour = "darkred" if bad else "dimgray"
        if compact:
            draw.text((x + 4, y + th + 2), f"{top} {bottom}".strip(), fill=colour, font=font)
            continue
        draw.text((x + 6, y + th + 3), top, fill="black", font=font)
        draw.text((x + 6, y + th + 18), bottom, fill=colour, font=font)
    sheet.save(out, "JPEG", quality=82, optimize=True, progressive=True)


def metrics_markdown(results: list[dict], lod: str) -> str:
    lines = [
        f"### Contact sheet: {len(results)} seeds, {lod}",
        "",
        "| seed | height / tip (m) | floors | podium | tower | towers | dominance | footprint (m) "
        "| tower base (m) | windows | ornament c / s / p / pod | luxury | L0 meshes / copies "
        "| checks |",
        "|---:|---:|---:|---:|---:|---:|---:|---|---|---:|---|---:|---:|---|",
    ]
    for r in results:
        failed = failures(r)
        l0 = r["lod"]["L0"]
        dominance = f"{r['dominance']:.2f}" if r["dominance"] else "–"
        orn = " / ".join(
            f"{r['ornament'][s]:.2f}" if s in r["ornament"] else "–"
            for s in ("central", "sister", "pavilion", "podium")
        )
        lines.append(
            f"| {r['seed']} | {r['height_m']:.0f} / {r['tip_m']:.0f} | {r['floors']} "
            f"| {r['podium_floors']} | {r['tower_floors']} | {r['towers']} | {dominance} "
            f"| {r['footprint_m'][0]:g} × {r['footprint_m'][1]:g} "
            f"| {r['tower_base_m'][0]:g} × {r['tower_base_m'][1]:g} "
            f"| {r['windows']:,} | {orn} | {r['layers']['luxury']['building']:.0%} "
            f"| {l0['unique']} / {l0['instances']:,} "
            f"| {'FAIL: ' + ', '.join(failed) if failed else 'ok'} |"
        )
    return "\n".join(lines) + "\n"


def contact_sheet(
    spec: Spec,
    seeds,
    out_dir: str | Path,
    *,
    tile: tuple[int, int] = (400, 300),
    cols: int = 4,
    samples: int = 16,
    lod: str = "L2",
) -> list[dict]:
    """Resolve, build, assemble and render each seed; write the sheet and metrics to out_dir."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    plans = [resolve(replace(spec, seed=s)) for s in seeds]
    camera = shared_camera(plans)
    results, tiles = [], []
    for plan in plans:
        seed_dir = out_dir / f"seed-{plan.seed}"
        seed_dir.mkdir(exist_ok=True)
        plan.save(seed_dir / "plan.json")
        build_library(plan, seed_dir, lod)
        render_tile(seed_dir / "manifest.json", seed_dir / "tile.png", camera, tile, samples)
        results.append({"seed": plan.seed, **measure(plan)})
        tiles.append(seed_dir / "tile.png")
    labels = [(*_label(r), bool(failures(r))) for r in results]
    _montage(labels, tiles, out_dir / "contact_sheet.jpg", tile, min(cols, len(tiles)))
    (out_dir / "metrics.json").write_text(json.dumps(results, indent=2) + "\n")
    (out_dir / "metrics.md").write_text(metrics_markdown(results, lod))
    return results


def detail_sheet(
    spec: Spec,
    seeds,
    out_dir: str | Path,
    *,
    tile: tuple[int, int] = (400, 300),
    samples: int = 24,
) -> None:
    """Close-ups at L0 (entrance, cluster or bridge, setback, crown): one row per seed."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    labels, tiles, columns = [], [], 0
    for seed in seeds:
        plan = resolve(replace(spec, seed=seed))
        seed_dir = out_dir / f"seed-{seed}"
        build_library(plan, seed_dir, "L0")
        entrance = next(e for e in plan.elements if e.kind == "entrance")
        bays, floors = entrance.tags["bays"], entrance.tags["floors"]
        bridges = [e for e in plan.elements if e.kind == "bridge"]
        crown = next(e for e in plan.elements if e.kind == "crown" and e.tags["tower"] == CENTRAL)
        base = f"{CENTRAL}/section.0"
        capital = {
            f
            for r in plan.regions
            if r.treatment and r.mass == base and r.tags["course"] == "capital"
            for f in range(*r.floors)
        }
        merlons = sum(
            e.count for e in plan.elements if e.kind == "merlon" and e.tags["mass"] == base
        )
        south = Counter(
            r.treatment
            for r in plan.regions
            if r.mass == base and r.facade == "south" and r.treatment in TREATMENTS
        )
        captions = {
            "entrance": f"{bays[1] - bays[0]} bays x {floors[1] - floors[0]} floors",
            "face": ", ".join(f"{n} {t}" for t, n in sorted(south.items())) or "no exceptions",
            "cluster": f"{len(bridges)} bridges; sister towers meet at floor {bridges[0].floor}"
            if bridges
            else "",
            "bridge": f"{len(bridges)} pavilion bridges",
            "tower corner": "south-east corner of the tower's base",
            "setback": f"capital {len(capital)} floors, cornice, {merlons} merlons",
            "crown": f"{crown.params.get('tiers', 0)} tiers, "
            f"spire {crown.params.get('spire_height', 0):.0f} m",
        }
        cameras = detail_cameras(plan)
        columns = max(columns, len(cameras))
        for name, camera in cameras.items():
            path = seed_dir / f"{name.replace(' ', '_')}.png"
            render_tile(seed_dir / "manifest.json", path, camera, tile, samples)
            labels.append((f"seed {seed}  {name}", captions[name], False))
            tiles.append(path)
    _montage(labels, tiles, out_dir / "detail_sheet.jpg", tile, columns)


# Sweeps: one parameter varied along a row, everything else fixed (docs/PLAN.md section 20).
# A golden seed whose broad sister towers show the hierarchy and symmetry settings plainly
# (on seed 11 narrow sisters, capped by their proportions, hid both).
SWEEP_SEED = 37
STYLE_SWEEPS = (
    ("style.setback_strength", ["high", "medium", "low"]),
    ("style.hierarchy", ["strong", "moderate", "weak"]),
    ("style.dominant_axis", ["vertical", "horizontal"]),
    ("style.ornament_density", [0.0, 0.35, 0.65, 1.0]),
    ("style.symmetry", ["bilateral", "none"]),
    ("style.repetition", ["regular", "varied"]),
    ("style.termination", ["spire", "stepped", "flat"]),
    ("style.contrast", [0.0, 0.5, 1.0]),
)


def _short(value) -> str:
    return f"{value:g}" if isinstance(value, float) else str(value)


def sweep_markdown(rows: list[dict], seed: int, lod: str) -> str:
    lines = [
        f"### Sweep sheet: seed {seed}, {lod}",
        "",
        "| parameter | value | height (m) | towers | dominance | slenderness | taper "
        "| ornament c / s / pod | windows | checks |",
        "|---|---|---:|---:|---:|---:|---:|---|---:|---|",
    ]
    for r in rows:
        failed = failures(r)
        orn = " / ".join(
            f"{r['ornament'][s]:.2f}" if s in r["ornament"] else "–"
            for s in ("central", "sister", "podium")
        )
        lines.append(
            f"| {r['parameter']} | {_short(r['value'])} | {r['height_m']:.0f} | {r['towers']} "
            f"| {r['dominance'] or '–'} | {r['style']['slenderness']} | {r['style']['taper']} "
            f"| {orn} | {r['windows']:,} | {'FAIL: ' + ', '.join(failed) if failed else 'ok'} |"
        )
    return "\n".join(lines) + "\n"


def sweep_sheet(
    spec: Spec,
    sweeps,
    out_dir: str | Path,
    *,
    seed: int = SWEEP_SEED,
    tile: tuple[int, int] = (320, 240),
    samples: int = 12,
    lod: str = "L2",
) -> list[dict]:
    """One row per (parameter, values): the same seed with the parameter set to each value in
    turn, all framed by one camera so sizes compare. Writes sweep_sheet.jpg and metrics."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cols = max(len(values) for _, values in sweeps)
    cells = []  # (parameter, value, plan) or None for a blank cell
    for parameter, values in sweeps:
        for value in values:
            plan = resolve(replace(spec_with(spec, parameter, value), seed=seed))
            cells.append((parameter, value, plan))
        cells += [None] * (cols - len(values))
    camera = shared_camera([c[2] for c in cells if c])
    results, labels, tiles = [], [], []
    for i, cell in enumerate(cells):
        if cell is None:
            labels.append(("", "", False))
            tiles.append(None)
            continue
        parameter, value, plan = cell
        cell_dir = out_dir / f"cell-{i:02d}"
        cell_dir.mkdir(exist_ok=True)
        build_library(plan, cell_dir, lod)
        render_tile(cell_dir / "manifest.json", cell_dir / "tile.png", camera, tile, samples)
        result = {"parameter": parameter, "value": value, "seed": seed, **measure(plan)}
        results.append(result)
        failed = failures(result)
        top = f"{parameter.split('.')[-1]} = {_short(value)}"
        bottom = "FAIL " + ", ".join(failed) if failed else f"{result['height_m']:.0f} m"
        labels.append((top, bottom, bool(failed)))
        tiles.append(cell_dir / "tile.png")
    _montage(labels, tiles, out_dir / "sweep_sheet.jpg", tile, cols)
    (out_dir / "sweep.json").write_text(json.dumps(results, indent=2) + "\n")
    (out_dir / "sweep.md").write_text(sweep_markdown(results, seed, lod))
    return results


# What-if: the treatments one at a time, then together (docs/LAYERS.md section 9), on the
# central tower's base section seen whole from the south at L0, built alone so it's quick.
WHATIF_SEEDS = (11, 37)
WHATIF = (
    ("none", {"style.contrast": 0.0}),
    *((t, {"facade.treatments": [t], "style.contrast": 1.0}) for t in TREATMENTS),
    ("all, contrast 0.5", {"style.contrast": 0.5}),
    ("all, contrast 1", {"style.contrast": 1.0}),
    # Giant orders come into their own across a horizontal face's full-width bands.
    ("horizontal, contrast 1", {"style.dominant_axis": "horizontal", "style.contrast": 1.0}),
)


def _section(plan: Plan, mass_id: str) -> Plan:
    """The plan cut down to one mass and everything dressing it."""
    keep = [e for e in plan.elements if e.id == mass_id or e.tags.get("mass") == mass_id]
    return replace(plan, elements=tuple(keep))


def whatif_markdown(rows: list[dict]) -> str:
    lines = [
        "### What-if sheet: the central tower's base section, L0",
        "",
        "| seed | variant | luxury | exceptions | field | opening | recess | giant | rich "
        "| checks |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for r in rows:
        area, failed = r["layers"]["area"], failures(r)
        shares = " | ".join(f"{area.get(t, 0):.1%}" for t in TREATMENTS)
        lines.append(
            f"| {r['seed']} | {r['variant']} | {r['layers']['luxury']['building']:.0%} "
            f"| {r['layers']['exceptions']['building']:.1%} | {shares} "
            f"| {'FAIL: ' + ', '.join(failed) if failed else 'ok'} |"
        )
    return "\n".join(lines) + "\n"


def whatif_sheet(
    spec: Spec,
    seeds,
    out_dir: str | Path,
    *,
    tile: tuple[int, int] = (300, 300),
    samples: int = 16,
    variants=WHATIF,
) -> list[dict]:
    """One row per seed, one column per variant (name, {path: value}; default WHATIF): the
    central tower's base section at L0 from the mid-range camera. Shares and checks are the
    whole building's."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rows, labels, tiles = [], [], []
    for seed in seeds:
        for i, (name, changes) in enumerate(variants):
            changed = spec
            for path, value in changes.items():
                changed = spec_with(changed, path, value)
            plan = resolve(replace(changed, seed=seed))
            result = {"seed": seed, "variant": name, **measure(plan)}
            rows.append(result)
            cell = out_dir / f"seed-{seed}" / f"variant-{i}"
            build_library(_section(plan, f"{CENTRAL}/section.0"), cell, "L0")
            camera = detail_cameras(plan)["face"]
            render_tile(cell / "manifest.json", cell / "tile.png", camera, tile, samples)
            failed = failures(result)
            bottom = (
                "FAIL " + ", ".join(failed)
                if failed
                else (f"exceptions {result['layers']['exceptions']['building']:.0%}")
            )
            labels.append((f"{seed}  {name}", bottom, bool(failed)))
            tiles.append(cell / "tile.png")
    _montage(labels, tiles, out_dir / "whatif_sheet.jpg", tile, len(variants), compact=True)
    (out_dir / "whatif.md").write_text(whatif_markdown(rows))
    return rows


# Batch: many seeds as silhouettes, to judge whether the style holds (Phase 4's done-when).
BATCH_RANGES = (
    ("height (m)", lambda r: r["height_m"], None),
    ("towers", lambda r: r["towers"], None),
    ("dominance", lambda r: r["dominance"], "≥ the hierarchy's target"),
    ("slenderness", lambda r: r["style"]["slenderness"], f"{SLENDERNESS[0]:g}–{SLENDERNESS[1]:g}"),
    (
        "secondary slenderness",
        lambda r: r["style"]["secondary_slenderness"],
        "≤ the central tower's",
    ),
    ("taper", lambda r: r["style"]["taper"], f"{TAPER[0]:g}–{TAPER[1]:g}"),
    (
        "podium share",
        lambda r: r["style"]["podium_share"],
        f"{PODIUM_SHARE[0]:g}–{PODIUM_SHARE[1]:g}",
    ),
    ("spire share", lambda r: r["style"]["spire_share"], f"≤ {SPIRE_SHARE:g}"),
    ("ornament, central", lambda r: r["ornament"].get("central"), f"≤ {ORNAMENT_CAP:g}"),
    (
        "luxury share",
        lambda r: r["layers"]["luxury"]["building"],
        f"{LUXURY_SHARE[0]:g}–{LUXURY_SHARE[1]:g}",
    ),
    ("luxury, central", lambda r: r["layers"]["luxury"].get("central"), "≥ the others'"),
    ("sky lobbies (share)", lambda r: r["layers"]["courses"].get("lobby", 0), None),
    (
        "exceptions (share)",
        lambda r: r["layers"]["exceptions"]["building"],
        f"≤ {EXCEPTION_CAP:g}",
    ),
    ("exceptions, central", lambda r: r["layers"]["exceptions"].get("central"), None),
)


def batch_markdown(results: list[dict], lod: str) -> str:
    failing: dict[str, list[int]] = {}
    for r in results:
        for name in failures(r):
            failing.setdefault(name, []).append(r["seed"])
    lines = [f"### Batch: {len(results)} seeds, {lod}", ""]
    if failing:
        lines += [f"- **{name}** fails on seeds {seeds}" for name, seeds in sorted(failing.items())]
    else:
        lines.append("Every seed passes every check, the style envelope included.")
    lines += ["", "| measure | min | median | max | envelope |", "|---|---:|---:|---:|---|"]
    for name, get, envelope in BATCH_RANGES:
        values = sorted(v for v in map(get, results) if v is not None)
        if values:
            mid = values[len(values) // 2]
            lines.append(
                f"| {name} | {values[0]:g} | {mid:g} | {values[-1]:g} | {envelope or ''} |"
            )
    return "\n".join(lines) + "\n"


def batch_sheet(
    spec: Spec,
    seeds,
    out_dir: str | Path,
    *,
    tile: tuple[int, int] = (160, 120),
    cols: int = 10,
    samples: int = 8,
    lod: str = "L3",
) -> list[dict]:
    """Many seeds, small and at L3 by default (masses and crowns: the silhouette), under one
    camera, with compact captions and the style envelope's ranges across the batch."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    plans = [resolve(replace(spec, seed=s)) for s in seeds]
    camera = shared_camera(plans)
    results, labels, tiles = [], [], []
    for plan in plans:
        seed_dir = out_dir / f"seed-{plan.seed}"
        build_library(plan, seed_dir, lod)
        render_tile(seed_dir / "manifest.json", seed_dir / "tile.png", camera, tile, samples)
        result = {"seed": plan.seed, **measure(plan)}
        results.append(result)
        failed = failures(result)
        labels.append((str(plan.seed), "FAIL " + ", ".join(failed) if failed else "", bool(failed)))
        tiles.append(seed_dir / "tile.png")
    _montage(labels, tiles, out_dir / "batch_sheet.jpg", tile, min(cols, len(tiles)), compact=True)
    (out_dir / "batch.json").write_text(json.dumps(results, indent=2) + "\n")
    (out_dir / "batch.md").write_text(batch_markdown(results, lod))
    return results
