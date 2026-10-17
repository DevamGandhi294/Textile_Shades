"""Black & white lines -> smooth vector shapes.

Every ink shape is traced as its outline (outer edge + holes), so line weight and
detail are kept exactly as drawn. Each outline is treated like a 1-D signal:
  1. low-pass filter (Gaussian) to remove hand wobble and pixel stair-steps,
  2. decimate with Douglas–Peucker: keep only points needed within an error bound,
  3. fit curves through the points; long segments become exact straight lines.

A shape is a list of closed outlines; an outline is a list of drawing ops:
('M', x, y) move · ('L', x, y) line · ('C', x1, y1, x2, y2, x, y) curve · ('Z',) close.
The same ops are written to SVG, PDF and EPS, and filled for PNG/TIFF.
"""
import cv2
import numpy as np


def _smooth_closed(pts, sigma):
    n = len(pts)
    if n < 8 or sigma <= 0:
        return pts
    r = min(int(3 * sigma), n // 2 - 1)
    if r < 1:
        return pts
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2)
    k /= k.sum()
    pad = np.r_[pts[-r:], pts, pts[:r]]
    return np.c_[np.convolve(pad[:, 0], k, "same")[r:-r], np.convolve(pad[:, 1], k, "same")[r:-r]]


def _outline_ops(pts, straight_len):
    """Closed point list -> ops. Segments longer than straight_len are straight lines;
    the curve next to a straight line leaves along that line, so there is no kink."""
    n = len(pts)
    if n < 3:
        return []
    L = lambda a: float(np.hypot(*a))
    ops = [("M", *pts[0])]
    for i in range(n):
        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[(i + 1) % n], pts[(i + 2) % n]
        seg = L(p2 - p1)
        if seg >= straight_len:
            ops.append(("L", *p2))
            continue
        t1 = (p2 - p0) / 6 if L(p1 - p0) < straight_len else (p1 - p0) / max(L(p1 - p0), 1e-6) * seg / 3
        t2 = (p3 - p1) / 6 if L(p3 - p2) < straight_len else (p3 - p2) / max(L(p3 - p2), 1e-6) * seg / 3
        ops.append(("C", *(p1 + t1), *(p2 - t2), *p2))
    ops.append(("Z",))
    return ops


def smooth_mask(mask, smooth):
    """Round off jagged edges by blurring the B&W image and thresholding it again.

    Unlike smoothing each traced outline, this treats every part of the drawing by its
    own size: a thin hatch stroke and a bold outline next to it are both kept, because
    the blur is small compared with any real stroke (capped at sigma 2 px). Edges get
    smoother; strokes keep their width and place.
    """
    sigma = min(2.0, 0.6 + 0.7 * smooth)
    b = cv2.GaussianBlur(mask.astype(np.float32), (0, 0), sigma)
    return b > 0.5


def trace(mask, lw, smooth=1.0):
    """Trace all ink shapes.

    smooth 0 = follow the pencil closely, no forced straight lines
           1 = balanced; long near-straight runs become straight
           2 = very smooth; shorter, looser runs become straight too
    """
    mask = smooth_mask(mask, smooth)
    cnts, hier = cv2.findContours(mask.astype(np.uint8), cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    if hier is None:
        return []
    hier = hier[0]
    level = 0.5 + 0.5 * smooth                       # 0.5 .. 1.5
    straighten = 0.0 if smooth < 0.25 else smooth * 1.25
    shapes = []
    for i, c in enumerate(cnts):
        if hier[i][3] != -1:                         # holes travel with their outer shape
            continue
        group, j = [c], hier[i][2]
        while j != -1:
            group.append(cnts[j])
            j = hier[j][0]
        # this shape's own stroke width (ink area / half its total edge length), so thin
        # hatching is smoothed gently and bold outlines more strongly
        area = cv2.contourArea(group[0]) - sum(cv2.contourArea(g) for g in group[1:])
        perim = sum(len(g) for g in group)
        w = float(np.clip(2 * area / max(perim / 2, 1) / 2, 1.0, lw))
        # the mask is already smooth; the outline only loses its pixel stair-steps here.
        # The error bound is small next to the thinnest stroke, so nothing is cut.
        eps = min(0.45 + 0.35 * smooth, max(0.4, w * 0.25)) * (1 + 0.3 * max(0.0, straighten - 1))
        straight_len = float("inf") if straighten <= 0 else max(12.0, w * 6 / max(straighten, 0.5))
        outlines = []
        for g in group:
            n = len(g)
            pts = g.reshape(-1, 2).astype(float) + 0.5
            if n >= 12:
                pts = _smooth_closed(pts, min(0.9, n / 25))
            if len(pts) >= 3:
                pts = cv2.approxPolyDP(pts.astype(np.float32).reshape(-1, 1, 2),
                                       eps if n >= 40 else 0.4, True).reshape(-1, 2).astype(float)
            ops = _outline_ops(pts, straight_len)
            if ops:
                outlines.append(ops)
        if outlines:
            shapes.append(outlines)
    return shapes


def flatten(ops, step=1.5):
    """Ops -> polygon points (curves sampled every ~step pixels)."""
    pts, cur = [], None
    for op in ops:
        if op[0] in ("M", "L"):
            cur = np.array(op[1:3])
            pts.append(cur)
        elif op[0] == "C":
            p0, c1, c2, p3 = cur, np.array(op[1:3]), np.array(op[3:5]), np.array(op[5:7])
            n = max(2, int((np.hypot(*(c1 - p0)) + np.hypot(*(c2 - c1)) + np.hypot(*(p3 - c2))) / step))
            t = np.linspace(0, 1, n + 1)[1:, None]
            pts.extend((1 - t) ** 3 * p0 + 3 * (1 - t) ** 2 * t * c1 + 3 * (1 - t) * t ** 2 * c2 + t ** 3 * p3)
            cur = p3
    return np.array(pts)


def render(shapes, size, scale=1.0, antialias=False):
    """Fill the shapes into a bool image of `size` (h, w). Hard edges by default, so the
    file has exactly two colours and a paint-bucket fill never leaks through grey pixels."""
    h, w = size
    ink = np.zeros((h, w), np.uint8)
    SH = 4
    for shape in shapes:
        polys = [np.round(flatten(o, max(0.75, 1.5 / scale)) * scale * (1 << SH)).astype(np.int32).reshape(-1, 1, 2)
                 for o in shape]
        polys = [p for p in polys if len(p) >= 3]
        if polys:
            cv2.fillPoly(ink, polys, 255, cv2.LINE_AA if antialias else cv2.LINE_8, shift=SH)
    return ink > 127


def count_ops(shapes):
    ops = [o for s in shapes for outline in s for o in outline]
    return {"curves": sum(o[0] == "C" for o in ops), "straight": sum(o[0] == "L" for o in ops)}
