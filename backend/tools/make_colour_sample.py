#!/usr/bin/env python3
"""Makes a synthetic hand-coloured border to try the colour layers on:

    python tools/make_colour_sample.py        writes samples/07_color_border.jpg

Five flowers (pink x3, orange x2, yellow centres) joined by green leaves, drawn with black outlines
and coloured the way a person does it: colour a little uneven, a little outside the lines, and the
photo has uneven light, a warm colour cast and grain.
"""
import sys
from pathlib import Path

import cv2
import numpy as np

W, H = 1600, 700
PINK, ORANGE, GREEN, YELLOW = (226, 112, 160), (238, 150, 60), (70, 150, 84), (242, 202, 60)

# where things are (before the photo effects): used by the tests to check the layers
FLOWERS = [(200 + 300 * i, 350, PINK if i % 2 == 0 else ORANGE) for i in range(5)]
LEAVES = [(350 + 300 * i, 350, 14 if i % 2 == 0 else -14) for i in range(4)]


def _ellipse(img, c, axes, angle, fill, rng, bleed=1):
    cv2.ellipse(img, (int(c[0]), int(c[1])), (axes[0] + bleed, axes[1] + bleed), angle, 0, 360,
                tuple(int(v) for v in np.clip(np.array(fill) + rng.integers(-10, 11, 3), 0, 255)), -1, cv2.LINE_AA)


def make(seed=7):
    rng = np.random.default_rng(seed)
    fills = np.full((H, W, 3), 255, np.uint8)
    lines = np.full((H, W), 255, np.uint8)
    for x, y, col in FLOWERS:
        for k in range(6):
            a = np.deg2rad(60 * k)
            c = (x + 52 * np.cos(a), y + 52 * np.sin(a))
            _ellipse(fills, c, (42, 20), 60 * k, col, rng)
            cv2.ellipse(lines, (int(c[0]), int(c[1])), (42, 20), 60 * k, 0, 360, 0, 4, cv2.LINE_AA)
        _ellipse(fills, (x, y), (22, 22), 0, YELLOW, rng)
        cv2.circle(lines, (x, y), 22, 0, 4, cv2.LINE_AA)
    for x, y, tilt in LEAVES:
        _ellipse(fills, (x, y), (62, 22), tilt, GREEN, rng)
        cv2.ellipse(lines, (x, y), (62, 22), tilt, 0, 360, 0, 4, cv2.LINE_AA)
    img = np.minimum(fills.astype(np.float32), lines[..., None].astype(np.float32) * 1.0)   # lines on top of colour
    img = cv2.GaussianBlur(img, (0, 0), 1.0)

    # the photo: uneven light, a warm cast, grain
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    light = 1.0 - 0.22 * ((xx / W - 0.25) ** 2 + (yy / H - 0.3) ** 2) * 2.2
    img = img * light[..., None] * np.array([1.0, 0.96, 0.86], np.float32)
    img = img + rng.normal(0, 4.0, img.shape)
    return np.clip(img, 0, 255).astype(np.uint8)


if __name__ == "__main__":
    out = Path(__file__).resolve().parent.parent / "samples" / "07_color_border.jpg"
    cv2.imwrite(str(out), cv2.cvtColor(make(), cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 90])
    print("wrote", out)
    sys.exit(0)
