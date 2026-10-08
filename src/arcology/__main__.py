"""Command line.

arcology resolve specs/default.json --seed 7 -o plan.json    spec -> plan (no Blender)
arcology build plan.json -o build/seed-7 --lod L2            plan -> library + manifest
arcology sheet specs/default.json -o build/review            golden seeds -> contact sheet
arcology detail specs/default.json -o build/detail           close-ups of 3 seeds at L0
arcology sweep specs/default.json -o build/sweep             style parameters, one per row
arcology batch specs/default.json -o build/batch             100 seeds as silhouettes (L3)
arcology elevations specs/default.json -o build/elevations   layer trees, flat (no Blender)
arcology whatif specs/default.json -o build/whatif           treatments one at a time (L0)
"""

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

from arcology.metrics import failures, measure
from arcology.plan import LODS, Plan
from arcology.resolve import ResolveError, resolve
from arcology.seeds import GOLDEN_SEEDS
from arcology.spec import SpecError, load_spec


def _size(text: str) -> tuple[int, int]:
    w, _, h = text.partition("x")
    return int(w), int(h)


def _sweep(text: str) -> tuple[str, list]:
    """'style.hierarchy=strong,weak' -> ("style.hierarchy", ["strong", "weak"]); values are
    read as JSON where they parse (numbers), else as strings."""
    path, sep, values = text.partition("=")
    if not sep or not values:
        raise argparse.ArgumentTypeError(f"expected PATH=V1,V2,..., got {text!r}")

    def value(v: str):
        try:
            return json.loads(v)
        except json.JSONDecodeError:
            return v

    return path, [value(v) for v in values.split(",")]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="arcology", description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    r = sub.add_parser("resolve", help="spec -> resolved plan (no Blender)")
    r.add_argument("spec", type=Path)
    r.add_argument("--seed", type=int, help="override the spec's seed")
    r.add_argument("-o", "--out", type=Path, help="write the plan here instead of stdout")

    b = sub.add_parser("build", help="plan -> element library + placement manifest")
    b.add_argument("plan", type=Path)
    b.add_argument("-o", "--out", type=Path, required=True)
    b.add_argument("--lod", default="L2", choices=LODS)

    s = sub.add_parser("sheet", help="spec -> contact sheet of many seeds, with metrics")
    s.add_argument("spec", type=Path)
    s.add_argument("--seeds", type=int, nargs="+", help="default: the golden seeds")
    s.add_argument("-o", "--out", type=Path, default=Path("build/review"))
    s.add_argument("--lod", default="L2", choices=LODS)
    s.add_argument("--tile", type=_size, default=(400, 300), help="tile size, e.g. 400x300")
    s.add_argument("--cols", type=int, default=4)
    s.add_argument("--samples", type=int, default=16)

    t = sub.add_parser("detail", help="spec -> close-ups (entrance, bridge, setback, crown) at L0")
    t.add_argument("spec", type=Path)
    t.add_argument("--seeds", type=int, nargs="+", help="default: the first 3 golden seeds")
    t.add_argument("-o", "--out", type=Path, default=Path("build/detail"))
    t.add_argument("--tile", type=_size, default=(400, 300), help="tile size, e.g. 400x300")
    t.add_argument("--samples", type=int, default=24)

    w = sub.add_parser("sweep", help="spec -> one parameter varied per row, one seed")
    w.add_argument("spec", type=Path)
    w.add_argument(
        "--set",
        dest="sweeps",
        type=_sweep,
        action="append",
        metavar="PATH=V1,V2",
        help="a row, e.g. style.hierarchy=strong,weak (repeatable); default: the style sweeps",
    )
    w.add_argument("--seed", type=int, help="default: golden seed 37")
    w.add_argument("-o", "--out", type=Path, default=Path("build/sweep"))
    w.add_argument("--lod", default="L2", choices=LODS)
    w.add_argument("--tile", type=_size, default=(320, 240), help="tile size, e.g. 320x240")
    w.add_argument("--samples", type=int, default=12)

    a = sub.add_parser("batch", help="spec -> many seeds as small silhouettes, with ranges")
    a.add_argument("spec", type=Path)
    a.add_argument("--count", type=int, default=100, help="seeds 0..count-1")
    a.add_argument("-o", "--out", type=Path, default=Path("build/batch"))
    a.add_argument("--lod", default="L3", choices=LODS)
    a.add_argument("--tile", type=_size, default=(160, 120), help="tile size, e.g. 160x120")
    a.add_argument("--cols", type=int, default=10)
    a.add_argument("--samples", type=int, default=8)

    v = sub.add_parser(
        "elevations", help="spec -> south elevations of the layer trees (no Blender)"
    )
    v.add_argument("spec", type=Path)
    v.add_argument("--seeds", type=int, nargs="+", help="default: the golden seeds")
    v.add_argument("-o", "--out", type=Path, default=Path("build/elevations"))
    v.add_argument("--tile", type=_size, default=(480, 420), help="tile size, e.g. 480x420")
    v.add_argument("--cols", type=int, default=4)

    f = sub.add_parser("whatif", help="spec -> the treatments one at a time, then together (L0)")
    f.add_argument("spec", type=Path)
    f.add_argument("--seeds", type=int, nargs="+", help="default: golden seeds 11 and 37")
    f.add_argument("-o", "--out", type=Path, default=Path("build/whatif"))
    f.add_argument("--tile", type=_size, default=(300, 300), help="tile size, e.g. 300x300")
    f.add_argument("--samples", type=int, default=16)

    args = parser.parse_args(argv)
    try:
        if args.command == "resolve":
            spec = load_spec(args.spec)
            plan = resolve(spec if args.seed is None else replace(spec, seed=args.seed))
            if args.out:
                plan.save(args.out)
                m = measure(plan)
                summary = (
                    f"{len(plan.elements)} elements, {m['height_m']:g} m, {m['floors']} floors"
                )
                print(f"{args.out}: {summary}")
            else:
                sys.stdout.write(plan.to_json())
            return 1 if failures(measure(plan)) else 0

        if args.command == "elevations":
            from arcology.elevation import elevation_sheet

            seeds = args.seeds or GOLDEN_SEEDS
            elevation_sheet(load_spec(args.spec), seeds, args.out, tile=args.tile, cols=args.cols)
            print(f"{args.out / 'elevation_sheet.jpg'}: {len(seeds)} seeds")
            return 0

        if args.command == "build":
            from arcology.build import build_library  # imports Blender

            manifest = build_library(Plan.load(args.plan), args.out, args.lod)
            unique, placed = len(manifest["library"]), len(manifest["instances"])
            print(f"{args.out}: {unique} unique elements, {placed} instances")
            return 0

        from arcology.review import (  # imports Blender
            STYLE_SWEEPS,
            SWEEP_SEED,
            WHATIF_SEEDS,
            batch_sheet,
            contact_sheet,
            detail_sheet,
            sweep_sheet,
            whatif_sheet,
        )

        if args.command == "whatif":
            rows = whatif_sheet(
                load_spec(args.spec),
                args.seeds or WHATIF_SEEDS,
                args.out,
                tile=args.tile,
                samples=args.samples,
            )
            failed = [f"{r['seed']} {r['variant']}" for r in rows if failures(r)]
            sheet = args.out / "whatif_sheet.jpg"
            print(f"{sheet}: {len(rows)} tiles, failing: {failed or 'none'}")
            return 1 if failed else 0

        if args.command == "sweep":
            results = sweep_sheet(
                load_spec(args.spec),
                args.sweeps or STYLE_SWEEPS,
                args.out,
                seed=SWEEP_SEED if args.seed is None else args.seed,
                tile=args.tile,
                samples=args.samples,
                lod=args.lod,
            )
            failed = [f"{r['parameter']}={r['value']}" for r in results if failures(r)]
            sheet = args.out / "sweep_sheet.jpg"
            print(f"{sheet}: {len(results)} tiles, failing: {failed or 'none'}")
            return 1 if failed else 0

        if args.command == "batch":
            results = batch_sheet(
                load_spec(args.spec),
                range(args.count),
                args.out,
                tile=args.tile,
                cols=args.cols,
                samples=args.samples,
                lod=args.lod,
            )
            failed = [r["seed"] for r in results if failures(r)]
            sheet = args.out / "batch_sheet.jpg"
            print(f"{sheet}: {len(results)} seeds, failing: {failed or 'none'}")
            return 1 if failed else 0

        if args.command == "detail":
            seeds = args.seeds or GOLDEN_SEEDS[:3]
            detail_sheet(
                load_spec(args.spec), seeds, args.out, tile=args.tile, samples=args.samples
            )
            print(f"{args.out / 'detail_sheet.jpg'}: {len(seeds)} seeds, close-ups at L0")
            return 0

        results = contact_sheet(
            load_spec(args.spec),
            args.seeds or GOLDEN_SEEDS,
            args.out,
            tile=args.tile,
            cols=args.cols,
            samples=args.samples,
            lod=args.lod,
        )
        failed = [r["seed"] for r in results if failures(r)]
        sheet = args.out / "contact_sheet.jpg"
        print(f"{sheet}: {len(results)} seeds, failing checks: {failed or 'none'}")
        return 1 if failed else 0
    except (SpecError, ResolveError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
