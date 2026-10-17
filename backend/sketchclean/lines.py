"""Shared tools for working with drawn lines.

Lines are handled two ways:
  * as an ink MASK (True where ink is), which keeps their real width and shape;
  * as CENTRE LINES (a 1-pixel skeleton), used to measure width, find loose ends
    and decide where a gap should be bridged.
Coordinates are (row, col) = (y, x).
"""
import cv2
import numpy as np
from scipy.spatial import cKDTree
from skimage.morphology import skeletonize

# 8 neighbour offsets, clockwise from north. Bit i in a neighbour mask = OFFSETS[i].
OFFSETS = [(-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1)]
_POPCOUNT = np.array([bin(i).count("1") for i in range(256)], np.uint8)


def disk(r):
    r = max(0, int(round(r)))
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))


# ----------------------------------------------------------------- width

def line_width(mask):
    """Typical stroke width in pixels: twice the median distance from centre line to edge."""
    if not mask.any():
        return 3.0
    dist = cv2.distanceTransform(mask.astype(np.uint8), cv2.DIST_L2, 3)
    v = dist[skeletonize(mask)]
    return float(np.median(v) * 2) if v.size else 3.0


def remove_specks(mask, min_area, hole_area=0):
    """Drop ink blobs smaller than min_area (dust, dirt); fill paper holes smaller than hole_area."""
    n, lab, st, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    keep = st[:, cv2.CC_STAT_AREA] >= min_area
    keep[0] = False
    out = keep[lab]
    if hole_area:
        n, lab, st, _ = cv2.connectedComponentsWithStats((~out).astype(np.uint8), connectivity=4)
        holes = st[:, cv2.CC_STAT_AREA] < hole_area
        holes[0] = False
        out |= holes[lab]
    return out


# ----------------------------------------------------------------- centre-line graph

def neighbour_masks(skel):
    """Bitmask of skeleton neighbours per pixel, with stair-step diagonals removed,
    so every plain line pixel has exactly 2 neighbours."""
    s = np.pad(skel, 1)
    H, W = skel.shape

    def at(dy, dx):
        return s[1 + dy:1 + dy + H, 1 + dx:1 + dx + W]

    masks = np.zeros(skel.shape, np.uint8)
    for i, (dy, dx) in enumerate(OFFSETS):
        nb = at(dy, dx).copy()
        if dy and dx:
            nb &= ~(at(dy, 0) | at(0, dx))
        masks |= (nb & skel).astype(np.uint8) << i
    masks[~skel] = 0
    return masks


def degree(masks):
    """Number of neighbours: 1 = loose end, 2 = plain line, 3+ = junction."""
    return _POPCOUNT[masks]


def neighbours(masks, y, x):
    m = masks[y, x]
    return [(y + dy, x + dx) for i, (dy, dx) in enumerate(OFFSETS) if m >> i & 1]


def walk(masks, start, first, limit):
    """Follow a line from start through first while pixels are plain line pixels."""
    path = [start, first]
    prev, cur = start, first
    while len(path) < limit and _POPCOUNT[masks[cur]] == 2:
        nxt = [p for p in neighbours(masks, *cur) if p != prev]
        if not nxt:
            break
        prev, cur = cur, nxt[0]
        if cur == start:
            break
        path.append(cur)
    return path


def prune_spurs(skel, max_len):
    """Remove short whiskers that branch off a line and end in nothing
    (thinning a slightly lumpy stroke creates them)."""
    skel = skel.copy()
    for _ in range(2):
        masks = neighbour_masks(skel)
        deg = degree(masks)
        removed = 0
        for y, x in np.argwhere(skel & (deg == 1)):
            nb = neighbours(masks, y, x)
            if not nb:
                continue
            path = walk(masks, (y, x), nb[0], max_len + 2)
            if len(path) <= max_len and deg[path[-1]] >= 3:
                for p in path[:-1]:
                    skel[p] = False
                removed += 1
        skel &= degree(neighbour_masks(skel)) > 0
        if not removed:
            break
    return skel


def centre_lines(mask, spur_len):
    return prune_spurs(skeletonize(mask), spur_len)


def loose_ends(skel, min_len=0):
    """Line ends that touch nothing. min_len skips dots and tiny marks."""
    deg = degree(neighbour_masks(skel))
    ends = [tuple(p) for p in np.argwhere(skel & (deg == 1))]
    if min_len and ends:
        n, lab, st, _ = cv2.connectedComponentsWithStats(skel.astype(np.uint8), connectivity=8)
        big = st[:, cv2.CC_STAT_AREA] >= min_len
        ends = [e for e in ends if big[lab[e]]]
    return ends


# ----------------------------------------------------------------- gaps

def find_gap_bridges(skel, max_gap, min_len=0):
    """Pairs of loose line ends that are one broken line, as [(y0, x0, y1, x1)].

    Two ends are joined when they are close and face each other (each end's direction
    points toward the other). Ends on pieces shorter than min_len (dots, specks, short
    hatch marks) are left alone, and an end is never joined back onto its own line.
    """
    masks = neighbour_masks(skel)
    ends = loose_ends(skel, min_len)
    if len(ends) < 2:
        return []
    look_back = max(6, int(max_gap * 0.6))
    info = {}
    for e in ends:
        nb = neighbours(masks, *e)
        path = walk(masks, e, nb[0], look_back + 1)
        d = np.array(e, float) - np.array(path[-1], float)
        n = np.linalg.norm(d)
        own = set(walk(masks, e, nb[0], int(max_gap * 2.5) + 2))
        info[e] = (d / n if n else d, own)

    pts = np.array(ends)
    tree = cKDTree(pts)
    cands = []
    for i, e in enumerate(ends):
        d, own = info[e]
        for j in tree.query_ball_point(e, max_gap):
            if j <= i:
                continue
            p = ends[j]
            if p in own:
                continue
            v = np.array(p, float) - np.array(e, float)
            dist = np.linalg.norm(v)
            if dist < 1.5:
                continue
            c1 = float(d @ (v / dist))
            c2 = float(info[p][0] @ (-v / dist))
            if dist <= max_gap * 0.5 and c1 > -0.2 and c2 > -0.2:
                score = dist * 0.4                       # very close: almost surely one line
            elif c1 < 0.3 or c2 < 0.3:
                continue
            else:
                score = dist * (2.2 - c1 - c2) * 0.7
            cands.append((score, e, p))
    cands.sort()
    used, bridges = set(), []
    for _, e, p in cands:
        if e in used or p in used:
            continue
        used.update((e, p))
        bridges.append((e[0], e[1], p[0], p[1]))
    return bridges


# ----------------------------------------------------------------- centre-line paths

def centreline_paths(skel):
    """Split centre lines into paths between ends and junctions, plus closed loops.
    Returns a list of (points_xy float array, closed bool). Paths meeting at a junction
    share the junction point exactly, so the network stays connected in CAD software."""
    masks = neighbour_masks(skel)
    deg = degree(masks)
    visited = np.zeros(skel.shape, bool)
    paths = []
    nodes = [tuple(p) for p in np.argwhere(skel & (deg != 2) & (deg > 0))]
    for node in nodes:
        for nb in neighbours(masks, *node):
            if deg[nb] != 2:
                if node < nb:
                    paths.append(([node, nb], False))
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
            paths.append((path, False))
    for start in map(tuple, np.argwhere(skel & (deg == 2) & ~visited)):   # loops with no junction
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
        paths.append((path, True))

    out = []
    for path, closed in paths:
        xy = np.array([(x + 0.5, y + 0.5) for y, x in path], float)
        if len(xy) >= 5:                               # remove pixel stair-steps, keep end points
            k = np.ones(5) / 5
            if closed:
                pad = np.r_[xy[-5:], xy, xy[:5]]
                sm = np.c_[np.convolve(pad[:, 0], k, "same"), np.convolve(pad[:, 1], k, "same")][5:-5]
            else:
                sm = np.c_[np.convolve(xy[:, 0], k, "same"), np.convolve(xy[:, 1], k, "same")]
                sm[:2], sm[-2:] = xy[:2], xy[-2:]
            xy = sm
        if len(xy) >= 3:
            xy = cv2.approxPolyDP(xy.astype(np.float32).reshape(-1, 1, 2), 0.8, closed).reshape(-1, 2).astype(float)
        if len(xy) >= 2:
            out.append((xy, closed))
    return out


# ----------------------------------------------------------------- closed areas

def closed_areas(mask):
    """Label paper areas fully surrounded by ink (the boxes a designer will colour).
    Areas touching the image border are not closed."""
    n, lab = cv2.connectedComponents((~mask).astype(np.uint8), connectivity=4)
    edge = np.unique(np.r_[lab[0], lab[-1], lab[:, 0], lab[:, -1]])
    lab[np.isin(lab, edge)] = 0
    lab[mask] = 0
    ids = np.unique(lab)
    ids = ids[ids > 0]
    remap = np.zeros(n, np.int32)
    remap[ids] = np.arange(1, len(ids) + 1)
    return remap[lab], len(ids)
