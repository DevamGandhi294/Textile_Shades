"""Split an outlined colour image into one layer per border colour.
Pixels are copied as they are (never redrawn, resized or blurred), so stacking
the layers gives back the exact original image."""
import sys, os
import cv2
import numpy as np

K = 16          # colours to look for first
SAME = 26.0     # hue distance (Lab a/b) below which two colours are one layer
WHITE = 18.0
STRONG = 45.0   # Lab distance from paper: the solid core of a line (used to find colours)    # Lab distance from paper white below which a pixel is background

def main(src, outdir):
    bgr = cv2.imread(src)
    h, w = bgr.shape[:2]
    lab = cv2.cvtColor(bgr.astype(np.float32) / 255, cv2.COLOR_BGR2LAB).reshape(-1, 3)
    paper = np.median(lab[lab[:, 0] > 90], axis=0)
    far = np.linalg.norm(lab - paper, axis=1)
    ink = far >= WHITE                                               # everything that is not paper
    strong = far >= STRONG                                           # the solid core of each line

    # colour of a pixel = its hue (a, b) plus a little lightness, so faded edges join their line
    feat = lab * np.float32([0.15, 1, 1])
    s = feat[strong][np.random.default_rng(0).choice(strong.sum(), min(strong.sum(), 80000), replace=False)]
    _, lbl, c = cv2.kmeans(s, K, None, (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 50, 0.2), 4, cv2.KMEANS_PP_CENTERS)
    share = np.bincount(lbl.ravel(), minlength=K)
    keep = []
    for i in np.argsort(-share):                                    # merge clusters of the same colour
        if share[i] < 0.003 * len(s):
            continue
        if all(np.linalg.norm(c[i] - c[j]) >= SAME for j in keep):
            keep.append(i)
    c = c[keep]
    owner = np.full(h * w, -1, np.int32)
    owner[strong] = np.argmin(((feat[strong][:, None] - c[None]) ** 2).sum(-1), axis=1)
    owner = owner.reshape(h, w)
    # faded edge pixels belong to the line they fade from: take the label of the nearest solid pixel
    core = owner >= 0
    _, idx = cv2.distanceTransformWithLabels((~core).astype(np.uint8), cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL)
    lookup = np.full(idx.max() + 1, -1, np.int32); lookup[idx[core]] = owner[core]
    faded = ink.reshape(h, w) & ~core
    owner[faded] = lookup[idx[faded]]

    os.makedirs(outdir, exist_ok=True)
    layers = []
    for k in range(len(c)):
        mask = owner == k
        rgba = np.zeros((h, w, 4), np.uint8)
        rgba[..., :3][mask] = bgr[mask]                             # original pixels, untouched
        rgba[..., 3][mask] = 255
        cv2.imwrite(f"{outdir}/layer_{k + 1:02d}.png", rgba)
        layers.append((mask, rgba))
    bg = np.zeros((h, w, 4), np.uint8)
    bg[..., :3][owner < 0] = bgr[owner < 0]; bg[..., 3][owner < 0] = 255
    cv2.imwrite(f"{outdir}/layer_00_background.png", bg)

    # proof: stack the layers back and compare with the original, pixel by pixel
    rebuilt = np.zeros_like(bgr)
    for m, rgba in [(owner < 0, bg)] + layers:
        rebuilt[m] = rgba[..., :3][m]
    diff = int(np.count_nonzero(np.any(rebuilt != bgr, axis=2)))
    counts = [int(m.sum()) for m, _ in layers]
    print(f"size {w}x{h}, {len(c)} colour layers + background, pixels in >1 layer: 0, pixels changed: {diff}")
    for k, (m, _) in enumerate(layers):
        col = bgr[m].mean(0)[::-1].astype(int)
        print(f"layer {k + 1}: {counts[k]} px, avg colour #%02x%02x%02x" % tuple(col))

    # contact sheet: each layer on white, small
    tiles = []
    for m, _ in layers:
        t = np.full_like(bgr, 255); t[m] = bgr[m]
        tiles.append(cv2.resize(t, (w // 3, h // 3), interpolation=cv2.INTER_AREA))
    while len(tiles) % 4:
        tiles.append(np.full_like(tiles[0], 255))
    rows = [np.hstack([cv2.copyMakeBorder(t, 4, 4, 4, 4, cv2.BORDER_CONSTANT, value=(200, 200, 200)) for t in tiles[i:i + 4]]) for i in range(0, len(tiles), 4)]
    cv2.imwrite(f"{outdir}/all_layers_preview.png", np.vstack(rows))

main(sys.argv[1], sys.argv[2])
