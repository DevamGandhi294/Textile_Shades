#!/usr/bin/env python3
"""Research tool: compare binarization algorithms side by side on your own sketches.

Same light correction for all, then 9 algorithms (Otsu, Bradley, Niblack, Sauvola, Wolf,
NICK, Gatos, Su, ISauvola) from the Doxa library. Writes one B&W file per algorithm and
a comparison grid.

    pip install doxapy
    python tools/compare_binarization.py samples/05_peacock_phone_photo.jpg --out research
    python tools/compare_binarization.py photo.jpg --crop 300,640,150,470   (y0,y1,x0,x1 in the photo)
"""
import argparse
import time
from pathlib import Path

import cv2
import numpy as np


def main():
    import doxapy
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("--out", default="research")
    ap.add_argument("--crop", help="y0,y1,x0,x1 area of the photo to show in the grid (default: centre)")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    gray = cv2.imread(a.image, cv2.IMREAD_GRAYSCALE)
    gray = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    bg = cv2.medianBlur(cv2.morphologyEx(gray, cv2.MORPH_CLOSE,
                                         cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (31, 31))), 51)
    flat = np.clip(gray.astype(np.float32) / np.maximum(bg, 1) * 255, 0, 255).astype(np.uint8)

    A = doxapy.Binarization.Algorithms
    runs = [("Otsu (no light fix)", A.OTSU, {}, gray), ("Otsu", A.OTSU, {}, flat),
            ("Bradley", A.BRADLEY, {"window": 61, "k": 0.15}, flat),
            ("Niblack", A.NIBLACK, {"window": 61, "k": -0.2}, flat),
            ("Sauvola", A.SAUVOLA, {"window": 61, "k": 0.2}, flat),
            ("Wolf", A.WOLF, {"window": 61, "k": 0.2}, flat),
            ("NICK", A.NICK, {"window": 61, "k": -0.15}, flat),
            ("Gatos", A.GATOS, {"window": 61, "k": 0.2, "glyph": 60}, flat),
            ("Su", A.SU, {"window": 0, "minN": 0}, flat),
            ("ISauvola", A.ISAUVOLA, {"window": 61, "k": 0.01}, flat)]
    results = {}
    for name, alg, params, img in runs:
        res = np.empty(img.shape, img.dtype)
        t = time.time()
        b = doxapy.Binarization(alg)
        b.initialize(img)
        b.to_binary(res, params)
        if res.mean() < 128:
            res = 255 - res
        results[name] = res
        cv2.imwrite(str(out / (name.lower().replace(" ", "_").replace("(", "").replace(")", "") + ".png")), res)
        print(f"{name:22s} {(time.time() - t) * 1000:7.0f} ms   ink {(res < 128).mean() * 100:5.1f}%")

    h, w = gray.shape
    if a.crop:
        y0, y1, x0, x1 = [int(v) * 2 for v in a.crop.split(",")]
    else:
        y0, y1, x0, x1 = h // 3, 2 * h // 3, w // 4, 3 * w // 4

    def tile(img, label):
        t = cv2.resize(img[y0:y1, x0:x1], None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
        t = cv2.cvtColor(t, cv2.COLOR_GRAY2BGR)
        cv2.rectangle(t, (0, 0), (len(label) * 11 + 12, 28), (40, 40, 40), -1)
        cv2.putText(t, label, (6, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)
        return np.pad(t, ((4, 4), (4, 4), (0, 0)), constant_values=150)

    tiles = [tile(gray, "Original photo")] + [tile(v, k) for k, v in results.items()]
    while len(tiles) % 4:
        tiles.append(np.full_like(tiles[0], 255))
    cv2.imwrite(str(out / "grid.png"), np.vstack([np.hstack(tiles[i:i + 4]) for i in range(0, len(tiles), 4)]))
    print(f"grid: {out / 'grid.png'}")


if __name__ == "__main__":
    main()
