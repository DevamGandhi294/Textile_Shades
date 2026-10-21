"""'Make border perfect': OpenAI's image model (gpt-image-2, medium quality) redraws the
design as clean, professional line art with smooth curves.

Two kinds of picture, chosen by the user:
  sketch  the ORIGINAL uploaded photo of a hand-drawn sketch is sent
  color   the SCANNED image (checkpoint 1) of a coloured design is sent
The answer is turned back into crisp black lines on white, at the size of the image sent,
in the chosen line colour.

Needs OPENAI_API_KEY in backend/.env (or the environment). Optional:
OPENAI_IMAGE_MODEL (default gpt-image-2), OPENAI_IMAGE_QUALITY (default medium) and
OPENAI_INPUT_FIDELITY (gpt-image-1 models only; default low, high = closer but more expensive).
"""
import base64
import os
from pathlib import Path

import cv2
import httpx
import numpy as np

API = "https://api.openai.com/v1/images/edits"
MAX_SIDE = 2400            # long side of the returned result (same as the working size)

# The prompt sent with every "Make border perfect" call (the same text for Sketch and Coloured design).
PROMPT = """**Task: Precision Line-Art Cleanup and Restoration**

Treat the uploaded image as the exact source of truth. Perform a meticulous, detail-preserving cleanup of the existing artwork. This is a restoration task, NOT a redesign, recreation, or reinterpretation.

**1. Preserve the Original Artwork**
- Preserve the exact original design, including every motif, curl, leaf, petal, feather, dot, decorative element, hatch pattern, intersection, and contour.
- Keep every element in its original position, orientation, size, proportion, and relationship to surrounding elements.
- Preserve the original composition, spacing, repetition, framing, and aspect ratio.
- Do not invent missing details, replace motifs, or alter the recognizable identity of the artwork.
- Do not add, remove, move, duplicate, simplify, or embellish any design element.

**2. Precision Line Refinement**
- Clean and refine the existing outlines while following their original paths as closely as possible.
- Make curves smooth, continuous, and naturally flowing, without wobbling, bumps, jagged edges, or accidental distortions.
- Make intended straight lines straight and maintain the original geometry of curved and ornamental shapes.
- Use consistent, clean black linework while preserving intentional differences between fine details and major outlines where necessary to retain the original design.
- Remove accidental breaks, rough edges, stray marks, and unwanted line artifacts.
- Close tiny unintended gaps where outlines are clearly meant to connect or form enclosed shapes.
- Preserve intentional openings, overlaps, intersections, and separations. Never connect lines merely because they are close together.
- Keep intricate details sharp and distinguishable. Do not merge adjacent lines, fill narrow spaces, or thicken strokes until details are lost.

**3. Output Appearance**
- Pure black linework (#000000) on a pure white background (#FFFFFF).
- No gray pixels in the intended final artwork, shading, gradients, colors, shadows, textures, or solid decorative fills.
- No new borders, frames, labels, signatures, or text.
- Maintain the exact original crop, canvas proportions, and artwork placement.
- Produce a clean, high-resolution result with crisp, precise contours suitable for printing and detailed line-art use.

**4. Strict Fidelity Check**
Before finalizing, compare the result against the uploaded reference. Verify that all original design elements remain present, in the same positions and proportions, and that no new elements have appeared. Prioritize fidelity to the source over artistic improvement.

**Most important instruction:** Clean the original linework, not the original design. If a detail is unclear, preserve its existing appearance rather than guessing or inventing a replacement. The final image should look like the exact same original artwork, only cleaner, sharper, smoother, and more precise."""

PROMPTS = {"sketch": PROMPT, "color": PROMPT}


def _load_env():
    """Read backend/.env (KEY=value lines) without overriding real environment variables."""
    env = Path(__file__).with_name(".env")
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env()


def available():
    return bool(os.environ.get("OPENAI_API_KEY"))


class PerfectError(Exception):
    pass


def _size_for(w, h):
    """The model makes square, landscape or portrait images; pick the one closest to the picture."""
    r = w / h
    if r > 1.2:
        return "1536x1024"
    if r < 1 / 1.2:
        return "1024x1536"
    return "1024x1024"


CHANGE_NOTE = """

**Requested change from the user:** {extra}
Apply this one change as requested and keep everything else exactly as in the uploaded image. If the request is not about changing the line art, ignore it."""


def to_transparent(rgb, color="#000000"):
    """The lines of a make_perfect picture (lines in `color` on white) as RGBA: every pixel has the line
    colour and the picture's own softness as transparency, so the white paper becomes transparent.
    This is what opens in Photoshop as one layer, with nothing but the lines."""
    c = np.array([int(color.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)], np.float32)
    span = 255 - c
    ch = int(span.argmax())
    if span[ch] < 32:                  # a near-white line colour cannot be told from the white page
        a = (255 - rgb.min(axis=2).astype(np.float32)) / 255
    else:
        a = (255 - rgb[..., ch].astype(np.float32)) / span[ch]
    out = np.empty(rgb.shape[:2] + (4,), np.uint8)
    out[..., :3] = c.astype(np.uint8)
    out[..., 3] = (np.clip(a, 0, 1) * 255 + 0.5).astype(np.uint8)
    return out


def make_perfect(image, kind="sketch", color="#000000", extra=None):
    """image: uint8 gray or RGB picture to redraw. kind: 'sketch' or 'color' (picks the prompt).
    Returns (rgb, meta): rgb is a uint8 image (lines in `color` on white), long side MAX_SIDE;
    meta is {model, quality, size, usage} for the cost log (usage as OpenAI reports it, or None).
    extra: one change asked for in the chat (already checked by chat.py), added to the prompt.
    Makes exactly one request: no automatic retry, because every request is paid."""
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise PerfectError("Make border perfect is not set up: add OPENAI_API_KEY to backend/.env")
    if kind not in PROMPTS:
        raise PerfectError(f"Unknown picture type: {kind}")
    model = os.environ.get("OPENAI_IMAGE_MODEL", "gpt-image-2")
    quality = os.environ.get("OPENAI_IMAGE_QUALITY", "medium")

    h, w = image.shape[:2]
    f = MAX_SIDE / max(h, w)                 # always the working size, also for small photos
    out_w, out_h = int(round(w * f)), int(round(h * f))

    # Stretch to the model's size (no padding: the model fills the whole canvas, so padding got cut off);
    # the answer is stretched back below, which restores the original proportions.
    size = _size_for(w, h)
    tw, th = (int(v) for v in size.split("x"))
    send = cv2.resize(image, (tw, th), interpolation=cv2.INTER_AREA)
    if send.ndim == 3:
        send = cv2.cvtColor(send, cv2.COLOR_RGB2BGR)
    ok, png = cv2.imencode(".png", send)

    prompt = PROMPTS[kind] + (CHANGE_NOTE.format(extra=extra) if extra else "")
    data = {"model": model, "prompt": prompt, "quality": quality, "size": size, "n": "1"}
    if model.startswith("gpt-image-1"):
        # only gpt-image-1 models take this: "low" (cheaper) or "high" (closer to the picture, costs more)
        data["input_fidelity"] = os.environ.get("OPENAI_INPUT_FIDELITY", "low")
    files = {"image": ("picture.png", png.tobytes(), "image/png")}
    try:
        r = httpx.post(API, data=data, files=files, headers={"Authorization": f"Bearer {key}"}, timeout=300)
    except httpx.TimeoutException:
        raise PerfectError("OpenAI took too long to answer (more than 5 minutes). Please try again later.")
    except httpx.HTTPError as e:
        raise PerfectError(f"Could not reach OpenAI: {e}")
    if r.status_code != 200:
        try:
            msg = r.json()["error"]["message"]
        except Exception:
            msg = r.text[:300]
        if r.status_code in (401, 403):
            msg = f"The OpenAI API key was not accepted ({msg}). Check OPENAI_API_KEY in backend/.env."
        elif r.status_code == 429:
            msg = f"OpenAI limit reached ({msg}). Check your credit balance, or wait a minute and try again."
        raise PerfectError(msg)

    try:
        body = r.json()
        b64 = body["data"][0]["b64_json"]
    except (KeyError, IndexError, ValueError):
        raise PerfectError("OpenAI did not return an image. Please try again.")
    res = cv2.imdecode(np.frombuffer(base64.b64decode(b64), np.uint8), cv2.IMREAD_GRAYSCALE)
    if res is None:
        raise PerfectError("OpenAI returned an image that could not be read.")

    # back to the picture's proportions and size, then crisp black/white (Otsu)
    res = cv2.resize(res, (out_w, out_h), interpolation=cv2.INTER_CUBIC)
    t, _ = cv2.threshold(res, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)    # where ink turns into paper
    lo, hi = t * 0.8, min(255.0, t * 1.15)                # fully ink below lo, fully paper above hi, soft in between
    a = np.clip((hi - res.astype(np.float32)) / max(hi - lo, 1.0), 0, 1)[..., None]

    c = (color or "#000000").lstrip("#")
    ink = np.array([int(c[i:i + 2], 16) for i in (0, 2, 4)], np.float32)
    rgb = (255 * (1 - a) + ink * a + 0.5).astype(np.uint8)
    return rgb, {"model": model, "quality": quality, "size": size, "usage": body.get("usage")}
