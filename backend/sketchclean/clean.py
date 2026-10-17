"""Checkpoint 2 — remove shades and clear the lines.

Input is the scan from Checkpoint 1 (levelled, not sharpened). Each control changes
one thing and is applied in this fixed order:

    remove shading → contrast → line thickness → [B&W: binarize]  |  [Scanner: sharpen]

The B&W mask is made from the unsharpened image: sharpening creates light/dark halos
along every line, and a threshold turns those into ragged edges.
"""
from dataclasses import dataclass

import cv2
import numpy as np
from skimage.filters import apply_hysteresis_threshold

from .config import CleanSettings
from .lines import disk, line_width, remove_specks
from .scan import ScanResult, sharpen


@dataclass
class CleanResult:
    image: np.ndarray       # float32 0..1 after shading / contrast / thickness (unsharpened)
    scan: np.ndarray        # uint8 scanner-look output (with sharpening)
    mask: np.ndarray        # bool black & white lines (True = ink)
    line_width: float       # typical stroke width in working pixels
    unit: float             # working pixels per original pixel


# ----------------------------------------------------------------- binarization

def wolf_threshold(img, window, k=0.3):
    """Wolf–Jolion local threshold (a refined Sauvola), on a 0..1 image.

    T = (1 - k)·m + k·M + k·(s / R)·(m - M)
      m, s = local mean and std over the window, M = darkest value in the image,
      R = largest local std. Ink = pixels darker than T.
    Chosen because it won the comparison on real pencil photos: clean paper, solid
    lines, and it keeps more faint hatching than Sauvola / Otsu.
    """
    win = (window, window)
    m = cv2.boxFilter(img, cv2.CV_32F, win, borderType=cv2.BORDER_REFLECT)
    sq = cv2.boxFilter(img * img, cv2.CV_32F, win, borderType=cv2.BORDER_REFLECT)
    s = np.sqrt(np.maximum(sq - m * m, 0))
    M = float(img.min())
    R = float(s.max()) or 1e-6
    T = (1 - k) * m + k * M + k * (s / R) * (m - M)
    return img < T


def fine_lines(img, lw):
    """Thin, light strokes (hatching, light detail lines) that the main threshold misses.

    Each pixel is compared only with the paper right around it (about one line width
    away): closing paints over thin dark strokes, and the difference to the original
    is the stroke's own contrast. A light grey hatch line next to white paper stands
    out even though it is far lighter than the outlines, and broad shading is ignored
    because it is wider than the window. Hysteresis keeps a line connected.
    """
    top = cv2.morphologyEx(img, cv2.MORPH_CLOSE, disk(max(2, lw * 0.6))) - img
    med = float(np.median(top))
    floor = med + 4 * 1.4826 * float(np.median(np.abs(top - med)))
    return apply_hysteresis_threshold(top, max(0.08, floor), max(0.16, floor * 2))


def black_and_white(img, unit, lw_hint=None):
    """B&W line mask = main strokes (Wolf) + fine strokes (local contrast)."""
    lw = lw_hint or max(3.0, unit * 1.5)
    # ~4.5 line widths: wide enough for solid strokes, narrow enough that dense hatching
    # is judged against its own neighbourhood (wider windows turn hatching into blotches)
    window = int(np.clip(lw * 4.5, 31, 201)) | 1
    mask = wolf_threshold(img, window)
    if lw_hint:                                      # second pass: line width is known
        mask |= fine_lines(img, lw)
    mask &= img < 0.92                               # pure paper is never ink
    return remove_specks(mask, min_area=int(max(12, unit ** 2 * 2.5)),
                         hole_area=int(max(4, unit ** 2 * 0.5)))


# ----------------------------------------------------------------- controls

def remove_shading(img, lw):
    """Keep thin dark lines, drop wide soft tone (pencil shading, smudges, leftover shadow).

    Morphological closing paints over anything narrower than the window with the
    surrounding lighter tone; subtracting the original leaves exactly the narrow dark
    structures (the lines). Broad shading is wider than the window, so it vanishes.
    """
    k = int(max(lw * 3, 9)) | 1
    closed = cv2.morphologyEx(img, cv2.MORPH_CLOSE, disk(k // 2))
    no_shade = np.clip(1 - (closed - img), 0, 1)
    # hatching is "busy" (light and dark alternate), shading is smooth: measure the local
    # variation and leave busy areas as they are, so hatch patterns are not faded
    win = (int(lw * 2) | 1,) * 2
    m = cv2.blur(img, win)
    std = np.sqrt(np.maximum(cv2.blur(img * img, win) - m * m, 0))
    busy = cv2.GaussianBlur(np.clip((std - 0.05) / 0.07, 0, 1), (0, 0), lw)
    return (busy * img + (1 - busy) * no_shade).astype(np.float32)


def apply_contrast(img, c):
    """c = -1 softer .. 0 unchanged .. +1 stronger: darker lines, whiter paper."""
    if abs(c) < 1e-3:
        return img
    black = max(0.0, 0.25 * c)
    white = 1.0 - 0.12 * c if c > 0 else 1.0 - 0.05 * c
    out = np.clip((img - black) / max(white - black, 1e-3), 0, 1)
    return out ** (1 + 0.6 * c)


def apply_thickness(img, t, unit):
    """t in original-photo pixels: + bolder (dark spreads), - thinner (paper eats in).
    Works on grayscale, so pencil shading inside the line is kept. Fractional values
    blend between the two nearest whole sizes, so the slider moves smoothly."""
    if abs(t) < 1e-3:
        return img
    r = abs(t) * unit
    lo, frac = int(r), r - int(r)
    op = cv2.erode if t > 0 else cv2.dilate          # erode a light-paper image = darker, wider lines
    a = op(img, disk(lo)) if lo else img
    b = op(img, disk(lo + 1))
    return (a * (1 - frac) + b * frac).astype(np.float32)


# ----------------------------------------------------------------- AI method

def ai_lines(prob, contrast, unit):
    """B&W mask from the AI line probability. Hysteresis: a pixel is certainly a line
    above `high`; a weaker pixel is kept only where it continues a certain line, so faint
    parts of real lines survive and isolated faint marks do not. Contrast moves both."""
    c = float(np.clip(contrast, -1, 1))
    high = 0.5 - 0.15 * c
    low = 0.25 - 0.1 * c
    mask = apply_hysteresis_threshold(prob, low, high)
    return remove_specks(mask, min_area=int(max(12, unit ** 2 * 2.5)), hole_area=int(max(4, unit ** 2 * 0.5)))


def detail_regions(ai_mask, classic_mask, lw):
    """Areas of hatching / dense texture: where the classic detector finds much more ink
    than the AI over a few line widths. The AI is trained to erase such 'tone', and
    inside it sometimes draws half-shapes, so there the classic result is used instead."""
    k = (int(lw * 4) | 1,) * 2
    dc = cv2.blur(classic_mask.astype(np.float32), k)
    da = cv2.blur(ai_mask.astype(np.float32), k)
    region = ((dc - da) > 0.12).astype(np.uint8)
    region = cv2.morphologyEx(region, cv2.MORPH_OPEN, disk(lw))          # ignore thin slivers
    region = cv2.dilate(region, disk(lw * 1.5))                          # include the region's edge
    return region.astype(bool)


def add_detail(ai_mask, classic_mask, lw, unit):
    """AI lines everywhere, except:
      * hatched / textured regions → classic result (keeps the hatch pattern),
      * isolated dots and small marks the AI dropped → added from classic, away from AI lines."""
    region = detail_regions(ai_mask, classic_mask, lw)
    out = (ai_mask & ~region) | (classic_mask & region)
    near_ai = cv2.dilate(out.astype(np.uint8), disk(max(1.0, lw * 0.75))).astype(bool)
    marks = remove_specks(classic_mask & ~near_ai, min_area=int(max(12, unit ** 2 * 3)))
    return out | marks


def mask_thickness(mask, t, unit):
    """Bolder (+) / thinner (−) by t original-photo pixels, applied to a B&W mask.
    Uses distance to the nearest edge, so fractional values change width smoothly."""
    if abs(t) < 1e-3:
        return mask
    r = abs(t) * unit
    if t > 0:
        return cv2.distanceTransform((~mask).astype(np.uint8), cv2.DIST_L2, 5) <= r
    thinner = cv2.distanceTransform(mask.astype(np.uint8), cv2.DIST_L2, 5) > r
    # never erase a line completely: keep its centre line
    from .lines import centre_lines
    return thinner | centre_lines(mask, 3)


# ----------------------------------------------------------------- run

def clean(scan: ScanResult, s: CleanSettings, ai_prob=None) -> CleanResult:
    """ai_prob: cached AI line probability (see ai.py). When given and s.method == 'ai',
    the B&W lines come from the AI; otherwise from the classic detector."""
    img = scan.levelled
    unit = scan.unit

    # measure line width once from a quick B&W pass (used to size every step below)
    lw = line_width(black_and_white(img, unit))

    if s.remove_shading:
        img = remove_shading(img, lw)
    img = apply_contrast(img, s.contrast)

    use_ai = s.method == "ai" and ai_prob is not None
    if use_ai:
        mask = ai_lines(ai_prob, s.contrast, unit)
        if s.keep_detail:
            mask = add_detail(mask, black_and_white(img, unit, lw), line_width(mask), unit)
        mask = mask_thickness(mask, s.thickness, unit)
        img = apply_thickness(img, s.thickness, unit)
    else:
        img = apply_thickness(img, s.thickness, unit)
        mask = black_and_white(img, unit, lw)
    return CleanResult(image=img, scan=sharpen(img, s.sharpness, unit), mask=mask,
                       line_width=line_width(mask), unit=unit)


def scan_line_width(scan: ScanResult):
    """Line width of the raw scan, as used to size the AI input."""
    return line_width(black_and_white(scan.levelled, scan.unit))
