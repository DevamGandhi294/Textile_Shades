"""Checkpoint 3 — fix uneven lines (black & white output).

Three kinds of unevenness, three fixes:
  * small breaks    → bridge two loose ends that face each other   (join_gaps)
  * uneven width    → trim bulges and fill thin spots, or redraw at one width  (even_width)
  * wobbly edges    → smooth the traced outline; near-straight runs become straight  (smooth)

Solid filled areas and dots are protected: evening the width only touches lines.
"""
from dataclasses import dataclass

import cv2
import numpy as np

from .clean import CleanResult
from .config import EvenSettings
from .lines import centre_lines, closed_areas, disk, find_gap_bridges, line_width, loose_ends
from .vectorize import render, trace


@dataclass
class EvenResult:
    mask: np.ndarray            # bool, final lines at working size (rendered from the vector shapes)
    shapes: list                # vector shapes (see vectorize.py)
    bridges: list               # gaps that were joined [(y0, x0, y1, x1)]
    loose_ends: list            # line ends still open [(y, x)]
    areas: np.ndarray           # int32 label image of closed boxes
    n_areas: int
    line_width: float


def join_gaps(mask, lw, unit):
    """Draw a short bridge where a line is broken. Nothing else in the drawing changes."""
    skel = centre_lines(mask, int(max(6, lw * 2)))
    bridges = find_gap_bridges(skel, max_gap=int(max(12, lw * 6, unit * 3)), min_len=int(max(20, unit * 8)))
    if bridges:
        # each bridge as thick as the line it repairs (thin hatch gets a thin bridge)
        dist = cv2.distanceTransform(mask.astype(np.uint8), cv2.DIST_L2, 3)
        k = max(3, int(lw) | 1)
        local = cv2.dilate(dist, np.ones((k, k), np.uint8))
        m8 = mask.astype(np.uint8)
        for y0, x0, y1, x1 in bridges:
            t = int(round(min(lw, 2 * min(local[y0, x0], local[y1, x1]))))
            cv2.line(m8, (x0, y0), (x1, y1), 1, max(1, t), cv2.LINE_8)
        mask = m8 > 0
    return mask, bridges


def _discs(skel, radius):
    """Draw a disc of the given radius (per pixel) at every centre-line pixel.
    Radii are grouped in 0.5 px steps so this is a handful of dilations, not a loop."""
    out = np.zeros(skel.shape, bool)
    q = np.round(radius * 2) / 2
    for r in np.unique(q[skel]):
        out |= cv2.dilate((skel & (q == r)).astype(np.uint8), disk(max(0.5, r))).astype(bool)
    return out


def even_width(mask, lw, unit, mode):
    """Even out line width, judged against each line's OWN typical width nearby, so fine
    hatching stays fine and bold outlines stay bold.

    light: trim spots wider than 1.5× and fill spots thinner than 0.65× the local width.
    full:  redraw every line at exactly its local typical width along its centre line.
    """
    if mode == "off":
        return mask
    # only very short whiskers are pruned here: a hatch segment between two crossings
    # is short too, and every real stroke needs its centre line or it would be trimmed away
    skel = centre_lines(mask, int(max(3, lw * 0.6)))
    dist = cv2.distanceTransform(mask.astype(np.uint8), cv2.DIST_L2, 3)

    # protect solid filled areas (much wider than a line) and dots / tiny marks
    solid = cv2.dilate((dist > lw * 1.5).astype(np.uint8), disk(lw * 1.5)).astype(bool) & mask
    n, lab, st, _ = cv2.connectedComponentsWithStats(skel.astype(np.uint8), connectivity=8)
    short = st[:, cv2.CC_STAT_AREA] < max(20, unit * 8)
    short[0] = False
    small = cv2.dilate((short[lab] & skel).astype(np.uint8), disk(lw)).astype(bool) & mask
    keep = solid | small
    sk = skel & ~short[lab] & ~solid

    # local typical radius: average of the centre-line radii within about one line width
    win = (int(lw) | 1,) * 2
    r_here = np.where(sk, dist, 0).astype(np.float32)
    r_sum = cv2.blur(r_here, win)
    r_cnt = cv2.blur(sk.astype(np.float32), win)
    r_typ = np.where(r_cnt > 0, r_sum / np.maximum(r_cnt, 1e-6), lw / 2)
    # a thin line next to a bold one must not be inflated to the bold one's width:
    # a spot is never widened by more than 40 % of its own width
    r_typ = np.minimum(r_typ, r_here * 1.4 + 0.5)

    if mode == "full":
        out = _discs(sk, np.maximum(0.75, r_typ))
    else:
        out = (mask & _discs(sk, r_typ * 1.5)) | _discs(sk, np.maximum(0.75, r_typ * 0.65))
    return out | keep


# ----------------------------------------------------------------- uniform width

def pen_width(mask):
    """The width of a normal, lightly drawn stroke.

    Measured along the centre lines as twice the distance to the edge, and taken at the
    30th percentile: places that were pressed hard or drawn over several times are wider,
    and they are a minority, so they cannot pull this value up the way an average would."""
    sk = centre_lines(mask, 3)
    if not sk.any():
        return 3.0
    d = cv2.distanceTransform(mask.astype(np.uint8), cv2.DIST_L2, 5)
    return float(max(2.0, np.percentile(d[sk] * 2, 30)))


def prune_by_radius(skel, dist, factor=1.3):
    """Remove side branches that only exist because a stroke is fat.

    Thinning a wide, overdrawn stroke or a dark blob creates short whiskers that run from
    its centre to its edge. Such a whisker is about as long as the stroke's half-width,
    so a branch shorter than `factor` × the half-width where it joins is removed. Real
    short strokes on thin lines are much longer than their half-width and are kept."""
    from .lines import degree, neighbour_masks, neighbours, walk
    skel = skel.copy()
    for _ in range(3):
        masks = neighbour_masks(skel)
        deg = degree(masks)
        removed = 0
        for y, x in np.argwhere(skel & (deg == 1)):
            nb = neighbours(masks, y, x)
            if not nb:
                continue
            path = walk(masks, (y, x), nb[0], 400)
            j = path[-1]
            if deg[j] >= 3 and len(path) <= max(3.0, factor * dist[j]):
                for p in path[:-1]:
                    skel[p] = False
                removed += 1
        if not removed:
            break
    return skel


def uniform_width(mask, width):
    """Redraw every line along its centre at exactly `width` pixels.

    Overdrawn, pressed-hard and smudged-thick parts come out the same width as everything
    else; dots become round dots of that width. Two passes of the pencil drawn a hair apart
    are first merged into one stroke (a small closing), so they give one line, not two."""
    # only passes that (almost) touch are merged; a larger closing would also fuse separate
    # nearby lines and rows of dots
    m = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_CLOSE, disk(min(1.5, width * 0.12))).astype(bool)
    dist = cv2.distanceTransform(m.astype(np.uint8), cv2.DIST_L2, 5)
    from skimage.morphology import skeletonize
    skel = prune_by_radius(skeletonize(m), dist)
    # 1. TRIM: ink is kept only within half a pen width of a centre line, so overdrawn,
    #    pressed-hard and smudged parts are cut back to pen width. Nothing new is created,
    #    so hatching cells and gaps between lines stay open.
    trim = m & _discs(skel, np.full(skel.shape, width / 2, np.float32))
    # 2. FILL: thin parts are widened up to pen width, but only where there is room: the
    #    added width is capped at 60 % of the open paper around the line, so dense hatching
    #    is not filled in and neighbouring lines do not merge.
    gap = cv2.distanceTransform((~m).astype(np.uint8), cv2.DIST_L2, 5)
    room = cv2.dilate(gap, disk(max(2.0, width)))
    fill = _discs(skel, np.minimum(width / 2, np.maximum(dist, 0.6 * room)))
    out = trim | fill
    # isolated dots smaller than the pen keep their round shape at pen size
    n, lab, st, _ = cv2.connectedComponentsWithStats(m.astype(np.uint8), connectivity=8)
    small = (np.maximum(st[:, cv2.CC_STAT_WIDTH], st[:, cv2.CC_STAT_HEIGHT]) <= width * 1.5)
    small[0] = False
    if small.any():
        dots = np.zeros_like(out, np.uint8)
        for i in np.nonzero(small)[0]:
            x, y = st[i, cv2.CC_STAT_LEFT] + st[i, cv2.CC_STAT_WIDTH] / 2, st[i, cv2.CC_STAT_TOP] + st[i, cv2.CC_STAT_HEIGHT] / 2
            cv2.circle(dots, (int(round(x)), int(round(y))), max(1, int(round(width / 2))), 1, -1)
        out |= dots.astype(bool)
    return out


def even(clean: CleanResult, s: EvenSettings) -> EvenResult:
    mask, unit = clean.mask, clean.unit
    lw = clean.line_width

    bridges = []
    if s.join_gaps:
        mask, bridges = join_gaps(mask, lw, unit)
    if s.even_width == "uniform":
        # one pen width for the whole drawing (the Line thickness control in Checkpoint 2
        # already acted on clean.mask, so it is included in the measured pen width)
        width = max(2.0, s.uniform_width * unit if s.uniform_width > 0 else pen_width(clean.mask))
        if s.beautify > 0:
            from .beautify import beautify
            mask, ext = beautify(mask, width, s.beautify, close_ends=s.join_gaps, unit=unit)
            bridges = bridges + ext
        else:
            mask = uniform_width(mask, width)
    else:
        mask = even_width(mask, lw, unit, s.even_width)

    shapes = trace(mask, line_width(mask), s.smooth)
    final = render(shapes, mask.shape)

    skel = centre_lines(final, int(max(6, lw * 2)))
    areas, n_areas = closed_areas(final)
    return EvenResult(mask=final, shapes=shapes, bridges=bridges,
                      loose_ends=loose_ends(skel, min_len=int(max(60, unit * 25))),
                      areas=areas, n_areas=n_areas, line_width=line_width(final))
