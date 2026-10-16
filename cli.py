#!/usr/bin/env python3
"""TextileBorder OutlineTool — command line (single files or batches).

Examples
  python cli.py sketch.jpg                         AI black & white + vector files in ./outputs
  python cli.py sketch.jpg --method classic        without the AI model
  python cli.py sketch.jpg --output scan           scanner look (grayscale PNG / TIFF)
  python cli.py sketch.jpg --thickness 0.5 --even full --smooth 1.5
  python cli.py scans/*.jpg --out results --width-cm 30 --dpi 300
"""
import argparse
import sys
import time
from pathlib import Path

from sketchclean import CleanSettings, EvenSettings, OutputSettings, Session, Settings


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("inputs", nargs="+", help="photos or scans")
    p.add_argument("--out", default="outputs", help="output folder (default: outputs)")
    p.add_argument("--output", choices=["bw", "scan"], default="bw", help="bw = clean lines, scan = scanner look")
    p.add_argument("--method", choices=["ai", "classic"], default="ai",
                   help="B&W line finder: ai (ONNX model in ./models) or classic (default ai)")
    p.add_argument("--no-detail", action="store_true", help="AI: do not add back hatching / dots")
    p.add_argument("--no-crop", action="store_true", help="do not auto-crop the paper in photos")

    c = p.add_argument_group("2 · clean")
    c.add_argument("--keep-shading", action="store_true", help="do not remove soft shading / smudges")
    c.add_argument("--contrast", type=float, default=0.0, help="-1 softer .. +1 stronger (default 0)")
    c.add_argument("--thickness", type=float, default=0.0, help="-2 thinner .. +3 bolder (default 0)")
    c.add_argument("--sharpness", type=float, default=0.6, help="0 .. 2, scanner output (default 0.6)")

    e = p.add_argument_group("3 · even out (bw)")
    e.add_argument("--even", choices=["uniform", "light", "full", "off"], default="uniform",
                   help="line width: uniform = same pen width everywhere (default), light, full = per line, off")
    e.add_argument("--pen", type=float, default=0.0, help="uniform pen width in photo pixels (0 = automatic)")
    e.add_argument("--beautify", type=float, default=1.0,
                   help="uniform: 0 off .. 1 normal .. 2 strong — smooth curves, close lines that stop short")
    e.add_argument("--smooth", type=float, default=1.0, help="0 follow pencil .. 2 very smooth (default 1)")
    e.add_argument("--no-join", action="store_true", help="do not bridge small gaps")

    o = p.add_argument_group("download")
    o.add_argument("--color", default="#000000", help="line colour (default #000000)")
    o.add_argument("--dpi", type=int, default=300)
    o.add_argument("--width-cm", type=float, default=0.0, help="output width in cm (0 = automatic)")
    o.add_argument("--formats", default="png,tiff,bmp,svg,pdf,eps,dxf")
    a = p.parse_args(argv)

    settings = Settings(
        clean=CleanSettings(output=a.output, method=a.method, keep_detail=not a.no_detail, remove_shading=not a.keep_shading, contrast=a.contrast,
                            sharpness=a.sharpness, thickness=a.thickness),
        even=EvenSettings(even_width=a.even, uniform_width=a.pen, beautify=a.beautify, smooth=a.smooth, join_gaps=not a.no_join),
        output=OutputSettings(color=a.color, dpi=a.dpi, width_cm=a.width_cm,
                              formats=tuple(f.strip().lower() for f in a.formats.split(","))))

    ok = True
    for f in a.inputs:
        t = time.time()
        try:
            s = Session(f, auto_crop=not a.no_crop).update(settings)
            files = s.export(a.out, Path(f).stem)
        except Exception as ex:                      # keep going through a batch
            print(f"[FAIL] {f}: {ex}", file=sys.stderr)
            ok = False
            continue
        rep = s.report()
        if rep.get("ai_note"):
            print(f"     note: {rep['ai_note']}")
        src = f" [{rep['lines_from']} lines]" if "lines_from" in rep else ""
        extra = src + ((f" | {rep['closed_boxes']} closed boxes, {rep['gaps_joined']} gaps joined, "
                        f"{rep['loose_ends']} loose ends") if "closed_boxes" in rep else "")
        print(f"[OK] {f} ({time.time() - t:.1f} s){extra}")
        print("     " + ", ".join(Path(v).name for v in files.values()))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
