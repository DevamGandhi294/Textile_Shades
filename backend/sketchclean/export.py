"""File writers. No external graphics libraries: PDF and EPS are written directly.

Vector files (SVG / PDF / EPS) hold the traced shapes in a `line-art` layer, plus an
optional `fill-boxes` layer: one white shape per closed box, so a designer can recolour
each box directly. Raster files (PNG / TIFF) are rendered at the chosen size and DPI.
"""
from pathlib import Path

import cv2
import numpy as np

from .imageio import hex_rgb, save_bw, save_gray
from .vectorize import render


class Page:
    """Maps working pixels to the output page (pixels and points) for one export."""
    def __init__(self, work_w, work_h, dpi, width_cm=0.0):
        self.work_w, self.work_h, self.dpi = work_w, work_h, dpi
        self.out_w = int(round(width_cm / 2.54 * dpi)) if width_cm else work_w
        self.scale = self.out_w / work_w                     # working px -> output px
        self.out_h = int(round(work_h * self.scale))
        self.pt = 72.0 / dpi * self.scale                     # working px -> points
        self.mm = (self.out_w / dpi * 25.4, self.out_h / dpi * 25.4)


# ----------------------------------------------------------------- closed boxes

def box_outlines(areas, n):
    """One outline (ops) per closed box, holes kept with even-odd fill."""
    if n == 0:
        return []
    ys, xs = np.nonzero(areas)
    ids = areas[ys, xs]
    y0 = np.full(n + 1, 1 << 30); y1 = np.full(n + 1, -1)
    x0 = np.full(n + 1, 1 << 30); x1 = np.full(n + 1, -1)
    np.minimum.at(y0, ids, ys); np.maximum.at(y1, ids, ys)
    np.minimum.at(x0, ids, xs); np.maximum.at(x1, ids, xs)
    out = []
    for rid in range(1, n + 1):
        if y1[rid] < 0:
            continue
        crop = np.pad((areas[y0[rid]:y1[rid] + 1, x0[rid]:x1[rid] + 1] == rid).astype(np.uint8), 1)
        cnts, _ = cv2.findContours(crop, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
        ops = []
        for c in cnts:
            c = c.reshape(-1, 2).astype(float) + (x0[rid] - 0.5, y0[rid] - 0.5)
            if len(c) > 8:
                c = cv2.approxPolyDP(c.astype(np.float32).reshape(-1, 1, 2), 0.8, True).reshape(-1, 2)
            if len(c) >= 3:
                ops += [("M", *c[0])] + [("L", *p) for p in c[1:]] + [("Z",)]
        if ops:
            out.append((rid, ops))
    return out


# ----------------------------------------------------------------- vector writers

def _svg_d(ops):
    parts = []
    for op in ops:
        if op[0] == "Z":
            parts.append("Z")
        else:
            v = op[1:]
            parts.append(op[0] + " ".join(f"{v[i]:.2f},{v[i + 1]:.2f}" for i in range(0, len(v), 2)))
    return " ".join(parts)


def _ps(ops, pdf):
    names = {"M": ("m", "moveto"), "L": ("l", "lineto"), "C": ("c", "curveto"), "Z": ("h", "closepath")}
    return "\n".join(f"{' '.join(f'{v:.2f}' for v in op[1:])} {names[op[0]][0 if pdf else 1]}".strip() for op in ops)


def write_svg(path, shapes, boxes, page: Page, color, n_boxes):
    p = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{page.mm[0]:.2f}mm" height="{page.mm[1]:.2f}mm" '
        f'viewBox="0 0 {page.work_w} {page.work_h}">',
        f'<!-- TextileBorder OutlineTool | {page.out_w}x{page.out_h} px at {page.dpi} DPI | {n_boxes} closed boxes -->',
    ]
    if boxes:
        p.append('<g id="fill-boxes" fill="#FFFFFF" stroke="none" fill-rule="evenodd">')
        p += [f'<path id="box-{rid}" d="{_svg_d(ops)}"/>' for rid, ops in boxes]
        p.append("</g>")
    p.append(f'<g id="line-art" fill="{color}" stroke="none" fill-rule="evenodd">')
    p += [f'<path d="{" ".join(_svg_d(o) for o in shape)}"/>' for shape in shapes]
    p.append("</g></svg>")
    Path(path).write_text("\n".join(p), encoding="utf-8")


def write_pdf(path, shapes, boxes, page: Page, color):
    W, H, k = page.work_w * page.pt, page.work_h * page.pt, page.pt
    r, g, b = (c / 255 for c in hex_rgb(color))
    body = [f"q {k:.6f} 0 0 {-k:.6f} 0 {H:.3f} cm"]           # draw in working px, y down
    if boxes:
        body.append("1 1 1 rg")
        body += [_ps(ops, True) + "\nf*" for _, ops in boxes]
    body.append(f"{r:.4f} {g:.4f} {b:.4f} rg")
    body += ["\n".join(_ps(o, True) for o in shape) + "\nf*" for shape in shapes]
    body.append("Q")
    content = "\n".join(body).encode("latin-1")
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {W:.3f} {H:.3f}] /Contents 4 0 R >>".encode(),
            f"<< /Length {len(content)} >>\nstream\n".encode() + content + b"\nendstream"]
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offs = []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += "".join(f"{o:010d} 00000 n \n" for o in offs).encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    Path(path).write_bytes(bytes(out))


def write_eps(path, shapes, boxes, page: Page, color):
    W, H, k = page.work_w * page.pt, page.work_h * page.pt, page.pt
    r, g, b = (c / 255 for c in hex_rgb(color))
    L = ["%!PS-Adobe-3.0 EPSF-3.0", f"%%BoundingBox: 0 0 {int(np.ceil(W))} {int(np.ceil(H))}",
         f"%%HiResBoundingBox: 0 0 {W:.3f} {H:.3f}", "%%Creator: TextileBorder OutlineTool", "%%EndComments",
         "gsave", f"0 {H:.3f} translate {k:.6f} {-k:.6f} scale"]
    if boxes:
        L.append("1 1 1 setrgbcolor")
        L += ["newpath\n" + _ps(ops, False) + "\neofill" for _, ops in boxes]
    L.append(f"{r:.4f} {g:.4f} {b:.4f} setrgbcolor")
    L += ["newpath\n" + "\n".join(_ps(o, False) for o in shape) + "\neofill" for shape in shapes]
    L += ["grestore", "showpage", "%%EOF"]
    Path(path).write_text("\n".join(L) + "\n", encoding="latin-1")


# ----------------------------------------------------------------- DXF (Wilcom, CAD)

def write_dxf(path, shapes, centrelines, page: Page):
    """AutoCAD R12 ASCII DXF in millimetres — the most widely readable DXF version.

    Layers:
      OUTLINE     closed polylines: the edges of every line shape (curves flattened)
      CENTERLINE  open / closed polylines along the middle of every line, useful for
                  run-stitch outlines in embroidery software
    Wilcom EmbroideryStudio: Import Graphic → choose Millimeters so the size is correct.
    """
    from .vectorize import flatten
    mm = 25.4 / page.dpi * page.scale                       # working px -> mm
    H = page.work_h
    out = ["0", "SECTION", "2", "HEADER", "9", "$ACADVER", "1", "AC1009",
           "9", "$INSUNITS", "70", "4",                       # 4 = millimetres
           "9", "$EXTMIN", "10", "0.0", "20", "0.0",
           "9", "$EXTMAX", "10", f"{page.work_w * mm:.3f}", "20", f"{H * mm:.3f}",
           "0", "ENDSEC",
           "0", "SECTION", "2", "TABLES", "0", "TABLE", "2", "LAYER", "70", "2",
           "0", "LAYER", "2", "OUTLINE", "70", "0", "62", "7", "6", "CONTINUOUS",
           "0", "LAYER", "2", "CENTERLINE", "70", "0", "62", "1", "6", "CONTINUOUS",
           "0", "ENDTAB", "0", "ENDSEC",
           "0", "SECTION", "2", "ENTITIES"]

    def poly(points, layer, closed):
        if len(points) < 2:
            return
        out.extend(["0", "POLYLINE", "8", layer, "66", "1", "10", "0.0", "20", "0.0", "30", "0.0",
                    "70", "1" if closed else "0"])
        for x, y in points:
            out.extend(["0", "VERTEX", "8", layer, "10", f"{x * mm:.3f}", "20", f"{(H - y) * mm:.3f}", "30", "0.0"])
        out.extend(["0", "SEQEND", "8", layer])

    for shape in shapes:
        for ops in shape:
            pts = flatten(ops, step=2.0)
            if len(pts) > 2 and np.allclose(pts[0], pts[-1]):
                pts = pts[:-1]
            poly(pts, "OUTLINE", True)
    for xy, closed in centrelines:
        poly(xy, "CENTERLINE", closed)
    out.extend(["0", "ENDSEC", "0", "EOF"])
    Path(path).write_text("\n".join(out) + "\n", encoding="ascii")


# ----------------------------------------------------------------- export

def export_bw(out_dir, stem, even, page: Page, color, formats, fill_boxes=True):
    """Black & white result: vector files + 2-colour raster files."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    files, failed = {}, {}
    boxes = box_outlines(even.areas, even.n_areas) if fill_boxes and {"svg", "pdf", "eps"} & set(formats) else []
    raster = None
    rgb = hex_rgb(color)

    def dxf(f):
        from .lines import centre_lines, centreline_paths
        write_dxf(f, even.shapes, centreline_paths(centre_lines(even.mask, int(max(4, even.line_width)))), page)

    jobs = {
        "svg": lambda f: write_svg(f, even.shapes, boxes, page, color, even.n_areas),
        "pdf": lambda f: write_pdf(f, even.shapes, boxes, page, color),
        "eps": lambda f: write_eps(f, even.shapes, boxes, page, color),
        "dxf": dxf,
        "png": lambda f: save_bw(raster, f, page.dpi, rgb, transparent=True),
        "tiff": lambda f: save_bw(raster, f, page.dpi, rgb),
        "bmp": lambda f: save_bw(raster, f, page.dpi, rgb),
    }
    for fmt in ("svg", "pdf", "eps", "dxf", "png", "tiff", "bmp"):
        if fmt not in formats:
            continue
        if fmt in ("png", "tiff", "bmp") and raster is None:
            raster = render(even.shapes, (page.out_h, page.out_w), page.scale)
        f = out_dir / f"{stem}.{'tif' if fmt == 'tiff' else fmt}"
        try:
            jobs[fmt](f)
            files[fmt] = f
        except Exception as e:                       # one bad format must not lose the others
            failed[fmt] = str(e)
    return files, failed


def export_scan(out_dir, stem, scan_img, page: Page, formats):
    """Scanner-look result: grayscale PNG / TIFF (vector formats need the B&W output)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    img = scan_img
    if (page.out_w, page.out_h) != (scan_img.shape[1], scan_img.shape[0]):
        interp = cv2.INTER_AREA if page.scale < 1 else cv2.INTER_CUBIC
        img = cv2.resize(scan_img, (page.out_w, page.out_h), interpolation=interp)
    files, failed = {}, {}
    for fmt in ("png", "tiff", "bmp"):
        if fmt in formats:
            f = out_dir / f"{stem}_scan.{'tif' if fmt == 'tiff' else fmt}"
            try:
                save_gray(img, f, page.dpi)
                files[fmt] = f
            except Exception as e:
                failed[fmt] = str(e)
    return files, failed
