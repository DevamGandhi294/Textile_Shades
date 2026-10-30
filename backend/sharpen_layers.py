"""Make the colour layers razor sharp: each layer becomes ONE solid colour with hard edges, traced as
vector paths (SVG), so it stays sharp at any zoom. Also writes a 4x PNG preview of the vector result."""
import sys, glob, os
import cv2
import numpy as np
import vtracer

HALF = 32.0     # a soft edge pixel counts as line when it is at least this far from paper white (Lab)

def main(layer_dir, outdir, scale=4):
    os.makedirs(outdir, exist_ok=True)
    paths = sorted(p for p in glob.glob(f"{layer_dir}/layer_*.png") if "background" not in p)
    svg_parts, w, h = [], 0, 0
    for p in paths:
        rgba = cv2.imread(p, cv2.IMREAD_UNCHANGED)
        h, w = rgba.shape[:2]
        mine = rgba[..., 3] > 0
        lab = cv2.cvtColor(rgba[..., :3].astype(np.float32) / 255, cv2.COLOR_BGR2LAB)
        far = np.linalg.norm(lab - np.float32([100, 0, 0]), axis=2)
        # outline vs pale fill/halo: split this layer's pixels by darkness (Otsu), per layer
        L = lab[..., 0]
        dark = np.where(mine, 100 - L, 0).astype(np.float32)
        t, _ = cv2.threshold(dark[mine].astype(np.uint8).reshape(-1, 1), 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        t = min(t, 18.0)                                              # keep light-but-real lines (pale cyan petals)
        solid = mine & (dark >= t)
        core = solid & (dark >= np.percentile(dark[solid], 50))
        b, g, r = np.median(rgba[..., :3][core], axis=0).astype(int)  # the layer's one true colour
        colour = "#%02x%02x%02x" % (r, g, b)
        # upsample the SOFT darkness 4x and cut it at the threshold: edges land between pixels, so curves are smooth
        big = cv2.resize(dark, (w * 4, h * 4), interpolation=cv2.INTER_CUBIC)
        img = np.where(big[..., None] >= t, 0, 255).astype(np.uint8).repeat(3, axis=2)
        ok, png = cv2.imencode(".png", img)
        svg = vtracer.convert_raw_image_to_svg(png.tobytes(), img_format="png", colormode="binary",
                                               mode="spline", filter_speckle=8, corner_threshold=60,
                                               path_precision=3)
        body = svg[svg.index(">", svg.index("<svg")) + 1: svg.rindex("</svg>")]
        name = os.path.splitext(os.path.basename(p))[0]
        layer_svg = f'<g id="{name}" fill="{colour}" transform="scale(0.25)">{body.replace("fill=\"#000000\"", "")}</g>'
        open(f"{outdir}/{name}.svg", "w").write(
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">{layer_svg}</svg>')
        svg_parts.append(layer_svg)
        print(name, colour, "threshold", t)
    open(f"{outdir}/all_layers.svg", "w").write(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
        f'<rect width="100%" height="100%" fill="#ffffff"/>{"".join(svg_parts)}</svg>')

main(sys.argv[1], sys.argv[2])
