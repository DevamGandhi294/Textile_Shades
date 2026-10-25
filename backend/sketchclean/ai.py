"""AI line extraction with an ONNX model (MangaLineExtraction, MIT licence).

The model turns a grayscale drawing into clean structural lines: even, thin strokes,
no blobs or smudges. Three things make it reliable on any photo:

1. Input = our Checkpoint 1 scan (shadow-free, levelled). On raw photos it fails.
2. Stroke-width normalisation: the model was trained on lines of a certain width in
   pixels. We measure the line width of each sketch and resize so its strokes land
   near that width (TARGET_STROKE_PX). Too-wide strokes get treated as tone and erased.
3. Overlapping tiles: the image is processed in tiles with a soft blend, so memory
   and time stay bounded for any image size and no seams appear.

Output is a line probability map at working size (1 = certainly line), cached per image.
"""
import os
import time
from pathlib import Path

import cv2
import numpy as np

TARGET_STROKE_PX = 4.0          # stroke width the model handles best (calibrated: 3 drops fine
                                # dots, 5 starts erasing structure as "tone")
MAX_MODEL_SIDE = 1400           # cap on the image the model sees (time grows with area)
TILE = 512                      # tile size (multiple of 16)
OVERLAP = 64                    # tile overlap, blended
MODEL_NAMES = ("manga_line_extraction.onnx", "manga_line_extraction_int8.onnx")

_session = None
_session_path = None


def find_model():
    """Model path: $SKETCHCLEAN_MODEL, else models/ next to the project (full precision first)."""
    env = os.environ.get("SKETCHCLEAN_MODEL")
    if env and Path(env).is_file():
        return Path(env)
    root = Path(__file__).resolve().parent.parent / "models"
    for name in MODEL_NAMES:
        if (root / name).is_file():
            return root / name
    return None


def available():
    try:
        import onnxruntime  # noqa: F401
    except ImportError:
        return False
    return find_model() is not None


def status():
    """Human-readable reason when AI is not available."""
    try:
        import onnxruntime  # noqa: F401
    except ImportError:
        return "AI not available: run  pip install onnxruntime"
    if find_model() is None:
        return "AI not available: put manga_line_extraction.onnx (or _int8.onnx) in the models folder"
    return f"AI model: {find_model().name}"


def session():
    global _session, _session_path
    path = find_model()
    if path is None:
        raise RuntimeError(status())
    if _session is None or _session_path != path:
        import onnxruntime as ort
        wanted = ["CUDAExecutionProvider", "DmlExecutionProvider", "CPUExecutionProvider"]
        providers = [p for p in wanted if p in ort.get_available_providers()]
        opts = ort.SessionOptions()
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        _session = ort.InferenceSession(str(path), sess_options=opts, providers=providers)
        _session_path = path
    return _session


def _run_tile(sess, tile):
    h, w = tile.shape
    H, W = -(-h // 16) * 16, -(-w // 16) * 16
    x = np.full((1, 1, H, W), 255, np.float32)       # pad with white paper
    x[0, 0, :h, :w] = tile
    y = sess.run(None, {"image": x})[0][0, 0, :h, :w]
    return np.clip(y, 0, 255)


def _window(n, overlap):
    """1-D blend weights: flat in the middle, cosine ramps over the overlap."""
    w = np.ones(n, np.float32)
    r = min(overlap, n // 2)
    if r > 0:
        ramp = 0.5 - 0.5 * np.cos(np.linspace(0, np.pi, r + 2)[1:-1])
        w[:r] = ramp
        w[-r:] = ramp[::-1]
    return w


def run_tiled(sess, gray):
    """Model over the whole image in overlapping tiles, blended without seams."""
    h, w = gray.shape
    if h <= TILE and w <= TILE:
        return _run_tile(sess, gray)
    acc = np.zeros((h, w), np.float32)
    wsum = np.zeros((h, w), np.float32)
    step = TILE - OVERLAP
    ys = list(range(0, max(h - TILE, 0) + 1, step)) or [0]
    xs = list(range(0, max(w - TILE, 0) + 1, step)) or [0]
    if ys[-1] + TILE < h:
        ys.append(h - TILE)
    if xs[-1] + TILE < w:
        xs.append(w - TILE)
    for y0 in ys:
        for x0 in xs:
            tile = gray[y0:y0 + TILE, x0:x0 + TILE]
            out = _run_tile(sess, tile)
            wy = _window(tile.shape[0], OVERLAP if 0 < y0 or y0 + TILE < h else 0)
            wx = _window(tile.shape[1], OVERLAP if 0 < x0 or x0 + TILE < w else 0)
            # keep full weight at the image border (no neighbour tile to blend with there)
            if y0 == 0:
                wy[:OVERLAP] = 1
            if y0 + tile.shape[0] >= h:
                wy[-OVERLAP:] = 1
            if x0 == 0:
                wx[:OVERLAP] = 1
            if x0 + tile.shape[1] >= w:
                wx[-OVERLAP:] = 1
            wgt = np.outer(wy, wx)
            acc[y0:y0 + tile.shape[0], x0:x0 + tile.shape[1]] += out * wgt
            wsum[y0:y0 + tile.shape[0], x0:x0 + tile.shape[1]] += wgt
    return acc / np.maximum(wsum, 1e-6)


def line_probability(levelled, line_width_px):
    """levelled: float 0..1 scan at working size (paper = 1).
    line_width_px: typical stroke width at working size.
    Returns (probability map at working size, info dict)."""
    t = time.time()
    sess = session()
    h, w = levelled.shape
    scale = float(np.clip(TARGET_STROKE_PX / max(line_width_px, 1.0), 0.15, 1.5))
    scale = min(scale, MAX_MODEL_SIDE / max(h, w))
    small = cv2.resize((levelled * 255).astype(np.float32), None, fx=scale, fy=scale,
                       interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC)
    out = run_tiled(sess, np.clip(small, 0, 255))
    prob = 1.0 - out / 255.0
    prob = cv2.resize(prob, (w, h), interpolation=cv2.INTER_CUBIC)
    info = {"model": _session_path.name, "model_input_px": [small.shape[1], small.shape[0]],
            "scale": round(scale, 3), "seconds": round(time.time() - t, 1),
            "device": sess.get_providers()[0]}
    return np.clip(prob, 0, 1).astype(np.float32), info
