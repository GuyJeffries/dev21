"""Command line.

arcology resolve specs/default.json --seed 7 -o plan.json    spec -> plan (no Blender)
arcology build plan.json -o build/seed-7 --lod L2            plan -> library + manifest
arcology sheet specs/default.json -o build/review            golden seeds -> contact sheet
arcology detail specs/default.json -o build/detail           close-ups of 3 seeds at L0
"""

import argparse
import sys
from dataclasses import replace
from pathlib import Path

from arcology.metrics import failures, measure
from arcology.plan import LODS, Plan
from arcology.resolve import ResolveError, resolve
from arcology.spec import SpecError, load_spec


def _size(text: str) -> tuple[int, int]:
    w, _, h = text.partition("x")
    return int(w), int(h)


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

    t = sub.add_parser("detail", help="spec -> close-ups (entrance, bridge, crown) at L0")
    t.add_argument("spec", type=Path)
    t.add_argument("--seeds", type=int, nargs="+", help="default: the first 3 golden seeds")
    t.add_argument("-o", "--out", type=Path, default=Path("build/detail"))
    t.add_argument("--tile", type=_size, default=(400, 300), help="tile size, e.g. 400x300")
    t.add_argument("--samples", type=int, default=24)

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

        if args.command == "build":
            from arcology.build import build_library  # imports Blender

            manifest = build_library(Plan.load(args.plan), args.out, args.lod)
            unique, placed = len(manifest["library"]), len(manifest["instances"])
            print(f"{args.out}: {unique} unique elements, {placed} instances")
            return 0

        from arcology.review import GOLDEN_SEEDS, contact_sheet, detail_sheet  # imports Blender

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
