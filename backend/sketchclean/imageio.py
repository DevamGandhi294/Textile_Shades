"""Loading and saving images."""
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps


def load_gray(path):
    """Load any photo or scan as 8-bit grayscale, turned upright.

    Phone photos often store their rotation as a tag instead of rotating the pixels;
    exif_transpose applies it so the sketch is not processed sideways.
    """
    img = Image.open(path)
    img = ImageOps.exif_transpose(img)
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
        img = Image.alpha_composite(bg, img.convert("RGBA"))
    return np.asarray(img.convert("L"), dtype=np.uint8).copy()


def load_rgb(path):
    """The same photo as load_gray, but in colour (8-bit RGB, turned upright)."""
    img = Image.open(path)
    img = ImageOps.exif_transpose(img)
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
        img = Image.alpha_composite(bg, img.convert("RGBA"))
    return np.asarray(img.convert("RGB"), dtype=np.uint8).copy()


def save_gray(img, path, dpi):
    """8-bit grayscale PNG or TIFF with the given DPI."""
    path = Path(path)
    kw = {"compression": "tiff_lzw"} if path.suffix.lower() in (".tif", ".tiff") else {}
    Image.fromarray(img, "L").save(path, dpi=(dpi, dpi), **kw)


def save_bw(ink, path, dpi, color=(0, 0, 0), transparent=False):
    """Black & white lines. Black lines -> 1-bit file (smallest, bucket-fill safe);
    coloured lines -> RGB; transparent=True -> RGBA PNG with clear paper."""
    path = Path(path)
    tif = path.suffix.lower() in (".tif", ".tiff")
    if transparent and not tif:
        rgba = np.zeros(ink.shape + (4,), np.uint8)
        rgba[..., :3] = color
        rgba[..., 3] = np.where(ink, 255, 0)
        Image.fromarray(rgba, "RGBA").save(path, dpi=(dpi, dpi))
    elif tuple(color) == (0, 0, 0):
        kw = {"compression": "group4"} if tif else {}
        Image.fromarray(~ink).save(path, dpi=(dpi, dpi), **kw)
    else:
        rgb = np.full(ink.shape + (3,), 255, np.uint8)
        rgb[ink] = color
        kw = {"compression": "tiff_lzw"} if tif else {}
        Image.fromarray(rgb, "RGB").save(path, dpi=(dpi, dpi), **kw)


def hex_rgb(c):
    c = (c or "#000000").lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))
