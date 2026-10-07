"""Review renders: contact sheets of many seeds, for pull requests (Blender + Pillow).

Every tile uses one camera, fitted to the box enclosing every building in the sheet, so
relative size reads correctly across seeds. Each tile is rendered from the handover package
(library + manifest) through the stand-in assembler, so the sheet also exercises that path.
Output is a compressed JPEG sized for limited bandwidth, plus the metrics as JSON and Markdown.
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
from arcology.plan import Plan, plan_bounds
from arcology.resolve import resolve
from arcology.spec import Spec

# Fixed seeds rendered on every pull request, so before/after sheets are comparable.
GOLDEN_SEEDS = (11, 23, 37, 41, 53, 67, 71, 89, 97, 101, 113, 127)

SKY = (0.62, 0.70, 0.82)
GROUND = (0.36, 0.38, 0.33)


def shared_camera(plans: list[Plan]) -> dict:
    """One framing for the whole sheet: the box enclosing every plan's bounds."""
    bounds = [plan_bounds(p) for p in plans]
    lo = tuple(min(b[0][i] for b in bounds) for i in range(3))
    hi = tuple(max(b[1][i] for b in bounds) for i in range(3))
    return {"lo": lo, "hi": hi}


def _stage(camera: dict, size: tuple[int, int], samples: int) -> None:
    lo, hi = Vector(camera["lo"]), Vector(camera["hi"])
    extent = max(hi - lo)
    scene = bpy.context.scene
    scene.render.resolution_x, scene.render.resolution_y = size  # before fitting the camera
    scene.render.resolution_percentage = 100

    # Ground far beyond the view, so its edge never shows as a false horizon.
    bpy.ops.mesh.primitive_plane_add(size=extent * 60)
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

    # Look from the south-east, slightly above, then let Blender fit the shared box exactly.
    bpy.ops.object.camera_add()
    cam = bpy.context.object
    cam.data.lens = 35
    view = Vector((-1, 1, -0.45)).normalized()
    cam.rotation_euler = view.to_track_quat("-Z", "Y").to_euler()
    corners = [(x, y, z) for x in (lo.x, hi.x) for y in (lo.y, hi.y) for z in (lo.z, hi.z)]
    fitted, _ = cam.camera_fit_coords(
        bpy.context.evaluated_depsgraph_get(), [c for corner in corners for c in corner]
    )
    cam.location = fitted - view * extent * 0.06  # a little margin
    cam.data.clip_start = 1.0
    cam.data.clip_end = extent * 100  # the default 100 m would cut the building off

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
    bottom = "checks: FAIL " + ", ".join(failed) if failed else "checks: ok"
    return top, bottom


def _montage(results: list[dict], tiles: list[Path], out: Path, size, cols: int) -> None:
    tw, th = size
    strip = 34
    rows = math.ceil(len(tiles) / cols)
    sheet = Image.new("RGB", (cols * tw, rows * (th + strip)), "white")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default(size=13)
    for i, (result, tile) in enumerate(zip(results, tiles, strict=True)):
        x, y = (i % cols) * tw, (i // cols) * (th + strip)
        sheet.paste(Image.open(tile).convert("RGB"), (x, y))
        top, bottom = _label(result)
        draw.text((x + 6, y + th + 3), top, fill="black", font=font)
        colour = "darkred" if failures(result) else "dimgray"
        draw.text((x + 6, y + th + 18), bottom, fill=colour, font=font)
    sheet.save(out, "JPEG", quality=82, optimize=True, progressive=True)


def metrics_markdown(results: list[dict], lod: str) -> str:
    lines = [
        f"### Contact sheet: {len(results)} seeds, {lod}",
        "",
        "| seed | height (m) | floors | podium | tower | footprint (m) | tower base (m) "
        "| slenderness | checks |",
        "|---:|---:|---:|---:|---:|---|---|---:|---|",
    ]
    for r in results:
        failed = failures(r)
        lines.append(
            f"| {r['seed']} | {r['height_m']:.0f} | {r['floors']} | {r['podium_floors']} "
            f"| {r['tower_floors']} | {r['footprint_m'][0]:g} × {r['footprint_m'][1]:g} "
            f"| {r['tower_base_m'][0]:g} × {r['tower_base_m'][1]:g} | {r['slenderness']} "
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
    _montage(results, tiles, out_dir / "contact_sheet.jpg", tile, min(cols, len(tiles)))
    (out_dir / "metrics.json").write_text(json.dumps(results, indent=2) + "\n")
    (out_dir / "metrics.md").write_text(metrics_markdown(results, lod))
    return results
