"""Beautify: redraw the drawing the way a professional would ink it.

A beginner's line has three kinds of error; each gets its own fix:
  * hand shake (small wobble along the line)  → smooth the line's centre path
  * thick / thin (pressure, overdrawing)      → redraw with one steady pen width
  * lines that stop just short of each other  → extend the end along its own direction
                                                until it touches the line it aimed at

Nothing else is added or removed: every stroke is redrawn on its own centre path,
junctions stay exactly where they were, and an end is only extended when it is
pointing at another line that is close (a few pen widths).

How:
  1. centre lines of the B&W drawing (whiskers from fat strokes removed)
  2. split into paths between ends and junctions (lines.centreline_paths, unsmoothed)
  3. each path is low-pass filtered (Gaussian on x and y along the path); its two end
     points are pinned, so connected lines stay connected
  4. dead ends: march along the end's direction; if another line is hit within the
     reach, the path is extended to it
  5. all paths are drawn with a round pen; in dense hatching the pen is narrowed so
     the cells stay open
"""
import cv2
import numpy as np
from skimage.morphology import skeletonize

from .lines import degree, disk, neighbour_masks, neighbours

SH = 4                                     # fixed-point bits for sub-pixel drawing


# ----------------------------------------------------------------- paths

def raw_paths(skel):
    """Centre lines → list of (points_xy float array, closed bool), pixel accurate."""
    masks = neighbour_masks(skel)
    deg = degree(masks)
    visited = np.zeros(skel.shape, bool)
    out = []
    nodes = [tuple(p) for p in np.argwhere(skel & (deg != 2) & (deg > 0))]
    for node in nodes:
        for nb in neighbours(masks, *node):
            if deg[nb] != 2:
                if node < nb:
                    out.append(([node, nb], False))
                continue
            if visited[nb]:
                continue
            path, prev, cur = [node, nb], node, nb
            visited[nb] = True
            while deg[cur] == 2:
                nxt = [p for p in neighbours(masks, *cur) if p != prev]
                if not nxt or (deg[nxt[0]] == 2 and visited[nxt[0]]):
                    break
                prev, cur = cur, nxt[0]
                path.append(cur)
                if deg[cur] == 2:
                    visited[cur] = True
            out.append((path, False))
    for start in map(tuple, np.argwhere(skel & (deg == 2) & ~visited)):
        if visited[start]:
            continue
        path, prev, cur = [start], None, start
        visited[start] = True
        while True:
            nxt = [p for p in neighbours(masks, *cur) if p != prev and (not visited[p] or p == start)]
            if not nxt or nxt[0] == start:
                break
            prev, cur = cur, nxt[0]
            visited[cur] = True
            path.append(cur)
        out.append((path, True))
    res = []
    for path, closed in out:
        xy = np.array([(x + 0.5, y + 0.5) for y, x in path], float)
        res.append((xy, closed, deg[path[0]] == 1, deg[path[-1]] == 1))
    return res


def smooth_path(xy, closed, sigma):
    """Gaussian low-pass of a path. Open paths keep both end points fixed (the filter is
    applied to the deviation from the straight chord, which is zero at the ends)."""
    n = len(xy)
    if n < 5 or sigma <= 0:
        return xy
    sigma = min(sigma, n / 4)
    r = max(1, int(3 * sigma))
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2)
    k /= k.sum()
    if closed:
        pad = np.r_[xy[-r:], xy, xy[:r]] if n > r else np.tile(xy, (3, 1))
        sm = np.c_[np.convolve(pad[:, 0], k, "same"), np.convolve(pad[:, 1], k, "same")]
        return sm[r:r + n] if n > r else sm[n:2 * n]
    t = np.linspace(0, 1, n)[:, None]
    chord = xy[0] + t * (xy[-1] - xy[0])
    dev = xy - chord
    # odd reflection about the pinned end points keeps the ends at zero deviation
    pad = np.r_[-dev[r:0:-1], dev, -dev[-2:-r - 2:-1]]
    sm = np.c_[np.convolve(pad[:, 0], k, "same"), np.convolve(pad[:, 1], k, "same")][r:r + n]
    out = chord + sm
    out[0], out[-1] = xy[0], xy[-1]
    return out


# ----------------------------------------------------------------- closing short ends

def extend_end(xy, at_start, ink, reach, look_back, own_r):
    """March from a dead end along its direction; return the extension points if another
    line is hit within `reach` pixels, else None.

    Ink closer than own_r to this line's own points is its own stroke, not a target, so a
    line is never extended back onto itself."""
    pts = xy if not at_start else xy[::-1]
    n = len(pts)
    if n < 4:
        return None
    a = pts[max(0, n - 1 - look_back)]
    b = pts[-1]
    d = b - a
    L = float(np.hypot(*d))
    if L < 1e-6:
        return None
    d /= L
    near = pts[max(0, n - 1 - int(reach * 2)):]        # own points that could be in the way
    h, w = ink.shape
    step = 0.75
    for i in range(1, int(reach / step) + 1):
        p = b + d * step * i
        x, y = int(p[0]), int(p[1])
        if not (0 <= x < w and 0 <= y < h):
            return None
        if ink[y, x] and np.min(np.hypot(*(near - p).T)) > own_r:
            return np.array([b, p])
    return None


# ----------------------------------------------------------------- drawing

def _poly(img, pts, closed, width):
    p = np.round(pts * (1 << SH)).astype(np.int32).reshape(-1, 1, 2)
    t = max(1, int(round(width)))
    cv2.polylines(img, [p], closed, 255, t, cv2.LINE_AA, shift=SH)
    if not closed and len(pts):                      # round caps
        for q in (pts[0], pts[-1]):
            c = tuple(int(v) for v in np.round(q * (1 << SH)))
            cv2.circle(img, c, max(1, int(round(width / 2 * (1 << SH)))), 255, -1, cv2.LINE_AA, shift=SH)


# ----------------------------------------------------------------- run

def beautify(mask, pen, strength=1.0, close_ends=True, unit=1.0):
    """mask: bool B&W drawing. pen: pen width in pixels. strength: 0..2 curve smoothing.
    Returns (bool mask redrawn, list of end extensions as (y0, x0, y1, x1))."""
    from .even import prune_by_radius                # whisker removal for fat strokes
    m = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_CLOSE, disk(min(1.5, pen * 0.12))).astype(bool)
    dist = cv2.distanceTransform(m.astype(np.uint8), cv2.DIST_L2, 5)
    skel = prune_by_radius(skeletonize(m), dist)

    # room around each line (dense hatching has little room → narrower pen there)
    gap = cv2.distanceTransform((~m).astype(np.uint8), cv2.DIST_L2, 5)
    room = cv2.dilate(gap, disk(max(2.0, pen)))

    # small marks (dots, short ticks) are kept as their own shape, not redrawn as strokes
    n_cc, lab, st, _ = cv2.connectedComponentsWithStats(m.astype(np.uint8), connectivity=8)
    small = np.maximum(st[:, cv2.CC_STAT_WIDTH], st[:, cv2.CC_STAT_HEIGHT]) <= pen * 2.5
    small[0] = False
    marks = small[lab]
    skel &= ~marks

    paths = raw_paths(skel)
    sigma = pen * 0.9 * strength                     # wobble shorter than ~2 pen widths is removed
    canvas = np.zeros(mask.shape, np.uint8)
    smoothed = []
    for xy, closed, start_free, end_free in paths:
        sxy = smooth_path(xy, closed, sigma) if len(xy) >= 5 else xy
        iy = np.clip(xy[:, 1].astype(int), 0, mask.shape[0] - 1)
        ix = np.clip(xy[:, 0].astype(int), 0, mask.shape[1] - 1)
        w = float(min(pen, max(2.0, 2 * np.median(dist[iy, ix]), 1.2 * np.median(room[iy, ix]))))
        smoothed.append((sxy, closed, start_free, end_free, w))

    extended = []                                    # [(y0, x0, y1, x1)] for the check view
    if close_ends:
        reach = max(6.0, pen * 3.0, unit * 4)        # how far a line may be continued
        for sxy, closed, sf, ef, w in smoothed:
            # w < pen means the pen was narrowed for dense hatching / texture: lines there
            # end on purpose, and joining them would add marks that are not in the drawing
            if closed or len(sxy) < 6 or w < pen * 0.85:
                continue
            for at_start, free in ((True, sf), (False, ef)):
                if not free:
                    continue
                ext = extend_end(sxy, at_start, m, reach, look_back=max(4, int(pen * 1.5)),
                                 own_r=w / 2 + max(2.0, pen * 0.5))
                if ext is not None:
                    _poly(canvas, ext, False, w)
                    extended.append((int(ext[0][1]), int(ext[0][0]), int(ext[1][1]), int(ext[1][0])))
    for sxy, closed, _, _, w in smoothed:
        _poly(canvas, sxy, closed, w)

    out = canvas > 127
    if marks.any():                                  # dots: original shape, edges rounded off
        soft = cv2.GaussianBlur(marks.astype(np.float32), (0, 0), max(0.8, pen * 0.12)) > 0.5
        out |= soft
    return out, extended
