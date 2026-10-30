"""Black outline (from the AI) + original photo -> one coloured outline layer per colour.

1. Lines: the dark pixels of the black outline image (tiny gaps closed).
2. Shapes: every closed white area between the lines is one shape (flower inside flower = two shapes).
3. Colour: each shape takes the colour of its INSIDE in the original photo (shrunk away from its edge,
   so a few pixels of AI drift do not matter).
4. Layers: shape colours are grouped (close shades = one layer); each shape's own closed border is cut
   from the black lines and painted in its layer colour.
"""
import os
import sys
import cv2
import numpy as np

SAME = 16.0          # Lab distance: shape colours closer than this share a layer (lower = more shades kept)
MAX_LAYERS = 12      # most colour layers kept
MIN_LAYER_SHARE = 0.01  # a colour group smaller than this share of all shapes joins its nearest layer
MIN_SHAPE = 30       # px: areas smaller than this are gaps inside a line, not shapes
PAPER = 14.0         # Lab distance from white: closer than this is paper, not colour
STRONG = 40.0        # Lab distance from white: a solid line colour, not a faded edge
BG_SHARE = 0.01      # a plain-paper area bigger than this share of the picture is background
BG_NEAR = 18.0       # Lab distance: a big area this close to the given background colour is background
INK_REACH = 3.0      # line widths: the original's line is looked for this far from the AI line (its drift)
SMOOTH = 9           # px: a line pixel takes the colour most of the line around it has (no single specks)


def lab_of(bgr):
    return cv2.cvtColor(bgr.astype(np.float32) / 255, cv2.COLOR_BGR2LAB)


def read_lines(outline_bgr, size, photo_bgr):
    """Black lines as a crisp mask (bool) plus a soft alpha (uint8), at `size` (w, h)."""
    grey = cv2.cvtColor(outline_bgr, cv2.COLOR_BGR2GRAY)
    grey = cv2.resize(grey, size, interpolation=cv2.INTER_CUBIC)
    grey, warp = align_to_photo(grey, photo_bgr)
    if warp is not None:
        print("aligned to photo: shift %.1f, %.1f px, scale %.3f" % (warp[0, 2], warp[1, 2], warp[0, 0]))
    dark = 255 - grey
    t, _ = cv2.threshold(dark, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    lines = dark >= max(t, 60)
    lines = cv2.morphologyEx(lines.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8)) > 0
    return lines, dark


def align_to_photo(outline_grey, photo_bgr):
    """Undo the AI's drift: find the shift / scale / small rotation that lays the outline on the photo's edges
    (OpenCV ECC on blurred edge maps), and warp the outline by it. Returns the aligned grey outline + the move."""
    h, w = outline_grey.shape
    f = min(1.0, 1000 / max(h, w))                                # align on a small copy: fast
    sz = (max(1, round(w * f)), max(1, round(h * f)))
    edges = cv2.Canny(cv2.GaussianBlur(cv2.cvtColor(photo_bgr, cv2.COLOR_BGR2GRAY), (5, 5), 0), 40, 120)
    a = cv2.GaussianBlur(cv2.resize(edges, sz, interpolation=cv2.INTER_AREA).astype(np.float32), (0, 0), 3)
    b = cv2.GaussianBlur(cv2.resize(cv2.Canny(outline_grey, 50, 150), sz, interpolation=cv2.INTER_AREA).astype(np.float32), (0, 0), 3)
    warp = np.eye(2, 3, dtype=np.float32)
    try:
        _, warp = cv2.findTransformECC(a, b, warp, cv2.MOTION_AFFINE,
                                       (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 200, 1e-6), None, 5)
    except cv2.error:
        return outline_grey, None                                  # could not align: use as is
    warp[:, 2] /= f                                                # the move at full size
    aligned = cv2.warpAffine(outline_grey, warp, (w, h), flags=cv2.INTER_CUBIC | cv2.WARP_INVERSE_MAP,
                             borderMode=cv2.BORDER_CONSTANT, borderValue=255)
    return aligned, warp


def line_width(lines):
    dist = cv2.distanceTransform(lines.astype(np.uint8), cv2.DIST_L2, 3)
    return max(1.0, 2 * float(np.percentile(dist[dist > 0], 90)))


def shapes_and_colours(lines, photo_lab, width, background=None):
    """Every closed area between the lines, and its colour in the original. The colour is the most common
    NON-paper colour inside the area; if the inside is plain paper (an outline-only original), the colour of
    the ring just around it is used. Big plain-paper areas are background (colour = None), and so are big areas
    of the `background` colour (Lab) if one is given."""
    n, label, stats, _ = cv2.connectedComponentsWithStats((~lines).astype(np.uint8), connectivity=4)
    H, W = lines.shape
    paper_lab = np.float32([100, 0, 0])
    far = np.linalg.norm(photo_lab - paper_lab, axis=2)
    paper = far < PAPER
    line_art = paper.mean() > 0.5          # the original is itself outline art: shapes take their LINE colour
    strong = far >= STRONG
    colours, keep, is_bg = np.zeros((n, 3), np.float32), np.zeros(n, bool), np.zeros(n, bool)
    pad = int(width) + 4
    ring_k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * pad + 1,) * 2)
    for i in range(1, n):
        a = stats[i, cv2.CC_STAT_AREA]
        if a < MIN_SHAPE:
            continue
        x, y, w, h = stats[i, :4]
        x0, y0, x1, y1 = max(0, x - pad), max(0, y - pad), min(W, x + w + pad), min(H, y + h + pad)
        m = (label[y0:y1, x0:x1] == i).astype(np.uint8)
        inner = cv2.erode(m, np.ones((3, 3), np.uint8)) > 0
        if inner.sum() < 12:
            inner = m > 0
        ink = ~paper[y0:y1, x0:x1]
        use = inner & ink
        # plain paper reaching the picture's edge is the background; a closed white petal inside the design is not
        page = a > BG_SHARE * H * W and (x == 0 or y == 0 or x + w >= W or y + h >= H)
        if line_art and use.sum() < max(6, 0.10 * inner.sum()) and page:
            is_bg[i] = True
            continue
        if line_art:                                               # colour of the line drawn around it
            ring = (cv2.dilate(m, ring_k) > 0) & strong[y0:y1, x0:x1]
            if ring.sum() >= 6:
                f = far[y0:y1, x0:x1]
                use = ring & (f >= np.percentile(f[ring], 50))     # the solid line, not its pale fill or halo
        elif use.sum() < max(6, 0.10 * inner.sum()):                # inside is plain paper
            if page:
                is_bg[i] = True                                    # the background
                continue
            use = (cv2.dilate(m, ring_k) > 0) & ink                # take the colour of its border instead
            if use.sum() < 6:
                continue
        px = photo_lab[y0:y1, x0:x1][use]
        px = px[px[:, 0] > 22] if (px[:, 0] > 22).sum() >= 0.25 * len(px) else px   # skip black printed lines
        q = np.round(px / np.float32([8, 5, 5])).astype(np.int32)  # most common colour (hue matters most)
        _, inv, cnt = np.unique(q, axis=0, return_inverse=True, return_counts=True)
        colours[i] = px[inv.ravel() == cnt.argmax()].mean(axis=0)
        if background is not None and a > BG_SHARE * H * W and np.linalg.norm(colours[i] - background) < BG_NEAR:
            is_bg[i] = True                                        # a coloured background, not a shape
            continue
        keep[i] = True
    return label, stats, colours, keep, is_bg


def group_colours(colours, keep, stats):
    """Shape colours -> layers (biggest total area first). Returns layer of every shape and layer colours."""
    idx = np.flatnonzero(keep)
    order = idx[np.argsort(-stats[idx, cv2.CC_STAT_AREA])]
    centres, area, layer_of = [], [], np.full(len(colours), -1)
    for i in order:
        c = colours[i]
        if centres:
            d = np.linalg.norm(np.array(centres) - c, axis=1)
            j = int(np.argmin(d))
            if d[j] < SAME:
                layer_of[i] = j
                a = stats[i, cv2.CC_STAT_AREA]                      # running area-weighted mean
                centres[j] = (centres[j] * area[j] + c * a) / (area[j] + a)
                area[j] += a
                continue
        centres.append(c.copy())
        area.append(stats[i, cv2.CC_STAT_AREA])
        layer_of[i] = len(centres) - 1
    centres, area = np.array(centres), np.array(area, np.float64)
    # small groups (a few odd shapes) join the nearest big layer, and at most MAX_LAYERS layers stay
    order = np.argsort(-area)
    total = area.sum()
    big = [j for n, j in enumerate(order) if n < MAX_LAYERS and area[j] >= MIN_LAYER_SHARE * total]
    remap = {}
    for j in range(len(centres)):
        remap[j] = j if j in big else big[int(np.argmin(np.linalg.norm(centres[big] - centres[j], axis=1)))]
    new_index = {j: n for n, j in enumerate(big)}
    layer_of = np.array([new_index[remap[l]] if l >= 0 else -1 for l in layer_of])
    return layer_of, centres[big], area[big]


def hex_of(lab, deeper=True):
    lab = np.array(lab, np.float32)
    if deeper:                                                     # border a bit darker so it shows on white
        lab[0] -= 25 if lab[0] > 80 else 15 if lab[0] > 55 else 5
    rgb = cv2.cvtColor(lab[None, None], cv2.COLOR_LAB2RGB)[0, 0]
    return "#%02x%02x%02x" % tuple(int(round(v)) for v in np.clip(rgb, 0, 1) * 255)


def colour_layers(photo, outline, background=None):
    """photo, outline: BGR pictures (the outline is laid on the photo's size). background: the background colour
    as Lab, or None. Returns [(colour "#rrggbb", lab, shape area px, rgba BGR)], one per colour layer, biggest first."""
    h, w = photo.shape[:2]
    lines, dark = read_lines(outline, (w, h), photo)
    if not lines.any():
        return []
    width = line_width(lines)
    label, stats, colours, keep, is_bg = shapes_and_colours(lines, lab_of(photo), width, background)
    if not keep.any():
        return []
    layer_of, centres, area = group_colours(colours, keep, stats)

    plab = lab_of(photo)
    far = np.linalg.norm(plab - np.float32([100, 0, 0]), axis=2)
    ink = far >= STRONG
    line_art = (far < PAPER).mean() > 0.5          # the original is outline art: its lines have their own colours

    # every line pixel belongs to ONE layer (so no colour is painted over another): first by the shapes it
    # closes, the smaller shape on top
    reach = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (int(width) * 2 + 3,) * 2)
    owner = np.full((h, w), -1, np.int32)
    areas = []
    for j in np.argsort(-area):                                    # big shapes first, small ones win their lines
        mine = np.isin(label, np.flatnonzero(layer_of == j))       # all shapes of this colour
        owner[(cv2.dilate(mine.astype(np.uint8), reach) > 0) & lines] = j
    for j in range(len(centres)):
        areas.append(int(np.isin(label, np.flatnonzero(layer_of == j)).sum()))
    # then by the ORIGINAL's own line under it: a line pixel takes the colour of the nearest ink of the photo
    # (outline art: every line; otherwise only lines that close no coloured shape), smoothed along the line so
    # one JPEG speck cannot change a piece of line
    vote_on = lines if line_art else lines & (owner < 0)
    if vote_on.any() and ink.any():
        dist, idx = cv2.distanceTransformWithLabels((~ink).astype(np.uint8), cv2.DIST_L2, 5,
                                                    labelType=cv2.DIST_LABEL_PIXEL)
        src = np.zeros((idx.max() + 1, 3), np.float32)
        src[idx[ink]] = plab[ink]
        ys, xs = np.nonzero(vote_on & (dist <= INK_REACH * width))
        if len(ys):
            which = np.argmin(np.linalg.norm(src[idx[ys, xs]][:, None] - centres[None], axis=2), axis=1)
            best, count = np.full((h, w), -1, np.int32), np.zeros((h, w), np.float32)
            for j in range(len(centres)):
                hit = np.zeros((h, w), np.float32)
                hit[ys[which == j], xs[which == j]] = 1
                c = cv2.boxFilter(hit, -1, (SMOOTH, SMOOTH), normalize=False)
                better = c > count
                best[better], count[better] = j, c[better]
            owner = np.where(vote_on & (best >= 0), best, owner)
    layers = []
    for j in range(len(centres)):
        border = owner == j
        if not border.any():
            continue
        colour = hex_of(centres[j], deeper=not line_art)          # outline art: exactly the original line colour
        mine = areas[j]
        rgba = np.zeros((h, w, 4), np.uint8)
        rgba[..., :3] = [int(colour[i:i + 2], 16) for i in (5, 3, 1)]
        rgba[..., 3] = np.where(border, dark, 0)                    # the AI line's own crisp edge
        layers.append((colour, centres[j], mine, rgba))
    return sorted(layers, key=lambda l: -l[2])                     # big areas first, small details on top


def run(photo_path, outline_path, outdir):
    photo = cv2.imread(photo_path)
    outline = cv2.imread(outline_path)
    h, w = photo.shape[:2]
    os.makedirs(outdir, exist_ok=True)
    layers = []
    for colour, _, a, rgba in colour_layers(photo, outline):
        name = f"layer_{len(layers) + 1:02d}_{colour[1:]}"
        cv2.imwrite(f"{outdir}/{name}.png", rgba)
        layers.append((name, colour, a, rgba))

    page = np.full((h, w, 3), 255, np.float32)                     # preview: all layers stacked on white
    for _, _, _, rgba in sorted(layers, key=lambda l: -l[2]):       # big areas first, small details on top
        a = rgba[..., 3:4] / 255.0
        page = page * (1 - a) + rgba[..., :3] * a
    cv2.imwrite(f"{outdir}/preview.png", page.astype(np.uint8))
    print(f"{w}x{h}, {len(layers)} colour layers (+ background)")
    for name, colour, a, _ in layers:
        print(f"  {name}  {colour}  shape area {a}px")
    return layers


if __name__ == "__main__":
    run(sys.argv[1], sys.argv[2], sys.argv[3])
