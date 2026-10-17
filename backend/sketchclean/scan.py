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


# ----------------------------------------------------------------- page

def _order_corners(pts):
    pts = pts.reshape(4, 2).astype(np.float32)
    s, d = pts.sum(1), np.diff(pts, axis=1).ravel()
    return np.array([pts[np.argmin(s)], pts[np.argmin(d)], pts[np.argmax(s)], pts[np.argmax(d)]], np.float32)


def find_page(gray):
    """Find the sheet in a photo and warp it flat. Returns (image, found).

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
        return gray, False
    c = max(cnts, key=cv2.contourArea)
    if not 0.15 < cv2.contourArea(c) / mask.size < 0.97:
        return gray, False
    inside = np.zeros_like(mask)
    cv2.drawContours(inside, [c], -1, 255, -1)
    if small[inside > 0].mean() - small[inside == 0].mean() < 40:
        return gray, False
    quad = cv2.approxPolyDP(c, 0.02 * cv2.arcLength(c, True), True)
    if len(quad) != 4:
        quad = cv2.boxPoints(cv2.minAreaRect(c))
    q = np.asarray(quad, np.float32).reshape(-1, 1, 2)
    if not cv2.isContourConvex(q.astype(np.int32)):
        return gray, False
    qa = cv2.contourArea(q)
    if qa <= 0 or abs(1 - cv2.contourArea(c) / qa) > 0.06:
        return gray, False
    tol = 0.012 * np.hypot(*small.shape)
    pts = c.reshape(-1, 2)[:: max(1, len(c) // 400)]
    if np.mean([abs(cv2.pointPolygonTest(q, (float(x), float(y)), True)) <= tol for x, y in pts]) < 0.9:
        return gray, False
    tl, tr, br, bl = src = _order_corners(quad) / scale
    out_w = int(max(np.linalg.norm(tr - tl), np.linalg.norm(br - bl)))
    out_h = int(max(np.linalg.norm(bl - tl), np.linalg.norm(br - tr)))
    M = cv2.getPerspectiveTransform(src, np.float32([[0, 0], [out_w, 0], [out_w, out_h], [0, out_h]]))
    flat = cv2.warpPerspective(gray, M, (out_w, out_h), flags=cv2.INTER_CUBIC)
    m = int(0.012 * min(out_w, out_h)) + 2           # trim the paper edge itself
    return flat[m:-m, m:-m], True


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
    h, w = gray.shape
    f = 600 / max(h, w)
    small = cv2.resize(gray, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
    bg = cv2.morphologyEx(small, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9)))
    bg = cv2.medianBlur(bg, 31)
    bg = cv2.resize(bg, (w, h), interpolation=cv2.INTER_LINEAR).astype(np.float32)
    return np.clip(gray.astype(np.float32) / np.maximum(bg, 1), 0, 1.25)


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


# ----------------------------------------------------------------- run

def scan(gray, auto_crop=True):
    page, found = find_page(gray) if auto_crop else (gray, False)
    noise = estimate_noise(page)
    clean = remove_grain(page, noise)

    long_side = max(clean.shape)
    target = min(max(long_side, WORK_LONG_SIDE), MAX_LONG_SIDE)
    unit = target / long_side
    if abs(unit - 1) > 0.02:
        clean = cv2.resize(clean, None, fx=unit, fy=unit,
                           interpolation=cv2.INTER_CUBIC if unit > 1 else cv2.INTER_AREA)

    levelled = auto_levels(even_light(clean))
    return ScanResult(original=gray, page=page, levelled=levelled,
                      preview=sharpen(levelled, 0.6, unit), unit=unit, page_found=found, noise=noise)
