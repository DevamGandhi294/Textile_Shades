"""Generate synthetic hand-drawn border sketches for testing the pipeline.

Creates three test inputs in ./samples:
  01_clean_scan.png     - dark pen lines on a flat scan
  02_faint_pencil.png   - faint pencil, paper texture, shadow, dirt, small gaps
  03_phone_photo.jpg    - pencil sketch photographed at an angle on a table
"""
import os
import numpy as np
import cv2

rng = np.random.default_rng(7)
W, H = 2400, 800


def wobble(pts, amp=1.5):
    """Add smooth hand-drawn wobble to a polyline."""
    pts = np.asarray(pts, float)
    n = len(pts)
    noise = rng.normal(0, 1, (n, 2))
    k = max(3, n // 15) | 1
    kernel = np.ones(k) / k
    for d in range(2):
        noise[:, d] = np.convolve(noise[:, d], kernel, mode="same")
    noise *= amp / (noise.std() + 1e-6)
    return pts + noise


def circle(cx, cy, r, n=120):
    t = np.linspace(0, 2 * np.pi, n)
    return np.c_[cx + r * np.cos(t), cy + r * np.sin(t)]


def ellipse(cx, cy, a, b, ang, n=80):
    t = np.linspace(0, 2 * np.pi, n)
    x, y = a * np.cos(t), b * np.sin(t)
    c, s = np.cos(ang), np.sin(ang)
    return np.c_[cx + x * c - y * s, cy + x * s + y * c]


def paisley(cx, cy, size, flip=False):
    t = np.linspace(0, 2 * np.pi, 160)
    r = size * (0.55 + 0.45 * np.cos(t / 2) ** 2)
    x = r * np.cos(t)
    y = 0.6 * r * np.sin(t)
    # curl the tail
    tail = np.exp(-((t - np.pi) ** 2) / 0.4)
    x = x - size * 0.9 * tail
    y = y + size * 0.4 * tail * (1 if not flip else -1)
    return np.c_[cx + x, cy + y]


def design_strokes():
    """Return a list of closed/open polylines that make one border."""
    strokes = []
    m = 40
    # outer frame + inner bands (double lines)
    for y in (60, 95, H - 95, H - 60):
        strokes.append([(m, y), (W - m, y)])
    strokes.append([(m, 60), (m, H - 60)])
    strokes.append([(W - m, 60), (W - m, H - 60)])
    # small triangles in top and bottom bands
    for x in range(m + 40, W - m - 40, 80):
        strokes.append([(x, 95), (x + 40, 60), (x + 80, 95)])
        strokes.append([(x, H - 95), (x + 40, H - 60), (x + 80, H - 95)])
    # vine across the middle field
    xs = np.linspace(m, W - m, 400)
    vine = np.c_[xs, H / 2 + 120 * np.sin((xs - m) / (W - 2 * m) * 6 * np.pi)]
    strokes.append(vine)
    # motifs
    for i, cx in enumerate(range(m + 200, W - m - 100, 400)):
        cy = H / 2
        # flower: centre + 8 petals + outer ring
        strokes.append(circle(cx, cy, 22))
        for k in range(8):
            a = k * np.pi / 4
            strokes.append(ellipse(cx + 55 * np.cos(a), cy + 55 * np.sin(a), 32, 14, a))
        strokes.append(circle(cx, cy, 105))
        # paisleys between flowers
        px = cx + 200
        if px < W - m - 90:
            flip = i % 2 == 0
            py = cy - 150 if flip else cy + 150
            strokes.append(paisley(px, py, 70, flip))
            strokes.append(paisley(px, py, 40, flip))
    return [np.asarray(s, float) for s in strokes]


def densify(s, step=3.0):
    out = [s[0]]
    for a, b in zip(s[:-1], s[1:]):
        n = max(1, int(np.hypot(*(b - a)) / step))
        for t in np.linspace(0, 1, n + 1)[1:]:
            out.append(a + (b - a) * t)
    return np.array(out)


def render(strokes, darkness, thick, gaps=0, grain=0.0, wob=1.5):
    ink = np.zeros((H, W), np.float32)
    for s in strokes:
        s = wobble(densify(s), wob)
        segs = [s]
        if gaps and len(s) > 40:
            segs = []
            cut = sorted(rng.choice(np.arange(10, len(s) - 10), size=min(gaps, len(s) // 40), replace=False))
            prev = 0
            for c in cut:
                g = rng.integers(2, 4)  # 2-3 points * 3px = 6-9 px gap
                segs.append(s[prev:c])
                prev = c + g
            segs.append(s[prev:])
        for seg in segs:
            if len(seg) < 2:
                continue
            p = np.round(seg * 4).astype(np.int32)  # 2-bit subpixel
            cv2.polylines(ink, [p], False, 1.0, thick, cv2.LINE_AA, shift=2)
    ink = cv2.GaussianBlur(ink, (3, 3), 0.8)
    if grain:
        ink *= np.clip(1 - grain * rng.random((H, W)), 0, 1).astype(np.float32)
    return ink * darkness


def paper(base=238, texture=6, shadow=0.0, dirt=0):
    img = np.full((H, W), base, np.float32)
    tex = cv2.GaussianBlur(rng.normal(0, 1, (H, W)).astype(np.float32), (0, 0), 1.2)
    img += tex * texture
    if shadow:
        yy, xx = np.mgrid[0:H, 0:W]
        g = np.clip(1 - (xx / W * 0.8 + yy / H * 0.6), 0, 1) ** 2
        img *= 1 - shadow * g
    for _ in range(dirt):
        x, y = rng.integers(0, W), rng.integers(0, H)
        cv2.circle(img, (int(x), int(y)), int(rng.integers(1, 4)), float(rng.integers(120, 190)), -1)
    return img


def main():
    os.makedirs("samples", exist_ok=True)
    strokes = design_strokes()

    # 1. clean pen scan
    img = paper(texture=3) - render(strokes, 200, 3, wob=1.0)
    cv2.imwrite("samples/01_clean_scan.png", np.clip(img, 0, 255).astype(np.uint8))

    # 2. faint pencil with shadow, dirt, gaps
    img = paper(texture=8, shadow=0.35, dirt=120) - render(strokes, 70, 2, gaps=2, grain=0.5, wob=2.0)
    cv2.imwrite("samples/02_faint_pencil.png", np.clip(img, 0, 255).astype(np.uint8))

    # 3. phone photo: pencil sheet on a table, tilted, warm light
    sheet = paper(texture=6, shadow=0.2, dirt=40) - render(strokes, 110, 2, gaps=1, grain=0.4)
    sheet = np.clip(sheet, 0, 255).astype(np.uint8)
    TW, TH = 3000, 1500
    table = rng.normal(70, 6, (TH, TW)).astype(np.float32)
    table = cv2.GaussianBlur(table, (0, 0), 3)
    src = np.float32([[0, 0], [W, 0], [W, H], [0, H]])
    dst = np.float32([[260, 330], [2700, 180], [2780, 1120], [190, 1260]])
    M = cv2.getPerspectiveTransform(src, dst)
    warped = cv2.warpPerspective(sheet, M, (TW, TH), flags=cv2.INTER_LINEAR, borderValue=0)
    mask = cv2.warpPerspective(np.full((H, W), 255, np.uint8), M, (TW, TH))
    photo = np.where(mask > 0, warped, table).astype(np.float32)
    yy, xx = np.mgrid[0:TH, 0:TW]
    vign = 1 - 0.35 * (((xx - TW / 2) / TW) ** 2 + ((yy - TH / 2) / TH) ** 2) * 2
    photo *= vign
    bgr = np.dstack([photo * 0.92, photo * 0.98, photo * 1.03])
    bgr += rng.normal(0, 3, bgr.shape)
    cv2.imwrite("samples/03_phone_photo.jpg", np.clip(bgr, 0, 255).astype(np.uint8), [cv2.IMWRITE_JPEG_QUALITY, 88])
    print("wrote samples/01_clean_scan.png, 02_faint_pencil.png, 03_phone_photo.jpg")


if __name__ == "__main__":
    main()
