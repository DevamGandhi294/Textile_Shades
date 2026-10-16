"""Runs the three checkpoints and keeps each result, so a settings change only redoes
the stages after it:

    load ─► 1 scan (once per image) ─► 2 clean ─► 3 even out ─► export

    s = Session("sketch.jpg")             # runs checkpoint 1
    s.update(Settings())                  # runs 2 and 3 (call again after any slider change)
    files = s.export("out/", "sketch")
"""
import json
import time
from pathlib import Path

import cv2
import numpy as np

from .clean import clean, scan_line_width
from .config import Settings
from .even import even
from .export import Page, export_bw, export_scan
from .imageio import hex_rgb, load_gray
from .scan import scan


class Session:
    def __init__(self, path, auto_crop=True):
        t = time.time()
        self.path = str(path)
        self.scan = scan(load_gray(path), auto_crop=auto_crop)
        self.clean = None
        self.even = None
        self.settings = None
        self.ai_prob = None          # AI line probability, computed once per image
        self.ai_info = None
        self.ai_error = None
        self.timing = {"scan": round(time.time() - t, 2)}

    def _ensure_ai(self):
        """Run the AI model once per image (it is the slow step); later setting changes reuse it."""
        if self.ai_prob is not None or self.ai_error:
            return
        from . import ai
        if not ai.available():
            self.ai_error = ai.status()
            return
        try:
            self.ai_prob, self.ai_info = ai.line_probability(self.scan.levelled, scan_line_width(self.scan))
            self.timing["ai"] = self.ai_info["seconds"]
        except Exception as e:                       # never let the AI stop the whole tool
            self.ai_error = f"AI failed, classic method used: {e}"

    def update(self, s: Settings):
        """Re-run checkpoint 2 (and 3 when the output is black & white)."""
        if s.clean.output == "bw" and s.clean.method == "ai":
            self._ensure_ai()
        t = time.time()
        self.clean = clean(self.scan, s.clean, self.ai_prob if s.clean.method == "ai" else None)
        self.timing["clean"] = round(time.time() - t, 2)
        self.even = None
        self.timing.pop("even", None)
        if s.clean.output == "bw":
            t = time.time()
            self.even = even(self.clean, s.even)
            self.timing["even"] = round(time.time() - t, 2)
        self.settings = s
        return self

    # ------------------------------------------------------------- previews (RGB uint8)

    def preview_scan(self):
        return cv2.cvtColor(self.scan.preview, cv2.COLOR_GRAY2RGB)

    def preview_clean(self):
        if self.settings.clean.output == "scan":
            return cv2.cvtColor(self.clean.scan, cv2.COLOR_GRAY2RGB)
        return _lines_rgb(self.clean.mask, "#000000")

    def preview_final(self):
        if self.even is None:
            return cv2.cvtColor(self.clean.scan, cv2.COLOR_GRAY2RGB)
        return _lines_rgb(self.even.mask, self.settings.output.color)

    def preview_check(self):
        """Each closed box in its own colour; green = gaps joined; red circle = loose end."""
        e = self.even
        if e is None:
            return None
        rng = np.random.default_rng(3)
        cols = rng.integers(150, 250, (e.n_areas + 1, 3)).astype(np.uint8)
        cols[0] = 255
        img = cols[e.areas]
        img[e.mask] = 0
        t = max(2, int(e.line_width * 0.6))
        for y0, x0, y1, x1 in e.bridges:
            cv2.line(img, (x0, y0), (x1, y1), (0, 170, 0), t)
        r = max(8, int(e.line_width * 1.5))
        for y, x in e.loose_ends:
            cv2.circle(img, (x, y), r, (230, 0, 0), t)
        return img

    # ------------------------------------------------------------- export

    def export(self, out_dir, stem):
        s = self.settings
        out_dir = Path(out_dir)
        work_h, work_w = self.clean.image.shape
        page = Page(work_w, work_h, s.output.dpi, s.output.width_cm)
        if self.even is not None:
            files, failed = export_bw(out_dir, stem, self.even, page, s.output.color, s.output.formats)
        else:
            files, failed = export_scan(out_dir, stem, self.clean.scan, page, s.output.formats)
        files["report"] = out_dir / f"{stem}_report.json"
        files["report"].write_text(json.dumps(self.report(page, failed), indent=2))
        return files

    def report(self, page=None, failed=None):
        s, e = self.settings, self.even
        rep = {
            "input": Path(self.path).name,
            "output": s.clean.output,
            "page_found_and_flattened": self.scan.page_found,
            "work_size_px": [int(self.clean.image.shape[1]), int(self.clean.image.shape[0])],
            "line_width_px": round(self.clean.line_width, 1),
            "settings": {"clean": vars(s.clean), "even": vars(s.even),
                         "output": {**vars(s.output), "formats": list(s.output.formats)}},
            "seconds": self.timing,
        }
        if page:
            rep["output_size_px"] = [page.out_w, page.out_h]
            rep["dpi"] = page.dpi
        if e is not None:
            rep.update(closed_boxes=e.n_areas, gaps_joined=len(e.bridges), loose_ends=len(e.loose_ends))
        if s.clean.output == "bw":
            rep["lines_from"] = "ai" if (s.clean.method == "ai" and self.ai_prob is not None) else "classic"
            if self.ai_info:
                rep["ai"] = self.ai_info
            if self.ai_error and s.clean.method == "ai":
                rep["ai_note"] = self.ai_error
        if failed:
            rep["failed_formats"] = failed
        return rep


def _lines_rgb(mask, color):
    img = np.full(mask.shape + (3,), 255, np.uint8)
    img[mask] = hex_rgb(color)
    return img


def process(path, settings: Settings, out_dir, auto_crop=True):
    """One-call convenience for scripts and the CLI."""
    s = Session(path, auto_crop).update(settings)
    return s, s.export(out_dir, Path(path).stem)
