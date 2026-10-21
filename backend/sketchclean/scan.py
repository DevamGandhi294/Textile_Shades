"""Checkpoint 1 — turn a phone photo into a clean "scanner look" image.

Order matters (see README): page → grain → light → levels. Sharpening is NOT done here
on the working image, because sharpening before the lines are found turns grain and
shadow edges into false lines; it is applied only to the scanner-look output.

All steps are automatic. Nothing here needs a user setting.
"""
from dataclasses import dataclass

import cv2
import numpy as np

from .config import WORK_LONG_SIDE, MAX_LONG_SIDE


@dataclass
class ScanResult:
    original: np.ndarray        # photo as loaded (grayscale, upright)
    page: np.ndarray            # after page crop/flatten, original resolution
    levelled: np.ndarray        # float32 0..1, paper = 1, at working size, NOT sharpened
    preview: np.ndarray         # uint8 scanner look (levelled + default sharpening)
    unit: float                 # working pixels per original pixel
    page_found: bool
    noise: float                # estimated grain level of the photo
    color: "np.ndarray | None" = None   # uint8 RGB colour copy of the scan at working size (for colour layers)


# ----------------------------------------------------------------- page

def _order_corners(pts):
    pts = pts.reshape(4, 2).astype(np.float32)
    s, d = pts.sum(1), np.diff(pts, axis=1).ravel()
    return np.array([pts[np.argmin(s)], pts[np.argmin(d)], pts[np.argmax(s)], pts[np.argmax(d)]], np.float32)


def find_page_warp(gray):
    """Find the sheet in a photo. Returns (M, out_w, out_h, margin) to warp it flat, or None.

    Only acts when the bright area is clearly bounded by 4 straight edges against a
    darker background, so a scan, a full-frame photo or a lighting gradient across
    the page is left untouched instead of being cropped wrongly.
    """
    h, w = gray.shape
    scale = 1000 / max(h, w)
    small = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    _, mask = cv2.threshold(cv2.GaussianBlur(small, (9, 9), 0), 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        return None
    c = max(cnts, key=cv2.contourArea)
    if not 0.15 < cv2.contourArea(c) / mask.size < 0.97:
        return None
    inside = np.zeros_like(mask)
    cv2.drawContours(inside, [c], -1, 255, -1)
    if small[inside > 0].mean() - small[inside == 0].mean() < 40:
        return None
    quad = cv2.approxPolyDP(c, 0.02 * cv2.arcLength(c, True), True)
    if len(quad) != 4:
        quad = cv2.boxPoints(cv2.minAreaRect(c))
    q = np.asarray(quad, np.float32).reshape(-1, 1, 2)
    if not cv2.isContourConvex(q.astype(np.int32)):
        return None
    qa = cv2.contourArea(q)
    if qa <= 0 or abs(1 - cv2.contourArea(c) / qa) > 0.06:
        return None
    tol = 0.012 * np.hypot(*small.shape)
    pts = c.reshape(-1, 2)[:: max(1, len(c) // 400)]
    if np.mean([abs(cv2.pointPolygonTest(q, (float(x), float(y)), True)) <= tol for x, y in pts]) < 0.9:
        return None
    tl, tr, br, bl = src = _order_corners(quad) / scale
    out_w = int(max(np.linalg.norm(tr - tl), np.linalg.norm(br - bl)))
    out_h = int(max(np.linalg.norm(bl - tl), np.linalg.norm(br - tr)))
    M = cv2.getPerspectiveTransform(src, np.float32([[0, 0], [out_w, 0], [out_w, out_h], [0, out_h]]))
    m = int(0.012 * min(out_w, out_h)) + 2           # trim the paper edge itself
    return M, out_w, out_h, m


def apply_page_warp(img, warp):
    """Warp a photo (grey or colour) flat with the result of find_page_warp."""
    M, out_w, out_h, m = warp
    flat = cv2.warpPerspective(img, M, (out_w, out_h), flags=cv2.INTER_CUBIC)
    return flat[m:-m, m:-m]


def find_page(gray):
    """Find the sheet in a photo and warp it flat. Returns (image, found)."""
    warp = find_page_warp(gray)
    return (gray, False) if warp is None else (apply_page_warp(gray, warp), True)


# ----------------------------------------------------------------- grain

def estimate_noise(gray):
    """Grain level from the fine detail of flat paper areas (robust: median of |Laplacian|)."""
    lap = cv2.Laplacian(gray.astype(np.float32), cv2.CV_32F)
    return float(np.median(np.abs(lap)) * 1.4826 / 2.5)


def remove_grain(gray, noise):
    """Edge-preserving denoise. Done at the photo's own resolution, before enlarging,
    because grain lives at that scale (and it is faster)."""
    h = float(np.clip(noise * 1.3, 3, 12))
    return cv2.fastNlMeansDenoising(gray, None, h=h, templateWindowSize=7, searchWindowSize=21)


# ----------------------------------------------------------------- light

def even_light(gray):
    """Divide by the paper's own brightness so shadows and gradients become flat.

    The paper brightness is estimated by closing (which paints over dark lines with the
    surrounding paper) and a wide median, on a small copy for speed. Same idea as a
    scanner lamp giving every part of the page the same light.
    """
    return np.clip(gray.astype(np.float32) / np.maximum(paper_field(gray), 1), 0, 1.25)


def paper_field(gray):
    """The paper's own brightness at every pixel (float32, same size as `gray`)."""
    h, w = gray.shape
    f = 600 / max(h, w)
    small = cv2.resize(gray, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
    bg = cv2.morphologyEx(small, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9)))
    bg = cv2.medianBlur(bg, 31)
    return cv2.resize(bg, (w, h), interpolation=cv2.INTER_LINEAR).astype(np.float32)


# ----------------------------------------------------------------- levels

def auto_levels(flat):
    """Paper -> pure white, darkest pencil -> near black, greys kept in between.

    White point = the paper peak of the histogram; black point = the darkest 0.3 %.
    A mild gamma darkens pencil without touching the paper.
    """
    vals = flat[::4, ::4].ravel()
    hist, edges = np.histogram(vals, bins=256, range=(0, 1.25))
    upper = len(hist) // 3
    paper = edges[upper + np.argmax(hist[upper:])]       # most common bright value
    black = np.percentile(vals, 0.3)
    white = paper * 0.96
    lev = np.clip((flat - black) / max(white - black, 1e-3), 0, 1) ** 1.3
    return np.where(lev > 0.93, 1.0, lev).astype(np.float32)     # clean paper


def sharpen(lev, amount, unit):
    """Unsharp mask on a 0..1 image (returns uint8)."""
    img = lev * 255
    if amount > 0:
        blur = cv2.GaussianBlur(img, (0, 0), max(1.0, unit * 0.5))
        img = img + amount * (img - blur)
    return np.clip(img, 0, 255).astype(np.uint8)


# ----------------------------------------------------------------- colour

def _paper_light(chan, mask, fallback):
    """Light of one colour channel across the page, measured on paper pixels only (so coloured areas and
    lines never count as shadow): a blur of the paper pixels divided by a blur of the mask, at two sizes."""
    m = mask.astype(np.float32)
    fine = cv2.GaussianBlur(chan * m, (0, 0), 15), cv2.GaussianBlur(m, (0, 0), 15)
    wide = cv2.GaussianBlur(chan * m, (0, 0), 60), cv2.GaussianBlur(m, (0, 0), 60)
    coarse = np.where(wide[1] > 0.02, wide[0] / np.maximum(wide[1], 1e-6), fallback)
    near = np.where(fine[1] > 0.02, fine[0] / np.maximum(fine[1], 1e-6), coarse)
    k = np.clip(fine[1] / 0.2, 0, 1)                 # trust the near paper only where there is enough of it
    return k * near + (1 - k) * coarse


def color_scan(rgb_page, clean_gray):
    """Colour copy of the scan, same size as the grey working image.

    The paper is found in the photo (the brightest, least coloured big area) and its light is measured
    on paper pixels only, per colour channel. Dividing by it evens out the lighting AND removes the
    colour cast of the lamp: paper becomes white and colours keep their strength. Lines are NOT taken
    from this image; it only tells which colour each area has.
    """
    h, w = clean_gray.shape
    big = rgb_page.shape[1] > w
    rgb = cv2.resize(rgb_page, (w, h), interpolation=cv2.INTER_AREA if big else cv2.INTER_CUBIC)
    f = 600 / max(h, w)
    small = cv2.resize(rgb, None, fx=f, fy=f, interpolation=cv2.INTER_AREA).astype(np.float32) / 255
    lum = small.mean(axis=2)
    paper = np.median(small[lum >= np.percentile(lum, 70)], axis=0)         # colour of the paper (R, G, B)
    # paper pixels: the paper's colour (whatever the brightness) and bright enough not to be a line
    ratio = np.log(np.maximum(small, 1e-3)) - np.log(np.maximum(paper, 1e-3))
    chroma_off = np.abs(ratio - ratio.mean(axis=2, keepdims=True)).max(axis=2)
    mask = (chroma_off < 0.10) & (lum > 0.45 * np.percentile(lum, 95))

    img = rgb.astype(np.float32) / 255
    if mask.mean() >= 0.12:
        field = np.dstack([cv2.resize(_paper_light(small[..., c], mask, paper[c]), (w, h),
                                      interpolation=cv2.INTER_LINEAR) for c in range(3)])
        flat = img / np.maximum(field, 0.05)
    else:                                            # no clear paper in the photo: just stretch each channel
        flat = img / np.maximum(np.percentile(img[::4, ::4].reshape(-1, 3), 99, axis=0), 0.05)
    flat = np.clip(flat, 0, 1).astype(np.float32)

    # smooth the colour noise only (the lightness keeps its detail)
    lab = cv2.cvtColor(flat, cv2.COLOR_RGB2Lab)
    for c in (1, 2):
        lab[..., c] = cv2.GaussianBlur(lab[..., c], (0, 0), 2.0)
    out = cv2.cvtColor(lab, cv2.COLOR_Lab2RGB)
    return (np.clip(out, 0, 1) * 255 + 0.5).astype(np.uint8)


# ----------------------------------------------------------------- run

def scan(gray, auto_crop=True, rgb=None):
    """rgb: the same photo in colour (optional); it gets the same page crop as `gray`."""
    warp = find_page_warp(gray) if auto_crop else None
    page, found = (apply_page_warp(gray, warp), True) if warp is not None else (gray, False)
    noise = estimate_noise(page)
    clean = remove_grain(page, noise)

    long_side = max(clean.shape)
    target = min(max(long_side, WORK_LONG_SIDE), MAX_LONG_SIDE)
    unit = target / long_side
    if abs(unit - 1) > 0.02:
        clean = cv2.resize(clean, None, fx=unit, fy=unit,
                           interpolation=cv2.INTER_CUBIC if unit > 1 else cv2.INTER_AREA)

    levelled = auto_levels(even_light(clean))
    color = None
    if rgb is not None and rgb.shape[:2] == gray.shape:
        color = color_scan(apply_page_warp(rgb, warp) if warp is not None else rgb, clean)
    return ScanResult(original=gray, page=page, levelled=levelled,
                      preview=sharpen(levelled, 0.6, unit), unit=unit, page_found=found, noise=noise, color=color)
