"""Colour layers: one layer per main colour of the design, made offline (no AI, no cost).

A designer colours by layers: every area of the same colour belongs to one layer, so one change
recolours all of them. This module finds the colours of the (flattened, light-corrected) colour
scan and decides which layer every area belongs to:

    colour scan + final lines + closed boxes
      -> palette (k-means in Lab, similar colours merged)
      -> every pixel next to no line gets its nearest palette colour
      -> every closed box takes the colour most of its pixels have (crisp shapes, no leaks)
      -> colour is extended under the lines, so hiding the lines leaves no gaps
      -> exports: layered SVG (one group per colour + the lines), a ZIP of transparent PNG layers and a
         layered PSD (Background, one layer per colour, the lines on top)

The AI's "perfect border" can be laid over the same colours: refit_to_lines() gives every closed box of the
AI lines the colour layer that area had in the photo (a vote over the whole box, so a few pixels of shift
between the AI lines and the photo do not matter). No extra AI call is needed.

Areas that stay white (no clear colour) belong to no layer. Greys are not colours.
"""
import io
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from scipy import ndimage

from .export import Page, _svg_d, box_outlines
from .lines import closed_areas, disk

MAX_COLORS = 12            # most layers the user can ask for
AUTO_START = 8             # colours tried first when the number is found automatically
MIN_CHROMA = 20.0          # Lab chroma below this is paper tint, shadow or grey, not a colour
STRONG_CHROMA = 28.0       # a photo has colour layers only if this much colour is really in it ...
STRONG_SHARE = 0.002       # ... on at least this share of the page (a pencil sketch on tinted paper has none)
MERGE_DELTA_E = 14.0       # automatic palette: colours closer than this become one layer
MIN_SHARE = 0.008          # automatic palette: colours covering less than this share are crumbs...
MIN_DISTINCT_SHARE = 0.0015  # ...unless they are clearly different from every other colour (a flower centre)
BLEND_DISTANCE = 12.0      # a small colour this close to the line between two colours is just their blend
L_WEIGHT = 0.6             # lightness counts less than hue when comparing colours
MIN_COVER = 0.35           # a closed box needs this share of coloured pixels to belong to a layer
MIN_AGREE = 0.55           # ... and this share of them must agree on one colour


@dataclass
class LayerBase:
    labels: np.ndarray      # int8 (h, w): -1 = no colour, else palette id
    centers: np.ndarray     # (K, 3) Lab colour of every palette id
    counts: np.ndarray      # (K,) pixels of every palette id
    lines: np.ndarray       # bool (h, w): the final lines


# ----------------------------------------------------------------- colour helpers

def _lab_to_rgb(lab):
    rgb = cv2.cvtColor(np.asarray(lab, np.float32).reshape(1, -1, 3), cv2.COLOR_Lab2RGB).reshape(-1, 3)
    return [tuple(int(v) for v in np.clip(c * 255 + 0.5, 0, 255)) for c in rgb]


def _hex(rgb):
    return "#%02x%02x%02x" % tuple(rgb)


def colour_name(rgb):
    """A plain name for a colour, for the layer list ("Light pink", "Dark green", ...)."""
    r, g, b = (v / 255 for v in rgb)
    mx, mn = max(r, g, b), min(r, g, b)
    v, s = mx, (mx - mn) / mx if mx else 0
    if s < 0.12:
        return "White" if v > 0.9 else "Black" if v < 0.2 else "Grey"
    d = mx - mn
    h = (60 * ((g - b) / d % 6) if mx == r else 60 * ((b - r) / d + 2) if mx == g else 60 * ((r - g) / d + 4))
    if h < 15 or h >= 345:
        base = "Red"
    elif h < 40:
        base = "Orange" if v > 0.55 else "Brown"
    elif h < 70:
        base = "Yellow" if v > 0.6 else "Olive"
    elif h < 165:
        base = "Green"
    elif h < 200:
        base = "Teal"
    elif h < 255:
        base = "Blue"
    elif h < 300:
        base = "Purple"
    else:
        base = "Pink" if v > 0.6 else "Magenta"
    if base in ("Red", "Pink") and s < 0.45 and v > 0.7:
        return "Light pink" if base == "Pink" else "Pink"
    if s < 0.35 and v > 0.75 and base not in ("Yellow", "Orange"):
        return "Light " + base.lower()
    if v < 0.4:
        return "Dark " + base.lower()
    return base


# ----------------------------------------------------------------- palette

def _is_blend(centers, i):
    """True when colour i lies (almost) on the line between two other colours: the muddy edge where two
    colours meet, not a colour of its own."""
    p = centers[i]
    others = [k for k in range(len(centers)) if k != i]
    for x, a in enumerate(others):
        for b in others[x + 1:]:
            ab = centers[b] - centers[a]
            t = np.clip(np.dot(p - centers[a], ab) / max(np.dot(ab, ab), 1e-9), 0, 1)
            if np.linalg.norm(p - (centers[a] + t * ab)) < BLEND_DISTANCE:
                return True
    return False


def _cluster(feats, colors):
    """Palette centres (Lab) and their sizes, biggest first."""
    rng = np.random.default_rng(0)
    sample = feats[rng.choice(len(feats), min(len(feats), 60000), replace=False)]
    k = min(colors if colors > 0 else AUTO_START, len(sample))
    w = np.array([L_WEIGHT, 1, 1], np.float32)
    cv2.setRNGSeed(0)
    _, lab, ctr = cv2.kmeans((sample * w).astype(np.float32), k, None,
                             (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 40, 0.5), 3,
                             cv2.KMEANS_PP_CENTERS)
    centers = (ctr / w).astype(np.float64)
    counts = np.bincount(lab.ravel(), minlength=k).astype(np.float64)

    if colors == 0:                      # automatic: merge look-alikes, drop crumbs, keep small distinct colours
        fixed = np.zeros(len(centers), bool)
        while len(centers) > 1:
            total = counts.sum()
            d = np.linalg.norm(centers[:, None] - centers[None], axis=2)
            np.fill_diagonal(d, np.inf)
            i, j = np.unravel_index(d.argmin(), d.shape)
            if d[i, j] >= MERGE_DELTA_E:
                small = (counts / total < MIN_SHARE) & ~fixed
                if not small.any():
                    break
                i = int(np.argmin(np.where(small, counts, np.inf)))
                j = int(np.argmin(d[i]))
                if d[i, j] >= 2 * MERGE_DELTA_E and counts[i] / total >= MIN_DISTINCT_SHARE and not _is_blend(centers, i):
                    fixed[i] = True                      # small but clearly its own colour: keep it
                    continue
            tot = counts[i] + counts[j]
            centers[j] = (centers[i] * counts[i] + centers[j] * counts[j]) / tot
            counts[j] = tot
            fixed[j] = fixed[j] or fixed[i]
            centers, counts, fixed = np.delete(centers, i, 0), np.delete(counts, i), np.delete(fixed, i)
    order = np.argsort(-counts)
    return centers[order]


def _nearest(feats, centers):
    w = np.array([L_WEIGHT ** 2, 1, 1], np.float32)
    c = centers.astype(np.float32)
    out = np.empty(len(feats), np.int8)
    for i in range(0, len(feats), 400_000):
        d = (((feats[i:i + 400_000, None, :] - c[None]) ** 2) * w).sum(-1)
        out[i:i + 400_000] = d.argmin(1)
    return out


def build_base(color, lines, areas, line_width, colors=0):
    """color: uint8 RGB colour scan. lines: bool final lines. areas: int32 closed boxes (0 = none).
    colors: number of layers (0 = find it automatically)."""
    colors = int(min(max(colors, 0), MAX_COLORS))
    h, w = lines.shape
    if color.shape[:2] != (h, w):
        color = cv2.resize(color, (w, h), interpolation=cv2.INTER_AREA)
    lab = cv2.cvtColor(color.astype(np.float32) / 255, cv2.COLOR_RGB2Lab)
    chroma = np.hypot(lab[..., 1], lab[..., 2])
    near = cv2.dilate(lines.astype(np.uint8), disk(max(1.5, line_width * 0.3))) > 0
    cand = ~near & (chroma >= MIN_CHROMA)
    if (~near & (chroma >= STRONG_CHROMA)).sum() < max(300, STRONG_SHARE * h * w):
        return LayerBase(np.full((h, w), -1, np.int8), np.zeros((0, 3)), np.zeros(0, np.int64), lines)
    labels = np.full((h, w), -1, np.int8)
    empty = LayerBase(labels, np.zeros((0, 3)), np.zeros(0, np.int64), lines)
    ys, xs = np.nonzero(cand)
    if len(ys) < max(500, h * w // 2000):
        return empty

    feats = lab[ys, xs]
    centers = _cluster(feats, colors)
    K = len(centers)
    px = _nearest(feats, centers)
    labels[ys, xs] = px

    # a closed box takes the colour most of its pixels have: crisp shapes that follow the lines
    n = int(areas.max()) if areas.size else 0
    if n > 0:
        a = areas[ys, xs]
        inside = a > 0
        per = np.bincount(a[inside].astype(np.int64) * K + px[inside], minlength=(n + 1) * K).reshape(n + 1, K)
        size = np.bincount(areas.ravel(), minlength=n + 1)
        total = per.sum(1)
        cover = total / np.maximum(size, 1)
        agree = per.max(1) / np.maximum(total, 1)
        take = (cover >= MIN_COVER) & (agree >= MIN_AGREE)
        take[0] = False
        unfilled = (cover < MIN_COVER)
        unfilled[0] = False
        target = np.where(take, per.argmax(1), -1).astype(np.int8)
        in_taken = take[areas]
        labels[in_taken] = target[areas[in_taken]]
        labels[unfilled[areas]] = -1                   # stray colour in a box that is really white

    # crumbs of colour are not layers
    min_area = max(30, int(h * w * 0.00003))
    for k in range(K):
        count, cc, stats, _ = cv2.connectedComponentsWithStats((labels == k).astype(np.uint8), connectivity=8)
        small = np.nonzero(stats[:, cv2.CC_STAT_AREA] < min_area)[0]
        small = small[small > 0]
        if len(small):
            labels[np.isin(cc, small)] = -1
    if not (labels >= 0).any():
        return empty

    # extend the colours under the lines (the lines sit on top, so no gap shows if they are hidden)
    free = labels < 0
    dist, idx = ndimage.distance_transform_edt(free, return_indices=True)
    fill = lines & free & (dist <= line_width * 1.5 + 2)
    labels[fill] = labels[idx[0][fill], idx[1][fill]]

    counts = np.bincount(labels[labels >= 0], minlength=K).astype(np.int64)
    return LayerBase(labels, centers, counts, lines)


# ----------------------------------------------------------------- merge and describe

def apply_merge(base, merge):
    """merge: [(from_id, to_id), ...]. Returns the label image after merging and the palette
    [{"id", "rgb", "hex", "name", "share"}] (biggest first)."""
    K = len(base.centers)
    root = list(range(K))

    def find(i):
        while root[i] != i:
            i = root[i]
        return i

    for a, b in merge:
        if 0 <= a < K and 0 <= b < K and find(a) != find(b):
            root[find(a)] = find(b)
    lut = np.array([find(i) for i in range(K)] + [-1], np.int8)          # the last entry maps -1 to -1
    labels = lut[base.labels] if K else base.labels

    groups = {}
    for i in range(K):
        groups.setdefault(find(i), []).append(i)
    total = max(int((labels >= 0).sum()), 1)
    entries = []
    for rid, members in groups.items():
        n = int(sum(base.counts[m] for m in members))
        if n == 0:
            continue
        lab = sum(base.centers[m] * base.counts[m] for m in members) / n
        rgb = _lab_to_rgb(lab)[0]
        entries.append({"id": int(rid), "rgb": rgb, "hex": _hex(rgb), "name": colour_name(rgb), "share": n / total})
    entries.sort(key=lambda e: -e["share"])
    seen = {}
    for e in entries:                                                     # names must be unique
        seen[e["name"]] = seen.get(e["name"], 0) + 1
        if seen[e["name"]] > 1:
            e["name"] += f" {seen[e['name']]}"
    return labels, entries


def composite(labels, palette, hidden, lines, line_rgb, show_lines=True):
    """White page with the visible layers and (optionally) the lines on top; RGB uint8."""
    img = np.full(labels.shape + (3,), 255, np.uint8)
    for e in palette:
        if e["id"] not in hidden:
            img[labels == e["id"]] = e["rgb"]
    if show_lines:
        img[lines] = line_rgb
    return img


# ----------------------------------------------------------------- exports

def _slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "layer"


def write_layers_svg(path, labels, palette, line_shapes, page: Page, line_hex):
    """One SVG: a group per colour (named "01 Pink", ...) and a "Lines" group on top. The groups are
    Inkscape layers and plain top-level groups for Illustrator and CorelDRAW."""
    index = np.zeros(labels.shape, np.int32)
    for pos, e in enumerate(palette, 1):
        index[labels == e["id"]] = pos
    outlines = dict(box_outlines(index, len(palette)))
    p = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" '
        f'width="{page.mm[0]:.2f}mm" height="{page.mm[1]:.2f}mm" viewBox="0 0 {page.work_w} {page.work_h}">',
        f'<!-- TextileBorder OutlineTool | colour layers | {len(palette)} colours | {page.out_w}x{page.out_h} px at {page.dpi} DPI -->',
    ]
    for pos, e in enumerate(palette, 1):
        ops = outlines.get(pos)
        if not ops:
            continue
        label = f"{pos:02d} {e['name']}"
        p.append(f'<g id="{pos:02d}-{_slug(e["name"])}" inkscape:groupmode="layer" inkscape:label="{label}" '
                 f'fill="{e["hex"]}" stroke="none" fill-rule="evenodd">')
        p.append(f'<path d="{_svg_d(ops)}"/>')
        p.append("</g>")
    p.append(f'<g id="lines" inkscape:groupmode="layer" inkscape:label="Lines" fill="{line_hex}" stroke="none" fill-rule="evenodd">')
    p += [f'<path d="{" ".join(_svg_d(o) for o in shape)}"/>' for shape in line_shapes]
    p.append("</g></svg>")
    Path(path).write_text("\n".join(p), encoding="utf-8")


def _png_bytes(rgba, dpi):
    buf = io.BytesIO()
    Image.fromarray(rgba, "RGBA").save(buf, "PNG", dpi=(dpi, dpi))
    return buf.getvalue()


def write_layers_zip(path, labels, palette, lines, line_rgb, dpi):
    """A ZIP with one transparent PNG per colour, a transparent "lines" PNG and a composite preview.
    All images have the same size, so they stack exactly. dpi: pixels per inch of these images."""
    h, w = labels.shape
    with zipfile.ZipFile(path, "w", zipfile.ZIP_STORED) as z:
        for pos, e in enumerate(palette, 1):
            rgba = np.zeros((h, w, 4), np.uint8)
            m = labels == e["id"]
            rgba[m, :3] = e["rgb"]
            rgba[m, 3] = 255
            z.writestr(f"{pos:02d}_{_slug(e['name'])}.png", _png_bytes(rgba, dpi))
        rgba = np.zeros((h, w, 4), np.uint8)
        rgba[lines, :3] = line_rgb
        rgba[lines, 3] = 255
        z.writestr("lines.png", _png_bytes(rgba, dpi))
        flat = composite(labels, palette, set(), lines, line_rgb)
        z.writestr("composite.png", _png_bytes(np.dstack([flat, np.full((h, w), 255, np.uint8)]), dpi))


# ----------------------------------------------------------------- the AI's lines over the same colours

def refit_to_lines(labels, lines, line_width):
    """Colour layers for a different set of lines (the AI's perfect border).

    labels: int8 colour layer of every pixel from the photo (-1 = none). lines: bool, the new lines.
    Every closed box of the new lines gets the colour layer most of its area had in the photo; a box that
    covers two colours keeps both. The colour is then extended under the lines.
    """
    h, w = lines.shape
    out = np.full((h, w), -1, np.int8)
    areas, n = closed_areas(lines)
    if n == 0 or not (labels >= 0).any():
        return labels.copy()                  # no closed box in the new lines: keep the colours as they are
    K = int(labels.max()) + 1
    has = (areas > 0) & (labels >= 0)
    per = np.bincount(areas[has].astype(np.int64) * K + labels[has], minlength=(n + 1) * K).reshape(n + 1, K)
    size = np.bincount(areas.ravel(), minlength=n + 1)
    total = per.sum(1)
    cover = total / np.maximum(size, 1)
    agree = per.max(1) / np.maximum(total, 1)
    take = (cover >= MIN_COVER) & (agree >= MIN_AGREE)
    mixed = (cover >= MIN_COVER) & ~take
    take[0] = mixed[0] = False
    target = np.where(take, per.argmax(1), -1).astype(np.int8)
    m = take[areas]
    out[m] = target[areas[m]]
    mm = mixed[areas] & (labels >= 0)
    out[mm] = labels[mm]
    outside = (areas == 0) & ~lines & (labels >= 0)          # a background that touches the page edge is not a box
    out[outside] = labels[outside]
    free = out < 0
    dist, idx = ndimage.distance_transform_edt(free, return_indices=True)
    fill = lines & free & (dist <= line_width * 1.5 + 2)
    out[fill] = out[idx[0][fill], idx[1][fill]]
    return out


# ----------------------------------------------------------------- PSD

def new_psd(w, h, dpi):
    """An empty RGB PSD of w x h pixels, with the resolution (pixels per inch) stored in it."""
    from psd_tools import PSDImage
    from psd_tools.constants import Resource
    from psd_tools.psd.image_resources import ImageResource, ResoulutionInfo

    psd = PSDImage.new("RGB", (w, h), color=(255, 255, 255))
    fixed = int(round(dpi * 65536))                                   # pixels per inch as a 16.16 number
    psd.image_resources[Resource.RESOLUTION_INFO] = ImageResource(
        key=Resource.RESOLUTION_INFO,
        data=ResoulutionInfo(horizontal=fixed, horizontal_unit=1, width_unit=1,
                             vertical=fixed, vertical_unit=1, height_unit=1))
    return psd


def add_rgba_layer(psd, name, rgba):
    """Add a named pixel layer on top: rgba is uint8 (h, w, 4) at the canvas size. It is cut to the area that is
    not transparent; a layer with nothing in it is added as one empty pixel, so its name is still in the file."""
    from psd_tools.api.layers import PixelLayer

    ys, xs = np.nonzero(rgba[..., 3])
    if len(ys):
        y0, y1, x0, x1 = int(ys.min()), int(ys.max()) + 1, int(xs.min()), int(xs.max()) + 1
    else:
        y0, y1, x0, x1 = 0, 1, 0, 1
    crop = np.ascontiguousarray(rgba[y0:y1, x0:x1])
    psd.append(PixelLayer.frompil(Image.fromarray(crop, "RGBA"), psd, name, top=y0, left=x0))


def write_layers_psd(path, labels, palette, lines_alpha, line_rgb, dpi, lines_name="Lines", reference=None):
    """One layered PSD (opens in Photoshop with a layers list): a white "Background", a layer per colour
    ("01 Pink", ...) and the lines on top, all with the same position and size.

    lines_alpha: uint8 (h, w) transparency of the lines (255 = line); soft edges are kept.
    dpi: pixels per inch of the image (stored in the file).
    reference: optional uint8 RGB picture (the original photo, same size) added as a HIDDEN layer, so the
    designer can look at the real colours and shading without it being in the way."""
    from psd_tools.api.layers import PixelLayer
    from psd_tools.constants import Compression

    h, w = labels.shape
    psd = new_psd(w, h, dpi)

    def add(name, mask_alpha, rgb):
        """A layer in the colour `rgb` where mask_alpha > 0, cut to the area it covers."""
        ys, xs = np.nonzero(mask_alpha)
        if not len(ys):
            return
        y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
        rgba = np.zeros((y1 - y0, x1 - x0, 4), np.uint8)
        rgba[..., :3] = rgb
        rgba[..., 3] = mask_alpha[y0:y1, x0:x1]
        psd.append(PixelLayer.frompil(Image.fromarray(rgba, "RGBA"), psd, name, top=int(y0), left=int(x0)))

    add("Background", np.full((h, w), 255, np.uint8), (255, 255, 255))
    if reference is not None and reference.shape[:2] == (h, w):
        ref = PixelLayer.frompil(Image.fromarray(reference, "RGB"), psd, "Reference (original photo)", top=0, left=0,
                                 compression=Compression.ZIP)
        ref.visible = False
        psd.append(ref)
    for pos, e in enumerate(palette, 1):
        add(f"{pos:02d} {e['name']}", np.where(labels == e["id"], 255, 0).astype(np.uint8), e["rgb"])
    add(lines_name, lines_alpha, line_rgb)
    psd.save(str(path))
