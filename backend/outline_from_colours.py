"""Prototype: outlines straight from the photo's colours (no AI drawing).
Every colour region gets its own closed border, nested shapes included, and every layer
is cut from the same colour map, so the layers can never drift or mix."""
import sys
import cv2
import numpy as np

SAME = 8.0        # Lab distance: colours closer than this merge (lower keeps more minor shades)
MIN_AREA = 150    # px: regions smaller than this are specks and join their neighbour

def palette(lab, k=20):
    rng = np.random.default_rng(0)
    s = lab[rng.choice(len(lab), min(len(lab), 60000), replace=False)]
    _, lbl, c = cv2.kmeans(s, k, None, (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.5), 3, cv2.KMEANS_PP_CENTERS)
    share = np.bincount(lbl.ravel(), minlength=k)
    keep = []
    for i in np.argsort(-share):
        if share[i] < 0.002 * len(s):
            continue
        if all(np.linalg.norm(c[i] - c[j]) >= SAME for j in keep):
            keep.append(i)
    return c[keep]

def main(src, dst):
    bgr = cv2.imread(src)
    f = min(1.0, 1600 / max(bgr.shape[:2]))
    bgr = cv2.resize(bgr, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
    smooth = cv2.bilateralFilter(bgr, 9, 40, 9)                     # kill texture, keep edges
    lab = cv2.cvtColor(smooth.astype(np.float32) / 255, cv2.COLOR_BGR2LAB)
    h, w = lab.shape[:2]
    pal = palette(lab.reshape(-1, 3))
    labels = np.argmin(np.linalg.norm(lab.reshape(-1, 1, 3) - pal[None], axis=2), axis=1).reshape(h, w)
    labels = cv2.medianBlur(labels.astype(np.uint8), 5)              # every pixel: exactly one colour

    out = np.full((h, w, 3), 255, np.uint8)
    regions = 0
    for k, c in enumerate(pal):
        mask = (labels == k).astype(np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        contours, hier = cv2.findContours(mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_NONE)   # nested = parent/child
        lab_c = c.copy(); lab_c[0] = max(0, lab_c[0] - 15)               # border a bit deeper than the fill
        col = (np.clip(cv2.cvtColor(np.float32([[lab_c]]), cv2.COLOR_LAB2BGR)[0, 0], 0, 1) * 255).astype(int).tolist()
        big = [cv2.approxPolyDP(cn, 0.8, True) for cn in contours if cv2.contourArea(cn) >= MIN_AREA]
        cv2.drawContours(out, big, -1, col, 1, cv2.LINE_AA)
        regions += len(big)
    side = np.hstack([bgr, out])
    cv2.imwrite(dst, side)
    print(f"{len(pal)} colours, {regions} closed outlines -> {dst}")

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
