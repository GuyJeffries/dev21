"""Command line: python -m assetgen --seed 42 --out build/assets --preview build/preview.png"""

import argparse
import sys
from pathlib import Path

from assetgen.export import export_set
from assetgen.generators import build_set
from assetgen.preview import render_preview


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="assetgen", description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--rocks", type=int, default=4)
    parser.add_argument("--trees", type=int, default=3)
    parser.add_argument("--out", type=Path, default=Path("build/assets"))
    parser.add_argument("--preview", type=Path, help="also render a PNG preview of the set")
    args = parser.parse_args(argv)

    objs = build_set(args.seed, rocks=args.rocks, trees=args.trees)
    manifest = export_set(objs, args.out, args.seed)
    for asset in manifest["assets"]:
        print(f"{asset['name']}: {asset['verts']} verts, {asset['tris']} tris -> {asset['file']}")
    if args.preview:
        args.preview.parent.mkdir(parents=True, exist_ok=True)
        render_preview(objs, args.preview.resolve(), args.seed)
        print(f"preview -> {args.preview}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
