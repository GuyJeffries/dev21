"""Review renders for pull requests (Blender + Pillow).

Contact sheet: many seeds at L2, one camera fitted to the box enclosing every building, so
relative size reads correctly across seeds. Detail sheet: close-ups at L0 of the entrance
and the tower's base corner for a few seeds, where windows are big enough to judge.

Every tile is rendered from the handover package (library + manifest) through the stand-in
assembler, so the sheets also exercise that path. Output is compressed JPEG sized for limited
bandwidth, plus the metrics as JSON and Markdown.
"""

import json
import math
from dataclasses import replace
from pathlib import Path

import bpy
from mathutils import Vector
from PIL import Image, ImageDraw, ImageFont

from arcology.assemble import assemble
from arcology.build import build_library
from arcology.metrics import failures, measure
from arcology.plan import Plan, element_bounds, plan_bounds
from arcology.resolve import resolve
from arcology.spec import Spec

# Fixed seeds rendered on every pull request, so before/after sheets are comparable.
GOLDEN_SEEDS = (11, 23, 37, 41, 53, 67, 71, 89, 97, 101, 113, 127)

SKY = (0.62, 0.70, 0.82)
GROUND = (0.36, 0.38, 0.33)


# Default view: from the south-east, slightly above.
VIEW = (-1.0, 1.0, -0.45)


def shared_camera(plans: list[Plan]) -> dict:
    """One framing for the whole sheet: the box enclosing every plan's bounds."""
    bounds = [plan_bounds(p) for p in plans]
    lo = tuple(min(b[0][i] for b in bounds) for i in range(3))
    hi = tuple(max(b[1][i] for b in bounds) for i in range(3))
    return {"lo": lo, "hi": hi, "view": VIEW, "lens": 35, "ground": max(hi[0] - lo[0], hi[2]) * 60}


def detail_cameras(plan: Plan) -> dict[str, dict]:
    """Close-up framings: the main entrance, and the south-east corner of the tower's base."""
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
    top = f"seed {result['seed']}  {result['height_m']:.0f} m  {result['floors']} floors"
    failed = failures(result)
    bottom = (
        "checks: FAIL " + ", ".join(failed)
        if failed
        else f"checks ok  {result['windows']:,} windows"
    )
    return top, bottom


def _montage(
    labels: list[tuple[str, str, bool]], tiles: list[Path], out: Path, size, cols: int
) -> None:
    """Tiles in a grid, each with two caption lines; the second is red when `bad`."""
    tw, th = size
    strip = 34
    rows = math.ceil(len(tiles) / cols)
    sheet = Image.new("RGB", (cols * tw, rows * (th + strip)), "white")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default(size=13)
    for i, ((top, bottom, bad), tile) in enumerate(zip(labels, tiles, strict=True)):
        x, y = (i % cols) * tw, (i // cols) * (th + strip)
        sheet.paste(Image.open(tile).convert("RGB"), (x, y))
        draw.text((x + 6, y + th + 3), top, fill="black", font=font)
        draw.text((x + 6, y + th + 18), bottom, fill="darkred" if bad else "dimgray", font=font)
    sheet.save(out, "JPEG", quality=82, optimize=True, progressive=True)


def metrics_markdown(results: list[dict], lod: str) -> str:
    lines = [
        f"### Contact sheet: {len(results)} seeds, {lod}",
        "",
        "| seed | height (m) | floors | podium | tower | footprint (m) | tower base (m) "
        "| slenderness | windows | L0 meshes / copies | checks |",
        "|---:|---:|---:|---:|---:|---|---|---:|---:|---:|---|",
    ]
    for r in results:
        failed = failures(r)
        l0 = r["lod"]["L0"]
        lines.append(
            f"| {r['seed']} | {r['height_m']:.0f} | {r['floors']} | {r['podium_floors']} "
            f"| {r['tower_floors']} | {r['footprint_m'][0]:g} × {r['footprint_m'][1]:g} "
            f"| {r['tower_base_m'][0]:g} × {r['tower_base_m'][1]:g} | {r['slenderness']} "
            f"| {r['windows']:,} | {l0['unique']} / {l0['instances']:,} "
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
    tile: tuple[int, int] = (480, 320),
    samples: int = 24,
) -> None:
    """Close-ups at L0 (entrance, tower base corner): one row per seed."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    labels, tiles = [], []
    for seed in seeds:
        plan = resolve(replace(spec, seed=seed))
        seed_dir = out_dir / f"seed-{seed}"
        build_library(plan, seed_dir, "L0")
        entrance = next(e for e in plan.elements if e.kind == "entrance")
        bays, floors = entrance.tags["bays"], entrance.tags["floors"]
        captions = {
            "entrance": f"{bays[1] - bays[0]} bays x {floors[1] - floors[0]} floors",
            "tower corner": "south-east corner of the tower's base",
        }
        for name, camera in detail_cameras(plan).items():
            path = seed_dir / f"{name.replace(' ', '_')}.png"
            render_tile(seed_dir / "manifest.json", path, camera, tile, samples)
            labels.append((f"seed {seed}  {name}", captions[name], False))
            tiles.append(path)
    _montage(labels, tiles, out_dir / "detail_sheet.jpg", tile, 2)
