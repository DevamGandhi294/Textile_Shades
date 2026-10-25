#!/usr/bin/env python3
"""Quick check that every sample runs through all three checkpoints and writes every file.

    python tests/smoke_test.py
"""
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sketchclean import CleanSettings, EvenSettings, Session, Settings  # noqa: E402

CASES = [
    ("default B&W (AI)", Settings()),
    ("classic B&W", Settings(clean=CleanSettings(method="classic"))),
    ("scanner look", Settings(clean=CleanSettings(output="scan"))),
    ("no beautify", Settings(even=EvenSettings(beautify=0))),
    ("uniform pen 3px", Settings(even=EvenSettings(even_width="uniform", uniform_width=3.0))),
    ("bold, full even width", Settings(clean=CleanSettings(thickness=1.0, contrast=0.5),
                                       even=EvenSettings(even_width="full", smooth=2.0))),
]


def main():
    samples = sorted(p for p in (ROOT / "samples").iterdir() if p.suffix.lower() in (".png", ".jpg", ".jpeg"))
    failures = 0
    with tempfile.TemporaryDirectory() as out:
        for img in samples:
            sess = Session(img)
            for name, st in CASES:
                t = time.time()
                try:
                    files = sess.update(st).export(out, f"{img.stem}_{name.replace(' ', '_')}")
                    want = {"png", "tiff", "bmp", "report"} | ({"svg", "pdf", "eps", "dxf"} if st.clean.output == "bw" else set())
                    missing = want - set(files)
                    empty = [k for k, f in files.items() if Path(f).stat().st_size == 0]
                    assert not missing and not empty, f"missing {missing} empty {empty}"
                    print(f"  ok   {img.name:30s} {name:24s} {time.time() - t:5.1f} s")
                except Exception as e:
                    failures += 1
                    print(f"  FAIL {img.name:30s} {name:24s} {e}")
    print("all passed" if not failures else f"{failures} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
