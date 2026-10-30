"""Every colour layer (transparent PNG) -> a vector SVG layer: sharp at any zoom, same size and position."""
import sys, glob, os
import cv2
import numpy as np
import vtracer

UP = 4      # trace at 4x so the curves follow the line's soft edge between pixels


def layer_group(alpha, colour, name):
    """One layer's alpha (uint8, h x w) -> an SVG group of vector shapes in `colour`, at the layer's size."""
    h, w = alpha.shape
    big = cv2.resize(alpha, (w * UP, h * UP), interpolation=cv2.INTER_CUBIC)
    img = np.where(big[..., None] >= 128, 0, 255).astype(np.uint8).repeat(3, axis=2)
    ok, png = cv2.imencode(".png", img)
    svg = vtracer.convert_raw_image_to_svg(png.tobytes(), img_format="png", colormode="binary", mode="spline",
                                           filter_speckle=8, corner_threshold=60, path_precision=2)
    body = svg[svg.index(">", svg.index("<svg")) + 1: svg.rindex("</svg>")].replace('fill="#000000"', "")
    return f'<g id="{name}" fill="{colour}" transform="scale({1 / UP})">{body}</g>'


def svg_page(groups, w, h, background="#fff"):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
            f'<rect width="100%" height="100%" fill="{background}"/>{"".join(groups)}</svg>')


def main(layer_dir, outdir):
    os.makedirs(outdir, exist_ok=True)
    parts, w, h = [], 0, 0
    for p in sorted(glob.glob(f"{layer_dir}/layer_*.png")):
        rgba = cv2.imread(p, cv2.IMREAD_UNCHANGED)
        h, w = rgba.shape[:2]
        colour = "#%02x%02x%02x" % tuple(int(v) for v in rgba[..., :3][rgba[..., 3] > 0][0][::-1])
        name = os.path.splitext(os.path.basename(p))[0]
        g = layer_group(rgba[..., 3], colour, name)
        open(f"{outdir}/{name}.svg", "w").write(svg_page([g], w, h, "none"))
        parts.append(g)
    open(f"{outdir}/all_layers.svg", "w").write(svg_page(parts, w, h))
    print(len(parts), "vector layers")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
